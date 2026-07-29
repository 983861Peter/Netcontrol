# init_db.py
from sqlalchemy import inspect
from router_sim.models import Base
from router_sim.db import engine, SQLALCHEMY_DATABASE_URL

print(f"Using DATABASE_URL={SQLALCHEMY_DATABASE_URL}")

# Check if tables already exist
inspector = inspect(engine)
existing_tables = inspector.get_table_names()

# Only create tables that don't exist
if existing_tables:
    print(f"Tables already exist: {', '.join(existing_tables)}")
    print("Skipping table creation to preserve existing data.")
else:
    print("No tables found. Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully.")
