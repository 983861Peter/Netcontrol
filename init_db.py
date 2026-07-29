# router_sim/_init_db.py
from router_sim.models import Base
from router_sim.db import engine, SQLALCHEMY_DATABASE_URL

print(f"Using DATABASE_URL={SQLALCHEMY_DATABASE_URL}")
print(" Creating database tables...")
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
print(" Database tables created successfully.")
