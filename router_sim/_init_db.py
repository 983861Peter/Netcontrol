import os
import sys

# router_sim/_init_db.py - safe initializer that uses the application's engine
# It will only call Base.metadata.create_all to avoid accidental data loss.

try:
    # Import the application's db module which exposes Base and engine
    from router_sim import db as app_db
except Exception as e:
    print("[init_db] error importing router_sim.db:", e)
    raise

Base = getattr(app_db, "Base", None)
engine = getattr(app_db, "engine", None)

if Base is None or engine is None:
    print("[init_db] Could not find Base and engine in router_sim.db. Check router_sim/db.py")
    sys.exit(1)

print("🔄 Creating database tables (using engine):", engine.url)
# Do NOT drop existing tables in this initializer to avoid data loss in persistent deployments
Base.metadata.create_all(bind=engine)
print("✅ Database tables created successfully.")
