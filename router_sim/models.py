# auth/models.py
"""
ORM models for authentication and user capability flags.
Uses the same SQLAlchemy Base/engine as your main application.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, JSON, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
from .db import Base 
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any

class AuthUser(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="technician")
    is_active = Column(Boolean, default=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    phone_number = Column(String, nullable=True)
    ui_theme = Column(String, default="light")
    theme_accent = Column(String, default="#0096FF")
    created_at = Column(DateTime, default=func.now())

    can_add_device = Column(Boolean, default=False)
    can_delete_device = Column(Boolean, default=False)
    can_restart_device = Column(Boolean, default=False)
    can_configure_device = Column(Boolean, default=False)
    __table_args__ = {'extend_existing': True}
    company = relationship("Company", back_populates="auth_users")

class TransmissionStation(Base):
    __tablename__ = "transmission_stations"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    location = Column(String, nullable=True)
    is_gateway = Column(Boolean, default=False)  # Marks the entry point of the network
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    station_type = Column(String, default="primary") # primary, secondary, backup
    parent_id = Column(Integer, ForeignKey("transmission_stations.id"), nullable=True)
    link_device_id = Column(String, ForeignKey("devices.device_id"), nullable=True)
    device_model = Column(String, nullable=True) # Main equipment (e.g. AirFiber, Mikrotik)

    company = relationship("Company", back_populates="stations")
    sectors = relationship("Sector", back_populates="station", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="station", cascade="all, delete-orphan", foreign_keys="[Device.station_id]")

class Sector(Base):
    __tablename__ = "sectors"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)  # e.g., "Sector North", "Omni 1"
    station_id = Column(Integer, ForeignKey("transmission_stations.id"), nullable=False)
    
    # Extended sector properties
    mac_address = Column(String, nullable=True)  # Sector device MAC
    device_model = Column(String, nullable=True)  # e.g., "Ubiquiti AirFiber 5XHD", "Cambium Force 300"
    horn_orientation = Column(String, nullable=True)  # e.g., "30", "60", "90", "120" degrees
    ip_type = Column(String, default="dhcp")  # dhcp, static, pppoe
    ip_address = Column(String, nullable=True)  # Static IP if ip_type=static
    netmask = Column(String, nullable=True)  # Netmask if ip_type=static

    station = relationship("TransmissionStation", back_populates="sectors")
    devices = relationship("Device", back_populates="sector")

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    company_email = Column(String, nullable=False, unique=True)
    location = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    auth_users = relationship("AuthUser", back_populates="company")
    users = relationship("User", back_populates="company")
    clients = relationship("Client", back_populates="company")
    devices = relationship("Device", back_populates="company")
    stations = relationship("TransmissionStation", back_populates="company", cascade="all, delete-orphan")
    defaults = relationship("CompanyDefaults", uselist=False, back_populates="company", cascade="all, delete-orphan")
    templates = relationship("DeviceTypeTemplate", back_populates="company", cascade="all, delete-orphan")

class Device(Base):
    __tablename__ = "devices"

    device_id = Column(String, primary_key=True, index=True)
    mac_address = Column(String, unique=True, index=True, nullable=False)  # physical identifier
    name = Column(String, nullable=True, index=True)  # e.g. "Router 1"
    description = Column(String, nullable=True)  # Optional description 
    ip_address= Column(String, nullable=True)
    ip_type = Column(String, default="dhcp")  # dhcp, static, pppoe
    netmask = Column(String, nullable=True)  # Netmask if ip_type=static
    pppoe_username = Column(String, nullable=True)  # PPPoE username
    pppoe_password = Column(String, nullable=True)  # PPPoE password
    model = Column(String, nullable=True)
    device_type = Column(String, nullable=True)    # e.g., 'router', 'ap', 'switch', 'bridge', 'gateway'
    ssid = Column(String, nullable=True)           # wifi SSID advertised by device (if applicable)
    status = Column(String, default="offline")
    firmware_version = Column(String, default="1.0.0")
    snr = Column(Integer, nullable=True)           # Signal-to-Noise Ratio for wireless devices
    credentials = Column(JSON, nullable=True)  # stores username/pass or token
    created_at = Column(DateTime, default=datetime.utcnow)

    # Client relationship (one device belongs to one client)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    
    # WISP Hierarchy fields
    sector_id = Column(Integer, ForeignKey("sectors.id"), nullable=True)
    station_id = Column(Integer, ForeignKey("transmission_stations.id"), nullable=True)
    parent_device_id = Column(String, ForeignKey("devices.device_id"), nullable=True)

    sector = relationship("Sector", back_populates="devices")
    station = relationship("TransmissionStation", back_populates="devices", foreign_keys=[station_id])
    company = relationship("Company", back_populates="devices")
    client = relationship("Client", back_populates="devices")

    # Tracking fields
    last_seen = Column(DateTime, nullable=True)       # last successful contact
    uptime = Column(Integer, nullable=True)           # seconds reported by device (None if unknown)
    last_config_hash = Column(String, nullable=True)  # hash of last known config
    needs_restore = Column(Integer, default=0)       # flag 0/1 marking suspected reset

    backups = relationship("Backup", back_populates="device", cascade="all, delete")

    def __repr__(self):
        return f"<Device {self.device_id} mac={self.mac_address} ip={self.ip_address}>"

class CompanyDefaults(Base):
    __tablename__ = "company_defaults"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), unique=True, nullable=False)
    dns_primary = Column(String, nullable=True)
    dns_secondary = Column(String, nullable=True)
    ntp_server = Column(String, nullable=True)
    syslog_server = Column(String, nullable=True)
    snmp_community = Column(String, nullable=True)
    admin_username = Column(String, nullable=True)
    enable_password = Column(String, nullable=True) # Encrypted placeholder
    domain_name = Column(String, nullable=True)
    management_acl = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", back_populates="defaults")

class DeviceTypeTemplate(Base):
    __tablename__ = "device_type_templates"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    device_type = Column(String, nullable=False) # router, switch, wireless, firewall
    template_name = Column(String, nullable=True)
    config_content = Column(String, nullable=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="templates")

class User(Base):
    __tablename__ = "techies"

    id = Column(Integer, primary_key=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    alias = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)

    role = Column(String, default="tech_support")  # admin / tech_support

    company_id = Column(Integer, ForeignKey("companies.id"))
    company = relationship("Company", back_populates="users")

    created_at = Column(DateTime, default=datetime.utcnow)

# class User(Base):
#     __tablename__ = "users"
#     id = Column(Integer, primary_key=True)
#     username = Column(String(50), unique=True, nullable=False, index=True)
#     email = Column(String(120), unique=True, nullable=True)
#     password_hash = Column(String(255), nullable=False)
#     role = Column(String(20), default="technician")  # 'admin' or 'technician'
#     is_active = Column(Boolean, default=True)
#     created_at = Column(DateTime, default=datetime.utcnow)

#     # Capability toggles (admin can set these per user)
#     can_add_device = Column(Boolean, default=True)
#     can_delete_device = Column(Boolean, default=False)
#     can_restart_device = Column(Boolean, default=False)
#     can_configure_device = Column(Boolean, default=True)
#     __table_args__ = {'extend_existing': True}

    def as_dict(self, include_sensitive: bool = False):
        """Return serializable form (omit password_hash by default)."""
        data = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "can_add_device": bool(self.can_add_device),
            "can_delete_device": bool(self.can_delete_device),
            "can_restart_device": bool(self.can_restart_device),
            "can_configure_device": bool(self.can_configure_device),
        }
        if include_sensitive:
            data["password_hash"] = self.password_hash
        return data

# ✅ Interfaces
class NetworkInterface(Base):
    __tablename__ = "interfaces"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, ForeignKey("devices.device_id"))
    name = Column(String)
    ip = Column(String, nullable = False) # "eth0", "wan", "br-lan.10"
    mac_address = Column(String, nullable=True, index=True)
    description = Column(String, nullable=True)
    ip_address = Column(String, nullable=True) # primary IPv4
    ipv6_address = Column(String, nullable=True)# one canonical IPv6 (use an addresses table if multiple)
    netmask = Column(String)
    # operational / capability
    mtu = Column(Integer, nullable=True)
    speed = Column(Integer, nullable=True)  # link speed in Mbps
    duplex = Column(String, nullable=True)  # "full"/"half"/None
    admin_state = Column(String, nullable=True)# configured state: "up"/"down"
    oper_state = Column(String, nullable=True) # actual state: "up"/"down"/"unknown"

    # counters and telemetry
    rx_bytes = Column(Integer, default=0)
    tx_bytes = Column(Integer, default=0)
    rx_packets = Column(Integer, default=0)
    tx_packets = Column(Integer, default=0)
    rx_errors = Column(Integer, default=0)
    tx_errors = Column(Integer, default=0)

    # vlan / neighbor / snapshots
    vlan = Column(String, nullable=True)
    neighbors = Column(JSON, nullable=True)# LLDP/CDP neighbor info
    config_snapshot = Column(JSON, nullable=True) # last reported interface config

    # tracking
    last_change = Column(DateTime, nullable=True) # timestamp of last state change
    last_seen = Column(DateTime, nullable=True) # last poll time

    def as_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "name": self.name,
            "mac_address": self.mac_address,
            "description": self.description,
            "ip_address": self.ip_address,
            "netmask": self.netmask,
            "ipv6_address": self.ipv6_address,
            "mtu": self.mtu,
            "speed": self.speed,
            "duplex": self.duplex,
            "admin_state": self.admin_state,
            "oper_state": self.oper_state,
            "rx_bytes": self.rx_bytes,
            "tx_bytes": self.tx_bytes,
            "rx_packets": self.rx_packets,
            "tx_packets": self.tx_packets,
            "rx_errors": self.rx_errors,
            "tx_errors": self.tx_errors,
            "vlan": self.vlan,
            "neighbors": self.neighbors,
            "config_snapshot": self.config_snapshot,
            "last_change": self.last_change.isoformat() if self.last_change else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }

# Schema for adding a router
class RouterCreate(BaseModel):
    name: str
    ip_address: str
    vendor: str = "dlink"
    username: str
    password: str

# ✅ Routing Table
class RoutingTable(Base):
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, ForeignKey("devices.device_id"))
    destination = Column(String)
    gateway = Column(String)
    metric = Column(Integer)

# ✅ Config change history
class ConfigHistory(Base):
    __tablename__ = "config_history"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, ForeignKey("devices.device_id"))
    note = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    config_snapshot = Column(JSON)

# ✅ Firewall rules
class FirewallRule(Base):
    __tablename__ = "firewall_rules"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, ForeignKey("devices.device_id"))
    rule_type = Column(String)  # 'allow' or 'deny'
    port = Column(Integer)
    protocol = Column(String)  # TCP/UDP
    desc = Column(String)

# Backup archive
class Backup(Base):
    __tablename__ = "backups"

    backup_id = Column(String, primary_key=True, index=True)
    device_id = Column(String, ForeignKey("devices.device_id"), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    note = Column(String, nullable=True)
    config_json = Column(String, nullable=False)
    device = relationship("Device", back_populates="backups")
# Events/alerts logs (enhanced)
class EventLog(Base):
    __tablename__ = "event_logs"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    device_id = Column(String, ForeignKey("devices.device_id"), nullable=True)
    username = Column(String, nullable=True)                    # user who triggered the event
    activity_type = Column(String, nullable=True)               # e.g., "device_created", "device_reset", "user_login", "config_deployed", "device_discovered"
    message = Column(String)
    severity = Column(String, default="INFO")                   # INFO/NOTICE/WARNING/ALERT/CRITICAL
    details = Column(JSON, nullable=True)                       # arbitrary payload (device count, reset reason, etc.)
    timestamp = Column(DateTime, default=datetime.utcnow)
    ts = Column(DateTime, default=datetime.utcnow)              # alias for compatibility

# Audit trail for user actions (who did what)
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)           # optional FK to users.id if you have it
    username = Column(String, nullable=True)           # store the username performing the action
    action = Column(String, nullable=False)            # e.g., "create_device", "deploy_config"
    target_type = Column(String, nullable=True)        # e.g., "device", "config"
    target_id = Column(String, nullable=True)          # e.g., device_id
    details = Column(JSON, nullable=True)              # arbitrary JSON payload/details
    timestamp = Column(DateTime, default=datetime.utcnow)

# DHCP lease assignments
class DHCPLease(Base):
    __tablename__ = "dhcp_leases"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, ForeignKey("devices.device_id"))
    client_mac = Column(String)
    client_ip = Column(String)
    lease_start = Column(DateTime)
    lease_end = Column(DateTime)

# ✅ DHCP configuration options
class DHCPConfig(Base):
    __tablename__ = "dhcp_configs"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, ForeignKey("devices.device_id"))
    enabled = Column(Boolean, default=True)
    range_start = Column(String)
    range_end = Column(String)
    dns_server = Column(String, nullable=True)
    lease_time = Column(Integer, default=86400)

class DeviceCreate(BaseModel):
    device_id: str = Field(..., example="router-001")
    mac_address: str
    ip_address: Optional[str] = None
    model: Optional[str] = Field(None, example="Ruijie")
    device_type: Optional[str] = Field(None, example="router")
    ssid: Optional[str] = Field(None, example="MyWiFi")
    status: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = Field(default_factory=dict)
    client_id: Optional[int] = None
    sector_id: Optional[int] = None
    parent_device_id: Optional[str] = None

    @validator('parent_device_id', 'client_id', 'sector_id', pre=True)
    def empty_string_to_none(cls, v):
        if isinstance(v, str) and v.strip() == '':
            return None
        return v

class CompanyDefaultsSchema(BaseModel):
    dns_primary: Optional[str] = None
    dns_secondary: Optional[str] = None
    ntp_server: Optional[str] = None
    syslog_server: Optional[str] = None
    snmp_community: Optional[str] = None
    admin_username: Optional[str] = None
    enable_password: Optional[str] = None
    domain_name: Optional[str] = None
    management_acl: Optional[str] = None

    class Config:
        from_attributes = True

class DeviceTemplateSchema(BaseModel):
    device_type: str
    template_name: Optional[str] = None
    config_content: str
    is_default: bool = False

    class Config:
        from_attributes = True

class Router(Base):
    __tablename__ = "routers"

    device_id = Column(String, primary_key=True, index=True)  # Unique device identifier (e.g., router-001)
    ip_address = Column(String, nullable=True)  # Supports DHCP or static assignment
    model = Column(String, nullable=True)
    status = Column(String, default="offline")  # online / offline / unknown
    credentials = Column(JSON, nullable=True)  # Optional login info or PPPoE config
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Router {self.device_id} ({self.ip})>"

class BackupCreate(BaseModel):
    note: Optional[str] = None

class DeviceUpdate(BaseModel):
    ip: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None

class DHCPRequestIn(BaseModel):
    client_mac: str
    client_hostname: Optional[str] = None
    requested_ip: Optional[str] = None

class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    alias = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)

    company_id = Column(Integer, ForeignKey("companies.id"))
    role = Column(String, default="tech_support")

    created_at = Column(DateTime, default=datetime.utcnow)


# class Invitation(Base):
#     __tablename__ = "invitations"

#     token = Column(String, primary_key=True, index=True)
#     username = Column(String, unique=True)
#     role = Column(String)
#     used = Column(Boolean, default=False)
#     created_at = Column(DateTime, default=datetime.utcnow)

class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    location = Column(String, nullable=True)  # e.g., "123 Main St, City, State"
    contact_info = Column(String, nullable=True)  # phone/email
    created_at = Column(DateTime, default=datetime.utcnow)

    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    company = relationship("Company", back_populates="clients")
    # Relationship to devices (one client can have many devices)
    devices = relationship("Device", back_populates="client", cascade="all, delete")

    def as_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "contact_info": self.contact_info,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
