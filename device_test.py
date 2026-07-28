# device_test.py
from datetime import datetime
from sqlalchemy.orm import Session
from router_sim.db import engine, SessionLocal, Base
from router_sim.models import Device

# ✅ Ensure tables exist
Base.metadata.create_all(bind=engine)

def add_device(device_id, name, ip, model="Generic"):
    db: Session = SessionLocal()
    try:
        new_dev = Device(
            device_id=device_id,
            name=name,
            ip_address=ip,
            model=model,
            status="offline",
            created_at=datetime.utcnow()
        )
        db.add(new_dev)
        db.commit()
        print(f"✅ Device added: {device_id}")
    except Exception as e:
        print("❌ Error adding device:", e)
    finally:
        db.close()

def list_devices():
    db: Session = SessionLocal()
    try:
        devices = db.query(Device).all()
        if not devices:
            print("⚠️ No devices found in database.")
        for d in devices:
            print(f"- ID: {d.device_id} | IP: {d.ip_address} | Model: {d.model} | Status: {d.status}")
    except Exception as e:
        print("❌ Error retrieving devices:", e)
    finally:
        db.close()

if __name__ == "__main__":
    # ✅ Test adding a device
    add_device("test-router-001", "Test Router", "192.168.0.100", "D-Link DIR-615")

    # ✅ Test printing devices
    print("\n📌 Database devices:")
    list_devices()
