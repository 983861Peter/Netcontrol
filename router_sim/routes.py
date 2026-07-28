# auth/routes.py
"""
Routes for auth: login, user management (admin-only), and helper dependencies.
Include this router in your main app with: app.include_router(auth_router)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Depends, WebSocket, WebSocketDisconnect, Query
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session, joinedload
from typing import Optional, Dict, Any, List
import asyncio
import logging
from datetime import timedelta, datetime
# import jose
# import jwt
from .db import get_db, SessionLocal  # ensure your db.py exposes get_db
from .models import User, AuthUser, Invitation, Client, Device, Company
from .rbac import require_role
from pydantic import BaseModel
from .db import get_db
from .schemas import UserCreate, UserLogin, UserUpdate, UserOut, InviteCreateSchema, InviteOut, ClientOut, ClientCreate, ClientUpdate
from .auth_utils import hash_password, verify_password, create_access_token, decode_access_token
import uuid
auth_router = APIRouter(prefix="/auth", tags=["Authentication"] )
logger = logging.getLogger("router_api")
connected_alert_ws: List[WebSocket] = []
router = APIRouter(prefix="", tags=["Clients"])
alerts_router = APIRouter()

@alerts_router.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    await ws.accept()
    connected_alert_ws.append(ws)
    try:
        while True:
            # keep connection open; the server will send events as they occur.
            await asyncio.sleep(60)
    except (WebSocketDisconnect, Exception):
        if ws in connected_alert_ws:
            connected_alert_ws.remove(ws)

# --- Dependencies & helpers --- #

def get_token_from_header(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization")
    if not auth:
        return None
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None

def get_current_user(request: Request, db: Session = Depends(get_db)) -> AuthUser:
    token = get_token_from_header(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    username = payload["sub"]
    user = db.query(AuthUser).options(joinedload(AuthUser.company)).filter(AuthUser.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user

def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privilege required")
    return current_user

async def broadcast_alert(payload: dict):
    to_remove = []
    for ws in connected_alert_ws:
        try:
            await ws.send_json(payload)
        except Exception:
            to_remove.append(ws)
    for ws in to_remove:
        if ws in connected_alert_ws:
            connected_alert_ws.remove(ws)

def log_activity(db: Session, activity_type: str, username: str | None = None, device_id: str | None = None, message: str = "", severity: str = "INFO", details: Dict[str, Any] | None = None, company_id: int | None = None):
    """
    Log a system activity (device created, reset, user action, etc).
    Automatically broadcasts to WebSocket clients.
    """
    from .models import EventLog

    final_company_id = company_id
    if not final_company_id and device_id:
        device = db.query(Device).filter(Device.device_id == device_id).first()
        if device:
            final_company_id = device.company_id

    try:
        ev = EventLog(
            activity_type=activity_type,
            username=username,
            device_id=device_id,
            message=message,
            severity=severity,
            details=details or {},
            company_id=final_company_id
        )
        db.add(ev)
        db.commit()
        # Broadcast to WebSocket clients
        asyncio.create_task(broadcast_alert({
            "id": ev.id,
            "activity_type": activity_type,
            "username": username,
            "device_id": device_id,
            "message": message,
            "severity": severity,
            "timestamp": ev.timestamp.isoformat()
        }))
    except Exception as e:
        logger.exception(f"log_activity error: {e}")
        db.rollback()

def log_user_login(db: Session, username: str):
    """Log user login."""
    user = db.query(AuthUser).filter(AuthUser.username == username).first()
    log_activity(db, "user_login", username=username, message=f"User {username} logged in", severity="NOTICE", details={"username": username}, company_id=user.company_id if user else None)

def log_user_logout(db: Session, username: str):
    """Log user logout."""
    user = db.query(AuthUser).filter(AuthUser.username == username).first()
    log_activity(db, "user_logout", username=username, message=f"User {username} logged out", severity="NOTICE", details={"username": username}, company_id=user.company_id if user else None)

# --- Public endpoints --- #


# verify_password_example.py
from .db import SessionLocal
from .models import AuthUser
from .auth_utils import verify_password  # or wherever verify_password is defined

db = SessionLocal()
username = "admin"                # target user
candidate = "AdminPass123!"       # plaintext to test

user = db.query(AuthUser).filter(AuthUser.username == username).first()
if not user:
    print("User not found")
else:
    ok = verify_password(candidate, user.password_hash)
    print("Password match?" , ok)

db.close()

ACCESS_TOKEN_EXPIRE_MINUTES = 60


# User Registration (Admin Only)
@auth_router.post("/register", response_model=UserOut)
def register_user(data: UserCreate, 
                    db: Session = Depends(get_db),
                    user=Depends(require_role("admin"))):

    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="User already exists")

    new_user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        role=data.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@auth_router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Authenticates user using username and password.
    Returns JWT access token if valid.
    """
    # ✅ Find user
    user = db.query(AuthUser).filter(AuthUser.username == form_data.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # ✅ Verify password hash
    if not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # ✅ Check active status
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account inactive")

    # ✅ Create JWT token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user.username,
        role=user.role,
        expires_delta=access_token_expires
    )
    log_user_login(db, user.username)  # Log successful login

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username
    }

