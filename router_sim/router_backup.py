from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .db import get_db
from .models import Device, Backup
import json
from datetime import datetime
from .vendor_sim import vendor_poll_device  # OR actual adapter
from .reset_detector import hash_config

router = APIRouter(prefix="/backup", tags=["Device Backups"])

@router.post("/create/{device_id}")
def create_device_backup(device_id: int, db: Session = Depends(get_db)):
    # Load device
    dev = db.query(Device).filter(Device.device_id == device_id).first()
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")

    # Poll the device for live config via adapter
    scanned = vendor_poll_device(dev.ip_address, dev)

    if not scanned:
        raise HTTPException(status_code=500, detail="Failed to retrieve device data")

    # Convert config to JSON
    config_json = json.dumps(scanned.get("config", {}), indent=2)

    # Create backup entry
    backup = Backup(
        device_id=dev.device_id,
        mac_address=dev.mac_address,
        ip_address=dev.ip_address,
        hostname=scanned.get("hostname", "unknown"),
        config_json=config_json,
    )

    db.add(backup)
    db.commit()
    db.refresh(backup)

    return {
        "status": "success",
        "backup_id": backup.id,
        "device_id": backup.device_id,
        "mac_address": backup.mac_address,
        "timestamp": backup.created_at,
    }
