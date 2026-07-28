from router_sim.models import * # Adjust imports if models are separate
from router_sim.db import engine, Base

from sqlalchemy import create_engine
from router_sim.models import * # Adjust imports if models are separate
from router_sim.db import engine, Base  # Ensure this imports the correct engine  
engine = create_engine("sqlite:///./network_mgmt.db", echo=True)
print("🔄 Creating database tables...")
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
print("✅ Database tables created successfully.")