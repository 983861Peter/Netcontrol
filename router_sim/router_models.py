# router_models.py - defines SQLAlchemy ORM models for router-related database tables

from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from router_sim.db import Base


class Router(Base):
    __tablename__ = "routers"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, index=True)
    ip_address = Column(String, index=True)
    model = Column(String, default="GenericRouter")
    status = Column(String, default="online")
    ssid = Column(String, default="DefaultSSID")
    wifi_password = Column(String, default="changeme")
    hostname = Column(String, default="router")
    config = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    dhcp_leases = relationship("DHCPLease", back_populates="router", cascade="all, delete-orphan")
    firewall_rules = relationship("FirewallRule", back_populates="router", cascade="all, delete-orphan")
    backups = relationship("RouterBackup", back_populates="router", cascade="all, delete-orphan")


class DHCPLease(Base):
    __tablename__ = "dhcp_leases"

    id = Column(Integer, primary_key=True, index=True)
    router_id = Column(Integer, ForeignKey("routers.id"))
    ip_address = Column(String)
    mac_address = Column(String)
    lease_start = Column(DateTime, default=datetime.utcnow)
    lease_end = Column(DateTime)
    active = Column(Boolean, default=True)

    router = relationship("Router", back_populates="dhcp_leases")


class FirewallRule(Base):
    __tablename__ = "firewall_rules"

    id = Column(Integer, primary_key=True, index=True)
    router_id = Column(Integer, ForeignKey("routers.id"))
    rule_name = Column(String)
    action = Column(String)  # allow / deny
    protocol = Column(String)  # tcp / udp / icmp
    port = Column(String)
    source = Column(String)
    destination = Column(String)

    router = relationship("Router", back_populates="firewall_rules")


class RouterBackup(Base):
    __tablename__ = "router_backups"

    id = Column(Integer, primary_key=True, index=True)
    router_id = Column(Integer, ForeignKey("routers.id"))
    backup_data = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)
    note = Column(String, nullable=True)

    router = relationship("Router", back_populates="backups")
