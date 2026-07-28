# router_schemas.py - defines Pydantic schemas for router models(data validation and serialization)

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


# ---------- DHCP ----------

class DHCPLeaseBase(BaseModel):
    ip_address: str
    mac_address: str
    lease_start: Optional[datetime] = None
    lease_end: Optional[datetime] = None
    active: Optional[bool] = True


class DHCPLeaseCreate(DHCPLeaseBase):
    pass


class DHCPLeaseResponse(DHCPLeaseBase):
    id: int

    class Config:
        from_attributes = True


# ---------- Firewall ----------

class FirewallRuleBase(BaseModel):
    rule_name: str
    action: str
    protocol: str
    port: str
    source: str
    destination: str


class FirewallRuleCreate(FirewallRuleBase):
    pass


class FirewallRuleResponse(FirewallRuleBase):
    id: int

    class Config:
        from_attributes = True


# ---------- Backups ----------

class RouterBackupBase(BaseModel):
    backup_data: dict
    note: Optional[str]


class RouterBackupResponse(RouterBackupBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


# ---------- Routers ----------

class RouterBase(BaseModel):
    device_id: str
    ip_address: str
    model: Optional[str] = "GenericRouter"
    status: Optional[str] = "online"
    ssid: Optional[str] = "DefaultSSID"
    wifi_password: Optional[str] = "changeme"
    hostname: Optional[str] = "router"
    config: Optional[dict]


class RouterCreate(RouterBase):
    pass


class RouterResponse(RouterBase):
    id: int
    created_at: datetime
    updated_at: datetime
    dhcp_leases: List[DHCPLeaseResponse] = []
    firewall_rules: List[FirewallRuleResponse] = []
    backups: List[RouterBackupResponse] = []

    class Config:
        from_attribtes = True
