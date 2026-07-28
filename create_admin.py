# create_admin.py
from router_sim.models import AuthUser, Base
from router_sim.db import SessionLocal, engine
from passlib.hash import bcrypt

db = SessionLocal()
admin = AuthUser(
    username="admin",
    email="admin@example.com",
    password_hash=bcrypt.hash("admin123"),
    role="administrator",
    is_active=True,
    can_add_device=True,
    can_delete_device=True,
    can_restart_device=True,
    can_configure_device=True
)
db.add(admin)
db.commit()
print("✅ Admin created successfully")
