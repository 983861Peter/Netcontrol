# auto_restore.py
from .db import SessionLocal
from .models import Device
from .config_manager import ConfigManager  # your module to push configs

def attempt_restore(device_id):
    db = SessionLocal()
    try:
        dev = db.query(Device).filter(Device.device_id == device_id).first()
        if not dev or not dev.last_config_hash:
            return False, "no config"

        # retrieve the last saved config from config_history or backups table
        # example: ConfigManager.get_backup_by_hash(hash)
        cfg = ConfigManager.get_backup_by_hash(dev.last_config_hash)
        if not cfg:
            return False, "no backup found"

        # apply config via adapter; this should be vendor-specific
        ok, msg = ConfigManager.push_config(dev.ip_address, dev.mac_address, cfg)
        if ok:
            dev.needs_restore = 0
            db.commit()
            return True, "restored"
        else:
            return False, msg
    finally:
        db.close()