@auth_router.post("/logout")
def logout(current_user = Depends(get_current_user)):
    db = SessionLocal()
    try:
        log_user_logout(db, current_user.username) # Log logout event
    finally:
        db.close()
    return {"message": "Logged out"}

@auth_router.get("/me")
def read_users_me(current_user: AuthUser = Depends(get_current_user)):
    """
    Get current user details.
    """
    return {
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "company_name": current_user.company.name if current_user.company else None,
        "phone_number": current_user.phone_number,
        "ui_theme": current_user.ui_theme,
    }

class CompanyRegister(BaseModel):
    company_name: str
    location: str
    username: str
    email: str
    password: str
    phone_number: Optional[str] = None

@auth_router.post("/register-company")
def register_company(data: CompanyRegister, db: Session = Depends(get_db)):
    # Check if company exists
    if db.query(Company).filter(Company.name == data.company_name).first():
        raise HTTPException(status_code=400, detail="Company with this name already exists")
    # Check if user exists
    if db.query(AuthUser).filter(AuthUser.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    
    # Create Company
    new_company = Company(
        name=data.company_name,
        company_email=data.email,
        location=data.location
    )
    db.add(new_company)
    db.commit()
    db.refresh(new_company)
    
    new_user = AuthUser(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
        role="admin",
        is_active=True,
        company_id=new_company.id,
        phone_number=data.phone_number
    )
    db.add(new_user)
    db.commit()
    log_activity(db, "company_registered", username=data.username, message=f"New company '{data.company_name}' registered by {data.username}", severity="NOTICE", company_id=new_company.id)
    
    return {"message": "Company and admin registered successfully"}

# @auth_router.post("/login")
# def login(data: UserLogin, db: Session = Depends(get_db)):
#     user = db.query(User).filter(User.username == data.username).first()
#     if not user or not verify_password(data.password, user.password_hash):
#         raise HTTPException(status_code=401, detail="Invalid username or password")
#     token = create_access_token(subject=user.username, role=user.role)
#     return {"access_token": token, "token_type": "bearer", "role": user.role}

# --- Admin-only user management --- #

@auth_router.post("/users", response_model=UserOut)
def create_user(user_in: UserCreate, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """
    Admin endpoint: create a user and set initial capability flags.
    Only accessible by users with role == 'admin'.
    """
    existing = db.query(User).filter(User.username == user_in.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    # Create
    u = User(
        username=user_in.username,
        email=user_in.email,
        password_hash=hash_password(user_in.password),
        role=user_in.role,
        can_add_device=bool(user_in.can_add_device),
        can_delete_device=bool(user_in.can_delete_device),
        can_restart_device=bool(user_in.can_restart_device),
        can_configure_device=bool(user_in.can_configure_device),
        is_active=True,
        company_id=current_admin.company_id
    )
    db.add(u); db.commit(); db.refresh(u)
    return u

@auth_router.get("/users", response_model=list[UserOut])
def list_users(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).filter(User.company_id == current_admin.company_id).order_by(User.created_at.desc()).all()
    return users

@auth_router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id, User.company_id == current_admin.company_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return u

@auth_router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, patch: UserUpdate, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id, User.company_id == current_admin.company_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    # apply partial updates
    update_data = patch.dict(exclude_unset=True)
    for k, v in update_data.items():
        setattr(u, k, v)
    db.add(u); db.commit(); db.refresh(u)
    return u

@auth_router.delete("/users/{user_id}")
def delete_user(user_id: int, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id, User.company_id == current_admin.company_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(u); db.commit()
    return {"message": f"user {user_id} deleted"}

class InviteRequest(BaseModel):
    full_name: str
    alias: str
    email: str
    phone: Optional[str] = None
    role: str

@auth_router.post("/invite", response_model=InviteOut)
def create_invitation(data: InviteRequest,
                        db: Session = Depends(get_db),
                        current_user: AuthUser = Depends(get_current_user)):
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can invite users")

    token = uuid.uuid4().hex

    inv = Invitation(
        token=token,
        full_name=data.full_name,
        alias=data.alias,
        email=data.email,
        phone_number=data.phone,
        role=data.role,
        company_id=current_user.company_id
    )

    db.add(inv)
    db.commit()
    # Return a shape matching InviteOut or just the token/url
    return InviteOut(token=token, username=data.alias, role=data.role, used=False)

class RegistrationRequest(BaseModel):
    token: str
    password: str

@auth_router.post("/complete-registration")
def complete_registration(data: RegistrationRequest, db: Session = Depends(get_db)):
    inv = db.query(Invitation).filter(Invitation.token == data.token).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invalid or expired invitation token")
    
    # Create the user
    new_user = AuthUser(
        username=inv.alias,
        email=inv.email,
        password_hash=hash_password(data.password),
        role=inv.role,
        company_id=inv.company_id,
        phone_number=inv.phone_number,
        is_active=True
    )
    db.add(new_user)
    db.delete(inv) # Consume invitation
    db.commit()
    return {"message": "Registration successful"}

# Client management routes
@router.get("/clients", response_model=list[ClientOut])
def list_clients(db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    if not current_user.company_id:
        return []
    clients = db.query(Client).options(joinedload(Client.devices)).filter(Client.company_id == current_user.company_id).order_by(Client.created_at.desc()).all()
    # Return ClientOut objects with device count
    client_outs = []
    for client in clients:
        client_outs.append(ClientOut(
            id=client.id,
            name=client.name,
            location=client.location,
            contact_info=client.contact_info,
            created_at=client.created_at,
            device_count=len(client.devices)
        ))
    return client_outs

@router.post("/clients", response_model=ClientOut)
def create_client(client: ClientCreate, db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    if not current_user.company_id:
        raise HTTPException(status_code=403, detail="User not associated with a company")
    new_client = Client(**client.dict(), company_id=current_user.company_id)
    db.add(new_client)
    db.commit()
    db.refresh(new_client)
    return ClientOut(
        id=new_client.id,
        name=new_client.name,
        location=new_client.location,
        contact_info=new_client.contact_info,
        created_at=new_client.created_at,
        device_count=0
    )

@router.get("/clients/{client_id}", response_model=ClientOut)
def get_client(client_id: int, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client

@router.put("/clients/{client_id}", response_model=ClientOut)
def update_client(client_id: int, client_update: ClientUpdate, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    update_data = client_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(client, key, value)
    
    db.commit()
    db.refresh(client)
    return client

@router.delete("/clients/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Check if client has attached devices
    if client.devices:
        raise HTTPException(status_code=400, detail="Cannot delete client with attached devices. Detach devices first.")
    
    db.delete(client)
    db.commit()
    return {"message": "Client deleted"}

@router.get("/clients/{client_id}/devices", response_model=list[dict])
def get_client_devices(client_id: int, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    return [device.as_dict() for device in client.devices]

# Device attachment routes
@router.post("/devices/{device_id}/attach-client")
def attach_device_to_client(device_id: str, client_id: int, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Check if device is already attached to another client
    if device.client_id and device.client_id != client_id:
        raise HTTPException(status_code=400, detail="Device is already attached to another client")
    
    device.client_id = client_id
    db.commit()
    return {"message": "Device attached to client"}

@router.post("/devices/{device_id}/detach-client")
def detach_device_from_client(device_id: str, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    device.client_id = None
    db.commit()
    return {"message": "Device detached from client"}
