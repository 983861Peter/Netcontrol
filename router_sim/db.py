# name=router_sim/db.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Read DB URL from env, default to a local sqlite file for development
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./network_mgmt.db")

# Normalize legacy provider URLs: some services still hand out 'postgres://'
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# If psycopg (v3) is installed, prefer it explicitly so SQLAlchemy doesn't try to import psycopg2
try:
    import psycopg  # type: ignore
    if SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
        SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
except Exception:
    # psycopg not present; leave the URL as-is
    pass

# Only pass SQLite-specific connect_args when using sqlite.
connect_args = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

try:
    if connect_args:
        engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
    else:
        engine = create_engine(SQLALCHEMY_DATABASE_URL)
except Exception as e:
    raise RuntimeError(
        f"Failed to create SQLAlchemy engine for DATABASE_URL={SQLALCHEMY_DATABASE_URL!r}: {e}"
    ) from e

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
