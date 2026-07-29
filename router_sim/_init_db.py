import os
from sqlalchemy import create_engine
from router_sim.models import Base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./network_mgmt.db")
print(f"Using DATABASE_URL={DATABASE_URL}")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
print(" Creating database tables...")
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
print(" Database tables created successfully.")
