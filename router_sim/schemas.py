# auth/schemas.py
from pydantic import BaseModel, Field, EmailStr, validator
from typing import Optional, Dict, Any
from datetime import datetime

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    email: Optional[EmailStr] = None
    role: Optional[str] = Field("technician")
    # Optional initial capability flags (admin may set these on creation)
    can_add_device: Optional[bool] = True
    can_delete_device: Optional[bool] = False
    can_restart_device: Optional[bool] = False
    can_configure_device: Optional[bool] = True
    ui_theme: Optional[str] = "light"
    theme_accent: Optional[str] = "#0096FF"

    @validator("role")
    def validate_role(cls, v):
        if v not in ("admin", "technician"):
            raise ValueError("role must be 'admin' or 'technician'")
        return v

class UserLogin(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None
    can_add_device: Optional[bool] = None
    can_delete_device: Optional[bool] = None
    can_restart_device: Optional[bool] = None
    can_configure_device: Optional[bool] = None
    ui_theme: Optional[str] = None
    theme_accent: Optional[str] = None

    @validator("role")
    def validate_role(cls, v):
        if v is None: 
            return v
        if v not in ("admin", "technician"):
            raise ValueError("role must be 'admin' or 'technician'")
        return v

class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[EmailStr]
    role: str
    is_active: bool
    created_at: Optional[datetime]
    can_add_device: bool
    can_delete_device: bool
    can_restart_device: bool
    can_configure_device: bool
    ui_theme: str
    theme_accent: str

    class Config:
        from_attributes = True

class UserPermissionUpdate(BaseModel):
    can_add_device: Optional[bool] = None
    can_delete_device: Optional[bool] = None
    can_restart_device: Optional[bool] = None
    can_configure_device: Optional[bool] = None

class UserResponse(BaseModel):
    id: int
    is_active: bool
    created_at: Optional[datetime]

    class Config:
        from_attributes = True

class UserBase(BaseModel):
    username: str
    email: Optional[EmailStr]
    role: str

class InviteCreateSchema(BaseModel):
    username: str
    role: str

class InviteOut(BaseModel):
    username: str
    role: str
    token: str
    used: bool

    class Config:
        from_attributes = True

class ClientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    location: Optional[str] = Field(None, max_length=200)
    contact_info: Optional[str] = Field(None, max_length=200)

class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    location: Optional[str] = Field(None, max_length=200)
    contact_info: Optional[str] = Field(None, max_length=200)

class ClientOut(BaseModel):
    id: int
    name: str
    location: Optional[str]
    contact_info: Optional[str]
    created_at: Optional[datetime]
    device_count: Optional[int] = 0

    class Config:
        from_attributes = True

class DeviceCreate(BaseModel):
    device_id: str = Field(..., example="router-001")
    mac_address: str
    ip_address: Optional[str] = None
    model: Optional[str] = Field(None, example="Ruijie")
    device_type: Optional[str] = Field(None, example="router")
    ssid: Optional[str] = Field(None, example="MyWiFi")
    status: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = Field(default_factory=dict)
    client_id: Optional[int] = None  # Add client attachment during creation
    sector_id: Optional[int] = None
    parent_device_id: Optional[str] = None

    @validator('parent_device_id', pre=True)
    def empty_string_to_none(cls, v):
        if isinstance(v, str) and v == '':
            return None
        return v
