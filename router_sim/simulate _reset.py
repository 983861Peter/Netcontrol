# simulate_reset.py
from router_sim.db import SessionLocal
from router_sim.models import Device
from reset_detector import evaluate_device_reset

db = SessionLocal()
dev = db.query(Device).first()
scanned = {
    "ip": dev.ip_address,
    "uptime": 10,
    "hostname": "Router",
    "config": {"ssid":"DefaultSSID", "wifi_password":"changeme"},
    "credentials_ok": False
}
is_reset, details = evaluate_device_reset(dev, scanned)
print("is_reset", is_reset, details)
