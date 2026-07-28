# jobs/poller.py
import asyncio
import json
from datetime import datetime
from .db import SessionLocal
from .models import Device, Backup, EventLog

from.vendor_sim import vendor_poll_device
from .adapter_loader import get_vendor_adapter
from .reset_detector import evaluate_device_reset
from .ws_broadcast import broadcast_ws_event

async def poll_device_and_evaluate(mac, ip):
    """
    Polls ONE device using the vendor adapter.
    Then evaluates whether it has been RESET.
    """
    db = SessionLocal()
    try:
        dev = db.query(Device).filter(Device.mac_address == mac).first()
        if not dev:
            return

        # Poll simulated device through adapter
        scanned = vendor_poll_device(ip, dev)
        now = datetime.utcnow()

        # Update basic fields
        dev.ip_address = scanned.get("ip", dev.ip_address)
        dev.last_seen = now

        new_uptime = scanned.get("uptime")
        if new_uptime is not None:
            dev.uptime = int(new_uptime)

        # Handle config hash
        if scanned.get("config") is not None:
            from .reset_detector import hash_config
            dev.last_config_hash = hash_config(scanned["config"])

        db.commit()

        # Evaluate RESET logic
        is_reset, details = evaluate_device_reset(dev, scanned)

        if is_reset:
            dev.needs_restore = 1
            db.commit()

            payload = {
                "type": "device_reset",
                "device_id": dev.device_id,
                "mac_address": dev.mac_address,
                "ip_address": dev.ip_address,
                "ts": now.isoformat(),
                "details": details
            }

            broadcast_ws_event(payload)
            
            # --- Automatic Reconfiguration Logic ---
            # Find latest backup
            latest_backup = db.query(Backup).filter(Backup.device_id == dev.device_id).order_by(Backup.timestamp.desc()).first()
            
            if latest_backup:
                try:
                    config = json.loads(latest_backup.config_json)
                    adapter = get_vendor_adapter(dev.model)
                    
                    restored = False
                    if adapter:
                        # Attempt to push config
                        if hasattr(adapter, 'DLinkAdapter'):
                            agent = adapter.DLinkAdapter(host=dev.ip_address, username="admin", password="")
                            if "ssid" in config:
                                res = agent.update_wifi(config["ssid"], config.get("wifi_password", ""))
                                if res.get("success"): restored = True
                        elif hasattr(adapter, 'push_config'):
                            res = adapter.push_config(dev.ip_address, {}, config)
                            if res.get("status") == "success": restored = True
                    
                    if restored:
                        dev.needs_restore = 0
                        db.add(EventLog(device_id=dev.device_id, activity_type="auto_restore", severity="NOTICE", message=f"Auto-restored device {dev.device_id} from backup after reset detection."))
                        db.commit()
                        broadcast_ws_event({"type": "alert", "severity": "NOTICE", "message": f"Auto-restored {dev.device_id}"})
                        
                except Exception as e:
                    print(f"[AutoRestore] Failed to restore {dev.device_id}: {e}")

    finally:
        db.close()


async def monitoring_loop():
    """
    Background monitoring loop that runs forever.
    Polls all devices every 10 seconds.
    """
    while True:
        db = SessionLocal()
        try:
            devices = db.query(Device).all()
        finally:
            db.close()

        tasks = []

        for d in devices:
            if d.ip_address:
                tasks.append(poll_device_and_evaluate(d.mac_address, d.ip_address))

        if tasks:
            await asyncio.gather(*tasks)

        await asyncio.sleep(10)
