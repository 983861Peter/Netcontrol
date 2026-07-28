# adapters/vendor_sim.py
import random
import time
from datetime import datetime
from .db import SessionLocal
from .models import Device
from .reset_detector import evaluate_device_reset, hash_config
from .ws_broadcast import broadcast_ws_event

"""
This is a FULLY simulated device adapter.

It pretends:
 - each device has uptime
 - each device has a config dict
 - hostname can change
 - credentials may fail randomly

This allows REAL reset detection even without real devices.
"""

# Simulated device memory store
SIM_DEVICES = {}

def init_simulated_device(mac, ip):
    """
    Called once when the poller discovers a new device.
    Simulates the internal state of the device.
    """

    SIM_DEVICES[mac] = {
        "ip": ip,
        "uptime": random.randint(30, 5000),
        "hostname": f"router-{mac[-6:].replace(':','')}",
        "config": {
            # "ssid": "MyWifi",
            # "password": "12345678",
            # "channel": 6
        },
        "credentials_ok": True,
        "last_change_ts": time.time(),
    }


def simulate_reset_event(mac):
    """
    Manually simulates a reset (for testing).
    """
    if mac not in SIM_DEVICES:
        return

    SIM_DEVICES[mac]["uptime"] = 10
    SIM_DEVICES[mac]["config"] = {
        # "ssid": "Default",
        # "password": "admin",
        # "channel": 1
    }
    SIM_DEVICES[mac]["hostname"] = "FactoryRouter"
    SIM_DEVICES[mac]["credentials_ok"] = False


def vendor_poll_device(ip, device):
    """
    Called by your poller to retrieve REAL-TIME
    simulated device data.
    """
    mac = device.mac_address

    # If new device -> create simulated memory
    if mac not in SIM_DEVICES:
        init_simulated_device(mac, ip)

    sim = SIM_DEVICES[mac]

    # Randomly make uptime increase
    sim["uptime"] += random.randint(1, 30)

    # OPTIONAL: Random small modifications to config
    if random.random() < 0.03:  # 3% chance
        sim["config"]["channel"] = random.choice([1, 6, 11])

    # OPTIONAL: Random credential failure
    if random.random() < 0.02:  # 2% chance
        sim["credentials_ok"] = False

    # Return EXACT format expected by reset_detector
    return {
        "ip": sim["ip"],
        "uptime": sim["uptime"],
        "hostname": sim["hostname"],
        "config": sim["config"].copy(),
        "credentials_ok": sim["credentials_ok"],
    }

# polling loop
def poll_device_and_evaluate(mac, ip):
    """
    Example: poll single device by IP using vendor adapter (SSH/HTTP/SNMP)
    Adapter must return e.g. {"uptime": int, "config": {...}, "hostname": "...", "credentials_ok": True/False}
    """
    db = SessionLocal()
    try:
        dev = db.query(Device).filter(Device.mac_address == mac).first()
        if not dev:
            return

        # call vendor adapter (implement per vendor), here's a placeholder:
        scanned = vendor_poll_device(ip, dev)  # returns dict as above OR None on fail
        now = datetime.utcnow()

        if scanned is None:
            # mark offline maybe
            dev.status = "offline"
            db.commit()
            return

        # update basic fields
        dev.ip_address = scanned.get("ip", dev.ip_address)
        dev.last_seen = now
        new_uptime = scanned.get("uptime")
        if new_uptime is not None:
            dev.uptime = int(new_uptime)

        # compute new config hash if available
        if "config" in scanned and scanned["config"] is not None:
            new_hash = hash_config(scanned["config"])
            dev.last_config_hash = new_hash

        db.commit()

        # run reset evaluation
        is_reset, details = evaluate_device_reset(dev, scanned)
        if is_reset:
            # mark flag and emit alert
            dev.needs_restore = 1
            db.commit()
            # create event log entry and broadcast via websocket
            payload = {
                "type": "device_reset",
                "device_id": dev.device_id,
                "mac_address": dev.mac_address,
                "ip_address": dev.ip_address,
                "ts": now.isoformat(),
                "details": details
            }
            # store to event logs table if you have it
            # broadcast via websocket (see WS broadcaster example below)
            broadcast_ws_event(payload)
        if scanned:
            dev = db.query(Device).filter(Device.device_id == mac).first()
            if dev:
                    is_reset, details = evaluate_device_reset(dev, scanned)
                    db.close()
                    return is_reset, details
            return False, {}
    finally:
        db.close()