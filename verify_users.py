# verify_users.py
from router_sim.db import SessionLocal
from router_sim.models import AuthUser

db = SessionLocal()
for u in db.query(AuthUser).all():
    print(u.username, u.role)
db.close()
