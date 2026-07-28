# router_api.py

import time
from fastapi import (
    FastAPI, HTTPException, Depends, status, BackgroundTasks,
    Query, Request, WebSocket, WebSocketDisconnect,APIRouter)
from flask import Flask, request, jsonify
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi.responses import StreamingResponse, RedirectResponse
import csv
from io import StringIO
import random
import uuid
import json
import ipaddress
import asyncio
import os
import re
import logging
import importlib
import subprocess
import platform
from .dlink_adapter import DLinkAdapter
from .routes import get_current_user, auth_router, log_user_logout, log_user_login, log_activity, router, alerts_router
from .models import AuthUser, Device, NetworkInterface, RoutingTable, ConfigHistory, FirewallRule, Backup, EventLog, DHCPLease, DHCPConfig, Router,DeviceCreate, BackupCreate,DeviceUpdate, DHCPRequestIn, RouterCreate, AuditLog, Client, CompanyDefaults, DeviceTypeTemplate, CompanyDefaultsSchema, DeviceTemplateSchema, TransmissionStation, Sector
from .auth_utils import hash_password,verify_password
from .adapter_loader import get_vendor_adapter
from .db import SessionLocal, engine, Base
from .admin_routes import user_router
from .router_schemas import RouterResponse
from .reset_detector import evaluate_device_reset 
from .ws_broadcast import register, unregister, broadcast_ws_event
from .poller import monitoring_loop, vendor_poll_device
from .router_backup import router as backup_router
from .scanner import scan_with_defaults
from sqlalchemy import (
    create_engine, Column, String, Integer, DateTime, Text, ForeignKey, Boolean, func)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session, joinedload

# Trying to import optional discovery/sync modules; if not present,the fallback is mocks.
try:
    from .discovery_engine import scan_network as discovery_scan_network
except Exception:
    discovery_scan_network = None

WS_POLL_INTERVAL = 5.0  
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("router_api")

# Global state for simulated cumulative network traffic (Gb)
SIMULATED_TRAFFIC_STATE = {
    "total_data_gb": 20.0,
    "last_update": time.time()
}

#           FastAPI app setup 
app = FastAPI(title="NetControl Router API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],# allow_origin_regex="https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for UI
ui_dir = Path(__file__).resolve().parent / "ui"
if ui_dir.exists():
    app.mount("/static", StaticFiles(directory=ui_dir), name="static")
    app.mount("/router_sim/ui", StaticFiles(directory=ui_dir), name="legacy_ui")
    logger.info("Mounted ui static at /static -> %s", ui_dir)
    logger.info("Mounted ui static at /router_sim/ui -> %s", ui_dir)
routers_router = APIRouter(prefix="/routers", tags=["Routers"])
#    Default admin setup on startup 


DEFAULT_ADMIN = {
    "username": os.getenv("NC_ADMIN_USER", "admin"),
    "password": os.getenv("NC_ADMIN_PASS", "admin@123"), 
    "email": os.getenv("NC_ADMIN_EMAIL", "admin@example.com")
}

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(monitoring_loop())
    init_system_settings()

def init_system_settings():
    """Ensures a bright, light blue theme is configured by default for high contrast."""
    if not os.path.exists(SETTINGS_FILE):
        default_settings = {
            "app_name": "NetControl",
            "branding": {
                "primary_color": "#0096FF",  # Bright Light Blue
                "background_color": "#F0F7FF",
                "surface_color": "#FFFFFF",
                "text_primary": "#1A2B44",
                "contrast_mode": "high"
            },
            "ui_defaults": {
                "theme": "light",
                "sidebar_bright": True
            }
        }
        with open(SETTINGS_FILE, "w") as f:
            json.dump(default_settings, f, indent=2)
        logger.info("Initialized system_settings.json with Light Blue theme.")

@app.on_event("startup")
def ensure_admin_user():
    """
    Ensures there is at least one administrator in the system.
    Creates a default admin account if none exists.
    """
    db = SessionLocal()
    try:
        existing = db.query(AuthUser).filter(
            AuthUser.username == DEFAULT_ADMIN["username"]
        ).first()

        if not existing:
            admin = AuthUser(
                username=DEFAULT_ADMIN["username"],
                email=DEFAULT_ADMIN["email"],
                password_hash=hash_password(DEFAULT_ADMIN["password"]),
                role="admin",
                is_active=True,
                can_add_device=True,
                can_delete_device=True,
                can_restart_device=True,
                can_configure_device=True,
            )
            db.add(admin)
            db.commit()
            print(f"[startup] ✅ Default admin user created: {DEFAULT_ADMIN['username']}")
        else:
            print(f"[startup] ℹ️ Admin user already exists: {DEFAULT_ADMIN['username']}")

    except Exception as e:
        print("[startup] ❌ Error ensuring admin user:", e)
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class RouterConfig(BaseModel):
    router_id: int
    ssid: str
    password: str

#  Dlink router apply config endpoint
def get_adapter(vendor_name, host, username, password):
    """
    Dynamically load a vendor-specific adapter.
    """
    try:
        if vendor_name.lower() == "dlink":
            return DLinkAdapter(host=host, username=username, password=password)
        else:
            module_name = f"adapters.{vendor_name.lower()}_adapter"
            vendor_module = importlib.import_module(module_name)
            adapter_class = getattr(vendor_module, f"{vendor_name.capitalize()}Adapter")
            return adapter_class(host=host, username=username, password=password)
    except Exception as e:
        print(f"[AdapterLoader] Could not load {vendor_name}: {e}")
        return None
#   Utility helpers
def log_event_db(db: Session, message: str, device_id: Optional[str] = None, level: str = "info", source: str = "api"):
    ev = EventLog(device_id=device_id, message=message, level=level, source=source)
    db.add(ev)
    db.commit()


def log_device_discovered(db: Session, device_count: int, subnet: str = ""):
    """Log discovery scan results."""
    log_activity(db, "device_discovered", message=f"Scan found {device_count} device(s) in {subnet}", severity="NOTICE", details={"count": device_count, "subnet": subnet})

def log_device_reset(db: Session, device_id: str, reason: str = ""):
    """Log device factory reset."""
    log_activity(db, "device_reset", device_id=device_id, message=f"Device {device_id} was factory reset{': ' + reason if reason else ''}", severity="WARNING", details={"device_id": device_id, "reason": reason})

def log_config_deployed(db: Session, username: str | None, device_ids: list, fragment: dict):
    """Log mass config deployment."""
    log_activity(db, "config_deployed", username=username, message=f"Config deployed to {len(device_ids)} device(s)", severity="NOTICE", details={"devices": device_ids, "fragment_keys": list(fragment.keys()), "username": username})

def log_backup_created(db: Session, device_id: str, backup_id: str):
    """Log backup created."""
    log_activity(db, "backup_created", device_id=device_id, message=f"Backup {backup_id} created for {device_id}", severity="INFO", details={"device_id": device_id, "backup_id": backup_id})
    
def log_audit_db(db: Session, username: str | None, action: str, target_type: str | None = None, target_id: str | None = None, details: Dict[str, Any] | None = None):
    """
    Write an audit record. Caller should provide open db session.
    """
    try:
        a = AuditLog(username=username, action=action, target_type=target_type, target_id=target_id, details=details or {})
        db.add(a)
        db.commit()
    except Exception:
        db.rollback()

def _apply_config_to_device(db: Session, device_id: str, fragment: dict, username: str | None = None):
    """Internal helper: persist ConfigHistory, update Device.last_config_hash, and log event."""
    try:
        # create config history
        ch = ConfigHistory(device_id=device_id, note="mass_deploy", config_snapshot=fragment)
        db.add(ch)
        # optionally compute hash (left simple)
        # mark device updated
        d = db.query(Device).filter(Device.device_id == device_id).first()
        if d:
            d.last_config_hash = str(hash(json.dumps(fragment, sort_keys=True)))
            db.add(d)
        db.commit()
        # record event
        log_event_db(db, f"Mass deploy applied to {device_id}", device_id=device_id)
    except Exception:
        db.rollback()


def read_credentials_field(obj: Device) -> Dict[str, Any]:
    if not obj.credentials:
        return {}
    try:
        return json.loads(obj.credentials)
    except Exception:
        return {}


def write_credentials_field(data: Dict[str, Any]) -> str:
    try:
        return json.dumps(data)
    except Exception:
        return "{}"


# IP helpers for DHCP
def ip_to_int(ipstr: str) -> int:
    return int(ipaddress.ip_address(ipstr))


def int_to_ip(i: int) -> str:
    return str(ipaddress.ip_address(i))


def iterate_ip_range(start: str, end: str):
    a = ip_to_int(start)
    b = ip_to_int(end)
    for i in range(a, b + 1):
        yield int_to_ip(i)


def get_dhcp_config_or_default(db: Session, device_id: str) -> DHCPConfig:
    cfg = db.query(DHCPConfig).filter(DHCPConfig.device_id == device_id).first()
    if cfg:
        return cfg
    # Try to infer from latest config (ConfigHistory)
    latest = db.query(ConfigHistory).filter(ConfigHistory.device_id == device_id).order_by(ConfigHistory.timestamp.desc()).first()
    if latest:
        try:
            conf = json.loads(latest.config_json)
            dhcp = conf.get("dhcp", {})
            if dhcp and "range_start" in dhcp and "range_end" in dhcp:
                cfg = DHCPConfig(
                    device_id=device_id,
                    range_start=dhcp.get("range_start"),
                    range_end=dhcp.get("range_end"),
                    lease_time=dhcp.get("lease_time", 86400),
                    enabled=dhcp.get("enabled", True)
                )
                db.add(cfg)
                db.commit()
                return cfg
        except Exception:
            pass
    # fallback default pool based on device ip if present
    dev = db.query(Device).filter(Device.device_id == device_id).first()
    if dev and dev.ip_address:
        try:
            base_net = ipaddress.ip_network(dev.ip_address + "/24", strict=False)
            hosts = list(base_net.hosts())
            start = str(hosts[99]) if len(hosts) > 100 else "192.168.1.100"
            end = str(hosts[149]) if len(hosts) > 150 else "192.168.1.200"
            cfg = DHCPConfig(device_id=device_id, range_start=start, range_end=end, lease_time=86400, enabled=True)
            db.add(cfg); db.commit(); return cfg
        except Exception:
            pass
    # final fallback
    cfg = DHCPConfig(device_id=device_id, range_start="192.168.1.100", range_end="192.168.1.200", lease_time=86400, enabled=True)
    db.add(cfg); db.commit(); return cfg


def find_next_free_ip(db: Session, cfg: DHCPConfig) -> Optional[str]:
    used = {l.ip_address for l in db.query(DHCPLease).filter(DHCPLease.device_id == cfg.device_id).all()}
    for ip in iterate_ip_range(cfg.range_start, cfg.range_end):
        if ip not in used:
            return ip
    return None


# Helper function for recursive status updates
def _update_child_status_recursively(db: Session, parent_device_id: str, new_status: str):
    children = db.query(Device).filter(Device.parent_device_id == parent_device_id).all()
    for child in children:
        if child.status != new_status: # Only update if status is actually changing
            child.status = new_status
            db.add(child)
            _update_child_status_recursively(db, child.device_id, new_status) # Recurse

def perform_auto_backup(db: Session, device_id: str, note: str = "Auto-backup"):
    """
    Generates a full backup of the device credentials and config.
    Discards previous backups for this device to ensure only the latest exists.
    """
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        return

    # 1. Gather Metadata & Credentials
    client_info = None
    if device.client:
        client_info = {"id": device.client.id, "name": device.client.name}
    
    station_info = None
    if device.station:
        station_info = {"id": device.station.id, "name": device.station.name}

    creds = read_credentials_field(device)
    
    # Heuristic for connection type
    conn_type = "DHCP"
    if creds and (creds.get("user") or creds.get("username")):
        conn_type = "PPPoE"
    elif device.ip_address:
        conn_type = "Static"

    # 2. Get latest config snapshot (if any) to merge
    latest_hist = db.query(ConfigHistory).filter(ConfigHistory.device_id == device_id).order_by(ConfigHistory.timestamp.desc()).first()
    config_data = latest_hist.config_snapshot if (latest_hist and latest_hist.config_snapshot) else {}
    if isinstance(config_data, str): # Safety check if stored as string
        try: config_data = json.loads(config_data)
        except: config_data = {}

    # 3. Construct Full Backup Payload
    backup_payload = config_data.copy()
    backup_payload.update({
        "device_id": device.device_id,
        "name": device.name,
        "ip_address": device.ip_address,
        "mac_address": device.mac_address,
        "client": client_info,
        "station": station_info,
        "device_type": device.device_type,
        "firmware_version": device.firmware_version,
        "station_id": device.station_id,
        "sector_id": device.sector_id,
        "parent_device_id": device.parent_device_id,
        "last_config_hash": device.last_config_hash,
        "last_successful_config_at": latest_hist.timestamp.isoformat() if latest_hist else None,
        "connection_type": conn_type,
        "credentials": creds,
        "ssid": device.ssid,
        "model": device.model,
        "backup_created_at": datetime.utcnow().isoformat()
    })

    # 4. Discard Old Backups & Save New
    db.query(Backup).filter(Backup.device_id == device_id).delete()
    
    new_backup = Backup(
        backup_id=str(uuid.uuid4()),
        device_id=device_id,
        note=note,
        config_json=json.dumps(backup_payload)
    )
    db.add(new_backup)
    db.commit()
    
    # 5. Log Event
    log_activity(db, "backup_created", device_id=device_id, message=f"Auto-backup updated for {device.name or device_id}", severity="INFO")

# WebSocket endpoint
@app.websocket("/ws/monitor")
async def ws_monitor(websocket: WebSocket):
    """
    WebSocket endpoint for real-time monitoring.
    Sends periodic updates (device list + basic status) to each connected client.
    """
    await websocket.accept()
    await register(websocket)
    try:
        while True:
            # gather latest device snapshot
            db: Session = get_db()
            try:
                devs = db.query(Device).all()
                payload = []
                for d in devs:
                    # build status_info; adapt fields to your Device model
                    # uptime / clients / last_seen may not exist — handle gracefully
                    # clients: count DHCP leases assigned (if table exists)
                    try:
                        clients_count = db.query(DHCPLease).filter(DHCPLease.device_id == d.device_id).count()
                    except Exception:
                        clients_count = None

                    status_info = {
                        "uptime": getattr(d, "uptime", None),
                        "clients": clients_count,
                        "last_seen": getattr(d, "last_seen", None)
                    }
                    payload.append({
                        "device_id": d.device_id,
                        "name": getattr(d, "name", None),
                        "ip_address": getattr(d, "ip_address", getattr(d, "ip", None)),
                        "model": getattr(d, "model", None),
                        "status": getattr(d, "status", None),
                        "status_info": status_info
                    })
            finally:
                db.close()

            # send to client
            await websocket.send_text(json.dumps({"type": "devices_snapshot", "ts": datetime.utcnow().isoformat(), "devices": payload}))

            # wait, but handle cancellation cleanly
            try:
                await asyncio.sleep(WS_POLL_INTERVAL)
            except asyncio.CancelledError:
                break

    except WebSocketDisconnect:
        # client disconnected normally
        print("WebSocket client disconnected (ws/monitor)")
    except asyncio.CancelledError:
        # server shutdown
        print("WebSocket monitor cancelled (server shutdown)")
    except Exception as exc:
        print("WebSocket monitor error:", exc)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
        await unregister(websocket)

#     Routers / Devices endpoints (UI expects /routers) 
#     ROUTER ENDPOINT: Add New Router
router_api = APIRouter(prefix="/routers", tags=["Routers"])

@router_api.post("/add", status_code=201)
async def add_router(router_data: RouterCreate, db: Session = Depends(get_db)):
    """
    Add a new router to the database.
    Automatically checks if IP or name already exists.
    """
    existing_router = db.query(Router).filter(Router.ip_address == router_data.ip_address).first()
    if existing_router:
        raise HTTPException(status_code=400, detail="Router with this IP already exists")

    new_router = Router(
        name=router_data.name,
        ip_address=router_data.ip_address,
        vendor=router_data.vendor,
        username=router_data.username,
        password=router_data.password,
        status="online"
    )
    db.add(new_router)
    db.commit()
    db.refresh(new_router)

    return {
        "status": "success",
        "message": f"Router '{new_router.name}' added successfully.",
        "router": {
            "id": new_router.id,
            "ip_address": new_router.ip_address,
            "vendor": new_router.vendor,
            "status": new_router.status
        }
    }

#   ROUTER ENDPOINT: List Routers
@router_api.get("/list")
async def list_routers(db: Session = Depends(get_db)):
    """
    Retrieve all routers currently registered in the system.
    Returns essential data for dashboard rendering.
    """
    routers = db.query(Router).all()
    if not routers:
        return {"status": "empty", "message": "No routers found in the database."}

    return {
        "status": "success",
        "count": len(routers),
        "routers": [
            {
                "id": r.id,
                "name": r.name,
                "ip_address": r.ip_address,
                "vendor": r.vendor,
                "status": r.status,
                "last_seen": r.last_seen.isoformat() if r.last_seen else None
            }
            for r in routers
        ]
    }


@app.get("/routers", summary="List routers (alias for devices list)")
def routers_list(db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    if not current_user.company_id:
        return []
    devs = db.query(Device).filter(Device.company_id == current_user.company_id).all()
    out = []
    for d in devs:
        out.append({
            "device_id": d.device_id,
            "ip": d.ip_address,
            "model": d.model,
            "status": d.status,
            "credentials": read_credentials_field(d),
            "created_at": d.created_at.isoformat() if d.created_at else None
        })
    return out

@app.get("/routers")
def get_all_routers(db: Session = Depends(get_db)):
    routers = db.query(Device).all()
    return routers


@app.get("/routers", response_model=List[RouterResponse])
def routers_create(payload: DeviceCreate, db: Session = Depends(get_db)):
    routers = db.query(Router).all()
    return routers

@routers_router.post("/", status_code=201)
def add_router(device: dict, db: Session = Depends(get_db)):
    try:
        new_device = Device(
            device_id=device.get("device_id"),
            ip=device.get("ip"),
            model=device.get("model", "Unknown"),
            status=device.get("status", "Offline"),
        )
        db.add(new_device)
        db.commit()
        return {"message": "Router added successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/")
def list_routers(db: Session = Depends(get_db)):
    return db.query(Device).all()

#   ROUTER ENDPOINT: View Router Details
@router_api.get("/{router_id}")
async def get_router_details(router_id: int, db: Session = Depends(get_db)):
    """
    Retrieve detailed info for a specific router by ID.
    Includes credentials, vendor, and last seen timestamp.
    """
    router = db.query(Router).filter(Router.id == router_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")
    return {
        "id": router.id,
        "name": router.name,
        "ip_address": router.ip_address,
        "vendor": router.vendor,
        "username": router.username,
        "status": router.status,
        "last_seen": router.last_seen.isoformat() if router.last_seen else None
    }

#   ROUTER ENDPOINT: Update Router Details
class RouterUpdate(BaseModel):
    name: str | None = None
    ip_address: str | None = None
    username: str | None = None
    password: str | None = None
    vendor: str | None = None
    status: str | None = None


@router_api.put("/update/{router_id}")
async def update_router(router_id: int, router_data: RouterUpdate, db: Session = Depends(get_db)):
    """
    Update router info — supports partial updates.
    Useful for reassigning IPs or changing router credentials.
    """
    router = db.query(Router).filter(Router.id == router_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")
    for key, value in router_data.dict(exclude_unset=True).items():
        setattr(router, key, value)
    db.commit()
    db.refresh(router)
    return {"status": "success", "message": f"Router {router.name} updated.", "router": {
        "id": router.id, "ip": router.ip_address, "status": router.status
    }}

#   ROUTER ENDPOINT: Delete Router
@router_api.delete("/delete/{router_id}")
async def delete_router(router_id: int, db: Session = Depends(get_db)):
    """
    Remove a router from the system entirely.
    Intended for decommissioned or replaced routers.
    """
    router = db.query(Router).filter(Router.id == router_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")

    db.delete(router)
    db.commit()
    return {"status": "success", "message": f"Router '{router.name}' deleted successfully."}

#   ROUTER ENDPOINT: Filter by Vendor
@router_api.get("/vendor/{vendor_name}")
async def list_routers_by_vendor(vendor_name: str, db: Session = Depends(get_db)):
    """
    Filter routers by vendor (e.g., D-Link, TP-Link, Ubiquiti, Ruijie).
    """
    routers = db.query(Router).filter(Router.vendor.ilike(f"%{vendor_name}%")).all()
    if not routers:
        return {"status": "empty", "message": f"No routers found for vendor '{vendor_name}'."}
    return {
        "status": "success",
        "vendor": vendor_name,
        "count": len(routers),
        "routers": [
            {"id": r.id, "name": r.name, "ip_address": r.ip_address, "status": r.status}
            for r in routers
        ]
    }

@router_api.get("/devices/{device_id}/interfaces", response_model=List[dict])
def list_device_interfaces(device_id: str, db: Session = Depends(get_db)):
    """
    Return all interfaces for a device. Each interface is serialized as a dict.
    """
    rows = db.query(NetworkInterface).filter(NetworkInterface.device_id == device_id).all()
    out = [r.as_dict() for r in rows]
    return out

@router_api.get("/interfaces/{iface_id}/metrics")
def interface_metrics(iface_id: int, db: Session = Depends(get_db)):
    """
    Return a small metrics object for a single interface (rx/tx bytes, packets).
    Useful for the UI to poll for live updates.
    """
    r = db.query(NetworkInterface).filter(NetworkInterface.id == iface_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Interface not found")
    return {
        "id": r.id,
        "device_id": r.device_id,
        "name": r.name,
        "rx_bytes": r.rx_bytes or 0,
        "tx_bytes": r.tx_bytes or 0,
        "rx_packets": r.rx_packets or 0,
        "tx_packets": r.tx_packets or 0,
        "last_seen": r.last_seen.isoformat() if r.last_seen else None
    }

# Provide the /devices routes as well (UI uses both in different places)
@app.get("/devices", summary="List all devices")
def list_devices(db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    if not current_user.company_id:
        return []
    # Return devices in the format the UI expects
    devs = db.query(Device).options(joinedload(Device.client)).filter(Device.company_id == current_user.company_id).all()
    out = []
    for d in devs:
        ip_addr = getattr(d, "ip_address", None) or getattr(d, "ip", None) or None
        
        client_info = None
        if d.client:
            client_info = {
                "id": d.client.id,
                "name": d.client.name,
                "location": d.client.location,
            }
        out.append({
            "device_id": d.device_id,
            "client_id": d.client_id,
            "parent_device_id": d.parent_device_id,
            "parentId": d.parent_device_id,
            "client": client_info,
            "mac_address": d.mac_address,
            "mac": d.mac_address,  
            "ip_address": ip_addr,
            "ip_type": getattr(d, "ip_type", "dhcp"),
            "netmask": getattr(d, "netmask", None),
            "pppoe_username": getattr(d, "pppoe_username", None),
            "pppoe_password": getattr(d, "pppoe_password", None),
            "model": getattr(d, "model", None),
            "status": getattr(d, "status", None),
            "name": getattr(d, "name", None),
            "device_type": d.device_type,
            "station_id": d.station_id,
            "sector_id": d.sector_id,
            "status_info": {
                "uptime": getattr(d, "uptime", None) if hasattr(d, "uptime") else None,
                "clients": getattr(d, "clients", None) if hasattr(d, "clients") else []
            }
        })
    return out


@app.post("/devices", summary="Create device", status_code =201)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    # prevent duplicate device_id
    if not current_user.company_id:
        raise HTTPException(status_code=403, detail="Cannot create device: user not in a company.")
    if db.query(Device).filter(Device.device_id == payload.device_id).first():
        raise HTTPException(status_code=400, detail="Device already exists")
    mac = getattr(payload, "mac_address", None) or getattr(payload, "mac", None)
    if not mac or not str(mac).strip():
        raise HTTPException(status_code=400, detail="MAC address is required")
    # Normalize MAC: uppercase, replace hyphens with colons
    mac_normalized = mac.strip().upper().replace("-", ":")
    # Validate MAC format (after normalization)
    mac_pattern = re.compile(r"^([0-9A-F]{2}:){5}([0-9A-F]{2})$")
    if not mac_pattern.match(mac_normalized):
        raise HTTPException(status_code=400, detail="Invalid MAC format. Use AA:BB:CC:DD:EE:FF or AA-BB-CC-DD-EE-FF")
    # prevent duplicate mac_address
    if db.query(Device).filter(Device.mac_address == mac_normalized).first():
        raise HTTPException(status_code=400, detail="Device with this MAC address already exists")
    # determine a safe name
    ip_address = getattr(payload, "ip_address", None) or getattr(payload, "ip", None) or None
    # if not ip_address:
    #     raise HTTPException(status_code=400, detail="IP address is required")

    # Check parent status if parent_device_id is provided
    initial_status = getattr(payload, "status", "online")
    if payload.parent_device_id:
        parent_device = db.query(Device).filter(Device.device_id == payload.parent_device_id).first()
        if parent_device and parent_device.status in ["offline", "restarting", "reset"]:
            initial_status = "offline" # Child cannot be online if parent is offline

    new_device = Device(
        device_id=payload.device_id,
        mac_address=mac_normalized,
        ip_address=ip_address,
        model=payload.model or None,
        device_type=getattr(payload, "device_type", None),
        ssid=getattr(payload, "ssid", None),
        status=initial_status,
        company_id=current_user.company_id,
        client_id=payload.client_id,
        sector_id=getattr(payload, "sector_id", None),
        parent_device_id=payload.parent_device_id
    )
    # populate both possible ip fields to be robust
    try:
        setattr(new_device, "ip_address", payload.ip_address)
    except Exception:
        pass
    # credentials field stored as JSON string if present
    if getattr(payload, "credentials", None):
        try:
            new_device.credentials = write_credentials_field(payload.credentials)
        except Exception:
            new_device.credentials = write_credentials_field({})
    db.add(new_device)
    # Create initial config history so backups work immediately
    initial_conf = {
        "hostname": payload.device_id,
        "interfaces": {"lan": {"ip": ip_address or "0.0.0.0", "netmask": "255.255.255.0", "is_up": True}},
        "dhcp": {"enabled": True, "range_start": "192.168.1.100", "range_end": "192.168.1.200"},
        "ssid": getattr(payload, "ssid", "DefaultSSID"),
        "wifi_password": "changeme"
    }
    db.add(ConfigHistory(device_id=new_device.device_id, note="initial", config_snapshot=initial_conf))
    try: 
        db.commit()
        db.refresh(new_device)
        # Trigger auto backup
        perform_auto_backup(db, new_device.device_id, "Initial Auto-Backup")
        log_activity(db, "device_created", device_id=new_device.device_id, message=f"Device {new_device.device_id} created with MAC {new_device.mac_address}", severity="INFO", details={"device_id": new_device.device_id, "mac": new_device.mac_address, "ip": new_device.ip_address})
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    return {
        "message": "Device created",
        "device": {
            "device_id": new_device.device_id,
            "mac_address": new_device.mac_address,
            "ip_address": new_device.ip_address,
            "model": getattr(new_device, "model", None),
            "status": getattr(new_device, "status", None)
        }
}

@app.get("/devices/{device_id}", summary="Get device details")
def get_device(device_id: str, db: Session = Depends(get_db)):
    # Handle sector lookups
    if device_id.startswith("SEC-"):
        try:
            sid = int(device_id.split("-")[1])
            s = db.query(Sector).filter(Sector.id == sid).first()
            if not s: raise HTTPException(status_code=404, detail="Sector not found")
            return {
                "device_id": device_id, "name": s.name, "mac_address": s.mac_address,
                "ip_address": s.ip_address, "model": s.device_model, "device_type": "sector",
                "status": "online", "station_id": s.station_id, "firmware_version": "N/A",
                "interfaces": [], "clients": [], "client_count": 0,
                "latest_config": {"ip_type": s.ip_type, "horn": s.horn_orientation},
                "status_info": {"uptime": None, "clients": [], "rx": 0, "tx": 0}
            }
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="Invalid sector ID format")
    d = db.query(Device).options(joinedload(Device.client)).filter(Device.device_id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    latest_conf = db.query(ConfigHistory).filter(ConfigHistory.device_id == device_id).order_by(ConfigHistory.timestamp.desc()).first()
    ifaces = db.query(NetworkInterface).filter(NetworkInterface.device_id == device_id).all()
    iface_list = [i.as_dict() for i in ifaces]
    routes = db.query(RoutingTable).filter(RoutingTable.device_id == device_id).all()
    clients = [{"mac": l.client_mac, "ip": l.client_ip} for l in db.query(DHCPLease).filter(DHCPLease.device_id == device_id).all()]
    
    # Get DHCP and DNS info
    dhcp_config = get_dhcp_config_or_default(db, device_id)
    dns_info = {"server": dhcp_config.dns_server} if hasattr(dhcp_config, 'dns_server') else {}

    # Safely parse latest_config
    latest_config = {}
    if latest_conf and latest_conf.config_snapshot:
        try:
            latest_config = latest_conf.config_snapshot if isinstance(latest_conf.config_snapshot, dict) else json.loads(latest_conf.config_snapshot)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Could not parse config_snapshot for device {device_id}")
            latest_config = {}
    # Include client information if device is assigned to a client
    client_info = None
    if d.client:
        client_info = {
            "id": d.client.id,
            "name": d.client.name,
            "location": d.client.location
        }

    # Simulate SNR if not present
    snr = getattr(d, 'snr', None)
    if snr is None and getattr(d, 'device_type', None) in ['access_point', 'radio', 'router']:
        snr = random.randint(25, 90) # Simulate dB

    status_info = {
        "uptime": getattr(d, "uptime", None),
        "clients": clients,
        "rx": 0,
        "tx": 0
    }
    return {
        "device_id": d.device_id,
        "name": d.name,
        "client_id": d.client_id,
        "ip_address": d.ip_address,
        "mac_address": d.mac_address,
        "model": d.model,
        "device_type": getattr(d, "device_type", None),
        "ssid": getattr(d, "ssid", None),
        "status": d.status,
        "status_info": status_info,
        "snr": snr,
        "firmware_version": getattr(d, "firmware_version", "1.0.0"),
        "clients": clients,
        "client_count": len(clients),
        "client": client_info,
        "uptime": getattr(d, "uptime", None),
        "credentials": read_credentials_field(d),
        "latest_config": latest_config,
        "interfaces": iface_list,
        "routes": [{"rule_id": r.rule_id, "destination": r.destination, "gateway": r.gateway, "interface": r.interface, "metric": r.metric} for r in routes],
        "dhcp_config": {"range_start": dhcp_config.range_start, "range_end": dhcp_config.range_end, "enabled": dhcp_config.enabled},
        "dns_info": dns_info,
        "sector_id": getattr(d, "sector_id", None),
        "created_at": d.created_at.isoformat() if d.created_at else None
    }


@app.put("/devices/{device_id}", summary="Update device metadata")
def update_device(device_id: str, payload: DeviceUpdate, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    
    old_status = d.status # Capture old status before update

    if payload.ip is not None: d.ip_address = payload.ip
    if payload.model is not None: d.model = payload.model
    if payload.status is not None: d.status = payload.status
    if payload.credentials is not None: d.credentials = write_credentials_field(payload.credentials)
    
    db.add(d); db.commit()

    # If parent device goes offline/restarting/reset, its children must also go offline
    if payload.status and payload.status in ["offline", "restarting", "reset"] and old_status != payload.status:
        _update_child_status_recursively(db, device_id, "offline")
        db.commit() # Commit recursive changes
    # If parent comes online, children's status will be re-evaluated by polling, not automatically set to online here.
    # This prevents children from coming online if they have their own issues.

    log_activity(db, "device_updated", device_id=device_id, message=f"Device metadata updated for {device_id}")
    perform_auto_backup(db, device_id, "Auto-backup: Device Updated")
    return {"message": "Device updated", "device_id": device_id}


@app.delete("/devices/{device_id}", summary="Delete device")
def delete_device(device_id: str, db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d: raise HTTPException(status_code=404, detail="Device not found")
    # Ensure user is in the same company

    # Before deleting the device, update its children
    children_to_update = db.query(Device).filter(Device.parent_device_id == device_id).all()
    for child in children_to_update:
        child.parent_device_id = None
        child.status = "offline" # Child goes offline if parent is deleted
        db.add(child)
        _update_child_status_recursively(db, child.device_id, "offline") # Also cascade to grand-children
    if d.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this device")
    log_activity(db, "device_deleted", device_id=device_id, message=f"Device deleted: {device_id}", severity="WARNING")
    db.delete(d); db.commit()
    return {"message": "Device deleted", "device_id": device_id}

#   Backups Management
@app.get("/backups", summary="List all backups")
def list_all_backups(db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    if not current_user.company_id:
        return []
    backups = db.query(Backup).join(Device, Backup.device_id == Device.device_id).filter(Device.company_id == current_user.company_id).order_by(Backup.timestamp.desc()).all()
    return [{
        "backup_id": b.backup_id,
        "device_id": b.device_id,
        "timestamp": b.timestamp.isoformat(),
        "note": b.note,
        "config_json": b.config_json
    } for b in backups]

#    Device status, backups, restore, factory reset
@app.post("/routers/{id}/apply_config")
def apply_config(id: str, payload: dict, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if not current_user.can_configure_device and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You do not have permission to configure devices")
    # proceed with apply_config logic...

@app.get("/devices/{device_id}/status", summary="Get simple status")
def device_status(device_id: str, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d: raise HTTPException(status_code=404, detail="Device not found")
    # Provide uptime and clients if available (simulate if not)
    # For real devices integrate with device agent/adapter to fetch real status
    latest_conf = db.query(ConfigHistory).filter(ConfigHistory.device_id == device_id).order_by(ConfigHistory.timestamp.desc()).first()
    status_info = {
        "device_id": d.device_id,
        "status": d.status,
        "ip": d.ip_address,
        "mac": None,
        "uptime": "N/A",
        "clients": []
    }
    # If interfaces have MAC fill it
    iface = db.query(NetworkInterface).filter(NetworkInterface.device_id == device_id).first()
    if iface and iface.mac:
        status_info["mac"] = iface.mac
    # Optionally, look into RouterLog or DHCP leases to find clients
    leases = db.query(DHCPLease).filter(DHCPLease.device_id == device_id).all()
    status_info["clients"] = [{"mac": l.client_mac, "ip": l.ip_address} for l in leases]
    return status_info


@app.post("/devices/{device_id}/backup", summary="Create config backup")
def create_backup(device_id: str, payload: BackupCreate = None, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d: raise HTTPException(status_code=404, detail="Device not found")
    latest = db.query(ConfigHistory).filter(ConfigHistory.device_id == device_id).order_by(ConfigHistory.timestamp.desc()).first()
    if not latest or not latest.config_snapshot: raise HTTPException(status_code=400, detail="No config to backup")
    backup_id = str(uuid.uuid4())
    note = payload.note if payload and payload.note else f"Backup from {datetime.utcnow().isoformat()}"
    
    try:
        config_str = json.dumps(latest.config_snapshot)
    except TypeError:
        raise HTTPException(status_code=500, detail="Could not serialize configuration to JSON for backup.")

    b = Backup(backup_id=backup_id, device_id=device_id, note=note, config_json=config_str)
    db.add(b); db.commit()
    log_activity(db, "backup_created", device_id=device_id, message=f"Manual backup created for {device_id}")
    return {"message": "Backup created", "backup_id": backup_id, "ts": b.timestamp.isoformat()}

@app.post("/devices/{device_id}/upgrade", summary="Upgrade device firmware")
def upgrade_firmware(device_id: str, target_version: str = Query("2.0.0"), background_tasks: BackgroundTasks = None, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d: raise HTTPException(status_code=404, detail="Device not found")
    
    # 1. Create pre-upgrade backup
    perform_auto_backup(db, device_id, f"Pre-upgrade backup (v{d.firmware_version})")
    
    def _process_upgrade(did, version):
        local_db = SessionLocal()
        try:
            dev = local_db.query(Device).filter(Device.device_id == did).first()
            if dev:
                dev.status = "upgrading"
                local_db.commit()
                time.sleep(8) # Simulate upgrade time
                dev.firmware_version = version
                dev.status = "online"
                dev.last_seen = datetime.utcnow()
                local_db.commit()
                log_activity(local_db, "firmware_upgrade", device_id=did, message=f"Device upgraded to firmware v{version}", severity="NOTICE")
        finally:
            local_db.close()

    background_tasks.add_task(_process_upgrade, device_id, target_version)
    return {"message": "Firmware upgrade started", "target_version": target_version}

@app.post("/devices/{device_id}/restart", summary="Restart device")
def restart_device(device_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    # schedule a simulated restart: update status and last_seen after a short delay
    def _do_restart(db_session, did, username):
        try:
            dev = db_session.query(Device).filter(Device.device_id == did).first()
            if dev:
                dev.status = "restarting"
                db_session.add(dev); db_session.commit()
                time.sleep(5)
                dev.status = "online"
                dev.last_seen = datetime.utcnow()
                db_session.add(dev); db_session.commit()
                # log & broadcast
                log_activity(db_session, "device_restarted", username=username, device_id=did, message=f"Device {did} restarted", severity="NOTICE")
        except Exception:
            db_session.rollback()
    # use a new DB session inside background task
    from .db import SessionLocal as _SessionLocal
    username = getattr(current_user, "username", "system")
    background_tasks.add_task(lambda: _do_restart(_SessionLocal(), device_id, username))
    return {"message": "Restart scheduled", "device_id": device_id}

@app.post("/devices/{device_id}/forget", summary="Forget (remove) device")
def forget_device(device_id: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    db.delete(d)
    db.commit()
    log_activity(db, "device_forget", username=getattr(current_user, "username", None), device_id=device_id, message=f"Device {device_id} removed", severity="WARNING")
    return {"message": "Device removed", "device_id": device_id}

@app.post("/devices/{device_id}/rename-ssid", summary="Rename device WiFi SSID")
def rename_ssid(device_id: str, payload: Dict[str, str], db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    new_ssid = payload.get("ssid")
    if not new_ssid:
        raise HTTPException(status_code=400, detail="ssid required")
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    # persist to ConfigHistory and update Device.ssid
    ch = ConfigHistory(device_id=device_id, note="rename_ssid", config_snapshot={"ssid": new_ssid})
    db.add(ch)
    d.ssid = new_ssid
    db.add(d)
    db.commit()
    
    perform_auto_backup(db, device_id, f"Auto-backup: SSID changed to {new_ssid}")
    
    log_activity(db, "rename_ssid", username=getattr(current_user, "username", None), device_id=device_id, message=f"SSID for {device_id} changed to {new_ssid}", severity="NOTICE", details={"ssid": new_ssid})
    return {"message": "SSID updated", "device_id": device_id, "ssid": new_ssid}

@app.post("/devices/{device_id}/copy-config", summary="Copy config from another device onto this one")
def copy_config_to_device(device_id: str, payload: Dict[str, str], background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    source_id = payload.get("source_device_id")
    if not source_id:
        raise HTTPException(status_code=400, detail="source_device_id required")
    src = db.query(ConfigHistory).filter(ConfigHistory.device_id == source_id).order_by(ConfigHistory.timestamp.desc()).first()
    if not src:
        raise HTTPException(status_code=404, detail="Source config not found")
    # schedule apply of config snapshot to target device
    fragment = src.config_snapshot
    def _apply(db_sess, target_id, frag, username):
        try:
            ch = ConfigHistory(device_id=target_id, note=f"copied_from:{source_id}", config_snapshot=frag)
            db_sess.add(ch)
            targ = db_sess.query(Device).filter(Device.device_id == target_id).first()
            if targ:
                targ.last_config_hash = str(hash(json.dumps(frag, sort_keys=True)))
                db_sess.add(targ)
            db_sess.commit()
            log_activity(db_sess, "config_copied", username=username, device_id=target_id, message=f"Config copied from {source_id} to {target_id}", severity="NOTICE", details={"from": source_id})
        except Exception:
            db_sess.rollback()
    from .db import SessionLocal as _SessionLocal
    background_tasks.add_task(lambda: _apply(_SessionLocal(), device_id, fragment, getattr(current_user, "username", None)))
    return {"message": "Config copy scheduled", "target": device_id, "source": source_id}


@app.post("/devices/{device_id}/restore", summary="Restore from latest backup")
def restore_backup(device_id: str, payload: Optional[Dict[str, Any]] = None, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d: raise HTTPException(status_code=404, detail="Device not found")
    backup_id = payload.get("backup_id") if payload and isinstance(payload, dict) else None
    if backup_id:
        b = db.query(Backup).filter(Backup.backup_id == backup_id, Backup.device_id == device_id).first()
    else:
        b = db.query(Backup).filter(Backup.device_id == device_id).order_by(Backup.timestamp.desc()).first()
    if not b: raise HTTPException(status_code=404, detail="Backup not found")
    
    try:
        config_snapshot = json.loads(b.config_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Backup is corrupted and cannot be parsed.")

    # Push config to device via adapter
    adapter = get_vendor_adapter(d.model)
    if adapter:
        try:
            # Depending on adapter implementation, we might need to instantiate a class or call a module function
            if hasattr(adapter, 'DLinkAdapter'):
                # Instantiate if it's a class-based adapter
                agent = adapter.DLinkAdapter(host=d.ip_address or "0.0.0.0", username="admin", password="")
                # Assuming update_wifi is the main config method for now, or implement a generic push_config
                if "ssid" in config_snapshot:
                    agent.update_wifi(config_snapshot["ssid"], config_snapshot.get("wifi_password", ""))
            elif hasattr(adapter, 'push_config'):
                adapter.push_config(d.ip_address, read_credentials_field(d), config_snapshot)
        except Exception as e:
            logger.error(f"Failed to push config to device {device_id}: {e}")
            # We continue to update DB state even if push fails, but log error

    ch = ConfigHistory(device_id=device_id, note=f"restored:{b.backup_id}", config_snapshot=config_snapshot)
    db.add(ch); db.commit()
    log_activity(db, "backup_restored", device_id=device_id, message=f"Restored {device_id} from backup {b.backup_id}")
    return {"message": "Restored from backup", "backup_id": b.backup_id}


@app.post("/devices/{device_id}/factory-reset", summary="Factory reset device")
def factory_reset(device_id: str, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d: raise HTTPException(status_code=404, detail="Device not found")
    default_conf = {
        "hostname": device_id,
        "interfaces": {"lan": {"ip": d.ip_address or "0.0.0.0", "netmask": "255.255.255.0", "is_up": True}},
        "dhcp": {"enabled": True, "range_start": "192.168.1.100", "range_end": "192.168.1.200"},
        "ssid": "DefaultSSID",
        "wifi_password": "changeme"
    }
    # delete interfaces and routes (fresh start)
    db.query(NetworkInterface).filter(NetworkInterface.device_id == device_id).delete()
    db.query(RoutingTable).filter(RoutingTable.device_id == device_id).delete()
    db.add(NetworkInterface(device_id=device_id, name="lan", ip=d.ip_address or None, netmask="255.255.255.0", is_up=True))
    db.add(ConfigHistory(device_id=device_id, note="factory_reset", config_snapshot=default_conf))
    d.status = "online"
    db.add(d); db.commit()    
    log_activity(db, "factory_reset", device_id=device_id, message=f"Factory reset performed on {device_id}", severity="WARNING")
    log_device_reset(db, device_id, reason="User initiated factory reset")
    return {"message": "Factory reset applied", "device_id": device_id}

@app.post("/devices/{device_id}/attach-client", summary="Attach device to client")
def attach_device_to_client(device_id: str, client_id: int = Query(..., description="Client ID to attach to"), db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d: raise HTTPException(status_code=404, detail="Device not found")

    c = db.query(Client).filter(Client.id == client_id).first()
    if not c: raise HTTPException(status_code=404, detail="Client not found")

    d.client_id = client_id
    db.add(d)
    db.commit()
    perform_auto_backup(db, device_id, f"Auto-backup: Attached to client {c.name}")
    log_activity(db, "device_attached", device_id=device_id, message=f"Device {device_id} attached to client {c.name}", severity="INFO", details={"client_id": client_id, "client_name": c.name})
    return {"message": f"Device {device_id} attached to client {c.name}"}

@app.post("/devices/{device_id}/detach-client", summary="Detach device from client")
def detach_device_from_client(device_id: str, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d: raise HTTPException(status_code=404, detail="Device not found")

    old_client_id = d.client_id
    d.client_id = None
    db.add(d)
    db.commit()
    perform_auto_backup(db, device_id, "Auto-backup: Detached from client")

    if old_client_id:
        c = db.query(Client).filter(Client.id == old_client_id).first()
        client_name = c.name if c else "Unknown"
        log_activity(db, "device_detached", device_id=device_id, message=f"Device {device_id} detached from client {client_name}", severity="INFO", details={"client_id": old_client_id, "client_name": client_name})

    return {"message": f"Device {device_id} detached from client"}

#   Device endpoint to apply config via vendor adapter

@app.post("/routers/{device_id}/apply_config")
def apply_config(device_id: str, config: dict, db: Session = Depends(get_db)):
    router = db.query(Device).filter(Device.device_id == device_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")

    # Determine vendor adapter dynamically
    adapter = get_vendor_adapter(router.model)
    if not adapter:
        raise HTTPException(status_code=400, detail="Unsupported router model")

    # Push config to router via adapter
    result = adapter.push_config(router.ip_address, router.credentials, config)
    router.last_config_push = datetime.utcnow()
    db.commit()
    
    perform_auto_backup(db, device_id, "Auto-backup: Configuration Applied")
    
    return {"message": "Configuration applied", "result": result}

@app.post("/routers/configure")
async def configure_router(config_data: RouterConfig, db: Session = Depends(get_db)):
    router = db.query(Router).filter(Router.id == config_data.router_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")

    adapter = get_adapter(router.vendor, router.ip_address, router.username, router.password)
    if not adapter or not adapter.login():
        raise HTTPException(status_code=400, detail="Failed to connect to device")

    result = adapter.update_wifi(config_data.ssid, config_data.password)
    return {"status": "Configuration updated", "result": result}


#   DHCP endpoints (basic simulation)
@app.get("/devices/{device_id}/dhcp/config")
def get_dhcp_config(device_id: str, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d: raise HTTPException(status_code=404, detail="Device not found")
    cfg = get_dhcp_config_or_default(db, device_id)
    return {"device_id": cfg.device_id, "range_start": cfg.range_start, "range_end": cfg.range_end, "lease_time": cfg.lease_time, "enabled": bool(cfg.enabled)}


@app.put("/devices/{device_id}/dhcp/config")
def put_dhcp_config(device_id: str, payload: Dict[str, Any], db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d: raise HTTPException(status_code=404, detail="Device not found")
    range_start = payload.get("range_start"); range_end = payload.get("range_end")
    lease_time = payload.get("lease_time", 86400); enabled = payload.get("enabled", True)
    cfg = db.query(DHCPConfig).filter(DHCPConfig.device_id == device_id).first()
    if not cfg:
        cfg = DHCPConfig(device_id=device_id, range_start=range_start, range_end=range_end, lease_time=lease_time, enabled=enabled)
        db.add(cfg)
    else:
        cfg.range_start = range_start; cfg.range_end = range_end; cfg.lease_time = lease_time; cfg.enabled = enabled
        db.add(cfg)
    db.commit()
    log_activity(db, "dhcp_config_updated", device_id=device_id, message=f"DHCP config updated on {device_id}: {range_start}-{range_end}")
    return {"message": "dhcp updated", "device_id": device_id}


@app.post("/devices/{device_id}/dhcp/request")
def request_dhcp_lease(device_id: str, payload: DHCPRequestIn, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d: raise HTTPException(status_code=404, detail="Device not found")
    cfg = get_dhcp_config_or_default(db, device_id)
    if not cfg.enabled:
        raise HTTPException(status_code=400, detail="DHCP disabled on device")
    # cleanup expired leases
    now = datetime.utcnow()
    expired = db.query(DHCPLease).filter(DHCPLease.device_id == device_id, DHCPLease.ts_expiry <= now).all()
    for e in expired:
        db.delete(e)
    db.commit()
    # check existing lease
    existing = db.query(DHCPLease).filter(DHCPLease.device_id == device_id, DHCPLease.client_mac == payload.client_mac).first()
    expiry = now + timedelta(seconds=cfg.lease_time)
    if existing:
        existing.client_hostname = payload.client_hostname or existing.client_hostname
        existing.ts_start = now; existing.ts_expiry = expiry
        db.add(existing); db.commit()
        log_activity(db, "dhcp_lease_renewed", device_id=device_id, message=f"DHCP lease renewed for {payload.client_mac} -> {existing.ip_address}")
        return {"lease_id": existing.lease_id, "ip_address": existing.ip_address, "ts_expiry": existing.ts_expiry.isoformat()}
    # honor requested ip if in pool and free
    if payload.requested_ip:
        try:
            if ip_to_int(payload.requested_ip) < ip_to_int(cfg.range_start) or ip_to_int(payload.requested_ip) > ip_to_int(cfg.range_end):
                raise HTTPException(status_code=400, detail="Requested IP outside pool")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid requested IP")
        used = {l.ip_address for l in db.query(DHCPLease).filter(DHCPLease.device_id == device_id).all()}
        if payload.requested_ip in used:
            raise HTTPException(status_code=409, detail="Requested IP already in use")
        lease_id = str(uuid.uuid4())
        lease = DHCPLease(lease_id=lease_id, device_id=device_id, client_mac=payload.client_mac, client_hostname=payload.client_hostname, ip_address=payload.requested_ip, ts_start=now, ts_expiry=expiry)
        db.add(lease); db.commit()
        log_activity(db, "dhcp_lease_assigned", device_id=device_id, message=f"DHCP lease assigned (requested) {payload.requested_ip} to {payload.client_mac}")
        return {"lease_id": lease_id, "ip_address": payload.requested_ip, "ts_expiry": lease.ts_expiry.isoformat()}
    # otherwise assign next free
    free_ip = find_next_free_ip(db, cfg)
    if not free_ip:
        raise HTTPException(status_code=409, detail="No available IPs in pool")
    lease_id = str(uuid.uuid4())
    lease = DHCPLease(lease_id=lease_id, device_id=device_id, client_mac=payload.client_mac, client_hostname=payload.client_hostname, ip_address=free_ip, ts_start=now, ts_expiry=expiry)
    db.add(lease); db.commit()
    log_activity(db, "dhcp_lease_assigned", device_id=device_id, message=f"DHCP lease assigned {free_ip} to {payload.client_mac}")
    return {"lease_id": lease_id, "ip_address": free_ip, "ts_expiry": lease.ts_expiry.isoformat()}


@app.get("/devices/{device_id}/dhcp/leases")
def list_dhcp_leases(device_id: str, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if not d: raise HTTPException(status_code=404, detail="Device not found")
    now = datetime.utcnow()
    rows = db.query(DHCPLease).filter(DHCPLease.device_id == device_id, DHCPLease.ts_expiry > now).order_by(DHCPLease.ts_start.desc()).all()
    out = [{"lease_id": r.lease_id, "client_mac": r.client_mac, "client_hostname": r.client_hostname, "ip_address": r.ip_address, "ts_start": r.ts_start.isoformat(), "ts_expiry": r.ts_expiry.isoformat()} for r in rows]
    return out


#    Logs/events
@app.get("/logs")
def get_logs(limit: int = 200, db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    """Return recent activity logs with all fields for alerts UI."""
    if not current_user.company_id:
        return []
    rows = db.query(EventLog).filter(EventLog.company_id == current_user.company_id).order_by(EventLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "activity_type": r.activity_type,
            "username": r.username,
            "device_id": r.device_id,
            "message": r.message,
            "severity": r.severity or "INFO",
            "details": r.details,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "ts": r.ts.isoformat() if getattr(r, "ts", None) else r.timestamp.isoformat() if r.timestamp else None
        }
        for r in rows
    ]

#       Discovery endpoint
@app.get("/discovery/scan")
def discover_devices(db: Session = Depends(get_db), subnet: str = Query("192.168.1.0/22")):
    """
    Scan a local subnet for reachable devices.
    If you have your own discovery_engine.scan_network, it will be used; otherwise returns a small mock.
    """
    if discovery_scan_network:
        try:
            return discovery_scan_network(subnet)
            
        except Exception as e:
            return {"error": "discovery failed", "detail": str(e)}

    # Simple mock result to allow UI testing
    mock = [
        {"ip": "192.168.1.1", "mac": "AA:BB:CC:DD:EE:01", "vendor": "D-Link", "http_title": "D-Link Router", "config_state": "reset"},
        {"ip": "192.168.1.10", "mac": "AA:BB:CC:DD:EE:02", "vendor": "Ruijie", "http_title": "Ruijie", "config_state": "configured"},
    ]
    devices = [DeviceCreate(device_id=f"device-{i+1}", ip=d["ip"], model=d["vendor"], status="online", credentials={}) for i, d in enumerate(mock)]
    log_device_discovered(db, len(devices), subnet=subnet)
    return mock

#Auto-provision endpoint
@app.post("/auto_provision")
async def auto_provision(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Automatically provisions devices that are detected as reset.
    Compares discovered MAC with system records; if a backup exists, restores it.
    """
    data = await request.json()
    ip = data.get("ip")
    mac = data.get("mac")
    vendor = data.get("vendor")

    if not mac:
        return {"status": "error", "message": "MAC address required"}

    # Normalize MAC
    mac = mac.upper().replace("-", ":")
    print(f"[AUTO-PROVISION] Device {ip} ({mac}) flagged as reset.")

    # Step 1: Check if device exists in DB by MAC
    device = db.query(Device).filter(Device.mac_address == mac).first()
    if not device:
        print(f"[AUTO-PROVISION] Device with MAC {mac} not found in system. Skipping.")
        return {"status": "skipped", "reason": "unknown_device"}

    # Update IP if changed (reset devices often revert to default IP)
    if device.ip_address != ip:
        device.ip_address = ip
        db.add(device)
        db.commit()

    # Step 2: Find latest backup
    latest_backup = db.query(Backup).filter(Backup.device_id == device.device_id).order_by(Backup.timestamp.desc()).first()
    
    if not latest_backup:
        print(f"[AUTO-PROVISION] No backup found for {device.device_id}. Skipping.")
        log_activity(db, "auto_provision_skipped", device_id=device.device_id, message=f"Reset detected for {device.device_id} but no backup found.", severity="WARNING")
        return {"status": "skipped", "reason": "no_backup"}

    # Step 3: Queue provisioning in background
    def _perform_restore(device_id, backup_id, target_ip, model_hint):
        session = SessionLocal()
        try:
            dev = session.query(Device).filter(Device.device_id == device_id).first()
            bkp = session.query(Backup).filter(Backup.backup_id == backup_id).first()
            if not dev or not bkp: return

            try:
                config_snapshot = json.loads(bkp.config_json)
            except json.JSONDecodeError:
                log_activity(session, "auto_provision_failed", device_id=device_id, message="Backup corrupted", severity="ERROR")
                return

            adapter = get_vendor_adapter(dev.model or model_hint)
            if adapter and hasattr(adapter, 'push_config'):
                creds = read_credentials_field(dev)
                # Attempt restore
                res = adapter.push_config(target_ip, creds, config_snapshot)
                log_activity(session, "auto_provision_success", device_id=device_id, message=f"Auto-adoption successful. Config restored from backup.", severity="NOTICE")
                dev.status = "online"
                session.commit()
            else:
                log_activity(session, "auto_provision_failed", device_id=device_id, message="Adapter missing or incompatible", severity="ERROR")
        except Exception as e:
            log_activity(session, "auto_provision_failed", device_id=device_id, message=f"Provisioning error: {str(e)}", severity="ERROR")
        finally:
            session.close()

    background_tasks.add_task(_perform_restore, device.device_id, latest_backup.backup_id, ip, vendor)
    log_activity(db, "auto_provision_started", device_id=device.device_id, message=f"Reset detected. Starting auto-adoption for {device.device_id}.", severity="NOTICE")
    
    return {"status": "queued", "device": device.device_id}

#analytics
@app.get("/analytics", summary="Basic analytics and reports")
def analytics_report(db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    """
    Return simple analytics: device counts, online, backups count, events by severity, avg uptime.
    UI (analytics.js) expects this shape.
    """
    if not current_user.company_id:
        return {
            "total_devices": 0, "online": 0, "offline": 0, "backups": 0,
            "events_by_severity": {}, "avg_uptime_seconds": 0, "devices_added_last_24h": 0,
            "device_breakdown": {},
            "usage": {"avg_tx_mbps": 0, "avg_rx_mbps": 0, "total_data_gb": 0, "active_devices_24h": 0}
        }

    total_devices = db.query(Device).filter(Device.company_id == current_user.company_id).count()
    online = db.query(Device).filter(Device.company_id == current_user.company_id, Device.status == "online").count()
    offline = total_devices - online
    backups = db.query(Backup).join(Device).filter(Device.company_id == current_user.company_id).count()
    # events by severity
    rows = db.query(EventLog.severity, func.count(EventLog.id)).filter(EventLog.company_id == current_user.company_id).group_by(EventLog.severity).all()
    events_by_severity = {r[0] or "INFO": r[1] for r in rows}
    # avg uptime (in seconds)
    avg_up = db.query(func.avg(Device.uptime)).filter(Device.company_id == current_user.company_id).scalar() or 0
    # devices added last 24h
    since = datetime.utcnow() - timedelta(hours=24)
    recent = db.query(Device).filter(Device.company_id == current_user.company_id, Device.created_at >= since).count()

    # Device breakdown
    device_search_map = {
        "router": "router",
        "switch": "switch",
        "radio": "radio",
        "gateway": "gateway",
        "access_point": "access point",
        "camera": "camera"
    }
    breakdown = {}
    for key, term in device_search_map.items():
        count = db.query(Device).filter(
            Device.company_id == current_user.company_id,
            (func.lower(Device.device_type).contains(term)) | 
            (func.lower(Device.model).contains(term))
        ).count()
        breakdown[key] = count

    # Calculate aggregate network traffic
    if total_devices > 0:
        # Summing actual cumulative bytes from all interfaces
        total_rx_bytes = db.query(func.sum(NetworkInterface.rx_bytes)).join(Device).filter(Device.company_id == current_user.company_id).scalar() or 0
        total_tx_bytes = db.query(func.sum(NetworkInterface.tx_bytes)).join(Device).filter(Device.company_id == current_user.company_id).scalar() or 0
        
        # If no real network data exists, estimate based on online devices (simulated environment)
        if total_rx_bytes == 0 and total_tx_bytes == 0 and online > 0:
            # Realistic Rates: TX is the baseline, RX is roughly 1.3x to 1.6x higher
            # Base: ~0.7 Mbps TX per device.
            rand_variation = 0.9 + (random.random() * 0.2) # +/- 10% jitter
            avg_tx = round((online * 0.7) * rand_variation, 1)
            # RX is at most a third to a half higher (e.g., 6mbps TX -> 8-10mbps RX)
            avg_rx = round(avg_tx * (1.3 + (random.random() * 0.2)), 1)
            
            # Cumulative Data Usage Simulation (Never drops)
            now = time.time()
            delta_seconds = now - SIMULATED_TRAFFIC_STATE["last_update"]
            
            # User requirement: 20MB to 200MB growth per minute depending on devices
            # 0.1 GB per minute for 10 devices is ~0.01 GB per device per minute
            growth_rate_per_device_per_sec = 0.01 / 60 
            delta_gb = (online * growth_rate_per_device_per_sec) * delta_seconds
            
            SIMULATED_TRAFFIC_STATE["total_data_gb"] += delta_gb
            SIMULATED_TRAFFIC_STATE["last_update"] = now
            total_data = round(SIMULATED_TRAFFIC_STATE["total_data_gb"], 2)
        else:
            # Use real accumulated data from database
            total_data = round((total_rx_bytes + total_tx_bytes) / (1024**3), 2)
            # Network Traffic Rates (Mbps) - Proportional to online devices for a stable live view
            avg_rx = round(online * 1.2, 1)
            avg_tx = round(online * 0.3, 1)
        
        usage = {
            "avg_tx_mbps": avg_tx,
            "avg_rx_mbps": avg_rx,
            "total_data_gb": total_data,
            "active_devices_24h": online
        }
    else:
        usage = {
            "avg_tx_mbps": 0, "avg_rx_mbps": 0, "total_data_gb": 0, "active_devices_24h": 0
        }

    return {
        "total_devices": total_devices,
        "online": online,
        "offline": offline,
        "backups": backups,
        "events_by_severity": events_by_severity,
        "avg_uptime_seconds": int(avg_up),
        "devices_added_last_24h": recent,
        "device_breakdown": breakdown,
        "usage": usage
    }

#      Settings Endpoints
SETTINGS_FILE = "system_settings.json"

@app.get("/settings", tags=["Settings"])
def get_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

@app.post("/settings", tags=["Settings"])
def save_settings(settings: Dict[str, Any]):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

#csv export endpoint
@app.get("/export/devices")
def export_devices_csv(db: Session = Depends(get_db)):
    """
    Export devices as CSV. Query params could be added (filter, fields etc).
    """
    devices = db.query(Device).all()
    def gen():
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(["device_id","mac_address","ip_address","model","status","created_at"])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        for d in devices:
            writer.writerow([d.device_id, d.mac_address, d.ip_address or "", d.model or "", d.status or "", d.created_at.isoformat() if getattr(d, "created_at", None) else ""])
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)
    headers = {"Content-Disposition": "attachment; filename=devices.csv"}
    return StreamingResponse(gen(), media_type="text/csv", headers=headers)

@app.get("/export/logs")
def export_logs_csv(db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    """
    Export event logs as CSV for the current user's company.
    """
    if not current_user.company_id:
        return StreamingResponse(iter(["company_id required"]), media_type="text/csv")

    logs = db.query(EventLog).filter(EventLog.company_id == current_user.company_id).order_by(EventLog.timestamp.desc()).all()
    
    def gen():
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(["timestamp", "severity", "activity_type", "device_id", "username", "message", "details"])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        for r in logs:
            writer.writerow([r.timestamp.isoformat() if r.timestamp else "", r.severity or "INFO", r.activity_type or "", r.device_id or "", r.username or "", r.message or "", json.dumps(r.details) if r.details else ""])
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)
    headers = {"Content-Disposition": "attachment; filename=event_logs.csv"}
    return StreamingResponse(gen(), media_type="text/csv", headers=headers)

@app.get("/api/companies/{company_id}/templates", response_model=List[DeviceTemplateSchema])
def list_device_templates(company_id: int, db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    if current_user.company_id != company_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    return db.query(DeviceTypeTemplate).filter(DeviceTypeTemplate.company_id == company_id).all()

@app.post("/api/companies/{company_id}/templates")
def create_or_update_template(company_id: int, payload: DeviceTemplateSchema, db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    if current_user.company_id != company_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    # Check if template exists for this type
    template = db.query(DeviceTypeTemplate).filter(
        DeviceTypeTemplate.company_id == company_id,
        DeviceTypeTemplate.device_type == payload.device_type
    ).first()

    if template:
        template.config_content = payload.config_content
        template.template_name = payload.template_name
        template.is_default = payload.is_default
    else:
        template = DeviceTypeTemplate(
            company_id=company_id,
            device_type=payload.device_type,
            template_name=payload.template_name,
            config_content=payload.config_content,
            is_default=payload.is_default
        )
        db.add(template)
    
    db.commit()
    db.refresh(template)
    return template

@app.post("/api/companies/{company_id}/templates/{device_type}/reset")
def reset_template(company_id: int, device_type: str, db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    if current_user.company_id != company_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Default templates
    defaults = {
        "router": "hostname {{hostname}}\ninterface eth0\n ip address {{ip_address}} {{netmask}}\n dns-server {{dns_primary}}\n ntp server {{ntp_server}}",
        "switch": "hostname {{hostname}}\nvlan 1\n name default\ninterface vlan 1\n ip address {{ip_address}} {{netmask}}",
        "firewall": "hostname {{hostname}}\nfirewall enable\nrule 1 allow tcp port 22",
        "wireless": "hostname {{hostname}}\nssid {{ssid}}\n psk {{wifi_password}}"
    }
    
    content = defaults.get(device_type, "hostname {{hostname}}")
    
    template = db.query(DeviceTypeTemplate).filter(
        DeviceTypeTemplate.company_id == company_id,
        DeviceTypeTemplate.device_type == device_type
    ).first()

    if template:
        template.config_content = content
    else:
        template = DeviceTypeTemplate(company_id=company_id, device_type=device_type, config_content=content, is_default=True)
        db.add(template)
    
    db.commit()
    return {"status": "reset", "content": content}

@app.post("/devices/adopt", summary="Adopt discovered device")
def adopt_device(payload: dict, db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    if not current_user.company_id:
        raise HTTPException(status_code=403, detail="User must belong to a company to adopt devices")

    ip = payload.get("ip")
    mac = payload.get("mac")
    
    if not ip or not mac:
        raise HTTPException(status_code=400, detail="IP and MAC required")

    # 1. Create/Get Device
    device_id = f"dev-{mac.replace(':', '')[-6:]}"
    existing = db.query(Device).filter(Device.mac_address == mac).first()
    
    if existing:
        if existing.company_id != current_user.company_id:
            raise HTTPException(status_code=409, detail="Device registered to another company")
        device = existing
        device.ip_address = ip
        device.status = "online"
    else:
        device = Device(
            device_id=device_id,
            mac_address=mac,
            ip_address=ip,
            company_id=current_user.company_id,
            status="online",
            model="Generic"
        )
        db.add(device)
    
    # 2. Fetch Company Defaults
    defaults = db.query(CompanyDefaults).filter(CompanyDefaults.company_id == current_user.company_id).first()
    def_dict = defaults.__dict__ if defaults else {}

    # 3. Fetch Device Template
    # Simple heuristic for type based on model or default to router
    dev_type = "router" 
    template_obj = db.query(DeviceTypeTemplate).filter(
        DeviceTypeTemplate.company_id == current_user.company_id,
        DeviceTypeTemplate.device_type == dev_type
    ).first()
    
    template_content = template_obj.config_content if template_obj else "hostname {{hostname}}\n# No template found"

    # 4. Merge & Generate Config
    # Prepare context
    context = {
        "hostname": device_id,
        "ip_address": ip,
        "netmask": "255.255.255.0",
        "ssid": "CompanyWiFi",
        "wifi_password": "securepassword"
    }
    # Overlay company defaults
    for k, v in def_dict.items():
        if v and not k.startswith('_'):
            context[k] = v
            
    # Simple jinja-like replacement ({{key}})
    final_config = template_content
    for k, v in context.items():
        final_config = final_config.replace(f"{{{{{k}}}}}", str(v))

    # 5. Save Config
    ch = ConfigHistory(device_id=device.device_id, note="Initial Adoption", config_snapshot={"raw": final_config})
    db.add(ch)
    db.commit()
    
    log_activity(db, "device_adopted", username=current_user.username, device_id=device.device_id, message=f"Device {device.device_id} adopted with template")
    
    return {"status": "adopted", "device_id": device.device_id, "config_preview": final_config}

#           Simple health & root
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/health")
def health(db: Session = Depends(get_db)):
    return {"status": "ok", "routers": len(db.query(Device).all()), "time": datetime.utcnow().isoformat()}


# API Endpoint: Apply Configuration to Router
@app.post("/routers/{device_id}/apply_config")
def apply_config(device_id: str, payload: dict, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Apply a configuration fragment to a specific router.
    Steps:
        1. Fetch device info from DB
        2. Load correct vendor adapter
        3. Push configuration via HTTP/Telnet/SSH depending on vendor
        4. Save config history in DB
    """
    router = db.query(Device).filter(Device.device_id == device_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")

    adapter = get_vendor_adapter(router.model)
    if not adapter:
        raise HTTPException(status_code=400, detail="No adapter for this router model")

    # Background push operation
    def push_task():
        result = adapter.push_config(router.ip_address, router.credentials, payload)
        print(f"[Config Push] {router.device_id}: {result}")

    background_tasks.add_task(push_task)
    return {"message": f"Configuration push initiated for {router.device_id}"}


# API Endpoint: Fetch Router Live Status
@app.get("/routers/{device_id}/status")
def fetch_router_status(device_id: str, db: Session = Depends(get_db)):
    """
    Retrieve live status from the router via its vendor adapter.
    Returns uptime, SSID, connected clients, etc.
    """
    router = db.query(Device).filter(Device.device_id == device_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")

    adapter = get_vendor_adapter(router.model)
    if not adapter:
        raise HTTPException(status_code=400, detail="No adapter available for this router type")

    try:
        status = adapter.fetch_status(router.ip_address, router.credentials)
        return {"device_id": device_id, "status": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve router status: {e}")

@app.get("/routers", response_model=list[dict])
def get_routers(db: Session = Depends(get_db)):
    """
    Returns a list of all routers/devices managed by the system.
    """
    routers = db.query(Router).all()
    return [
        {
            "device_id": r.device_id,
            "ip": r.ip_address,
            "model": r.model,
            "status": r.status,
            "status_info": {
                "uptime": r.uptime if hasattr(r, "uptime") else None,
                "clients": r.clients if hasattr(r, "clients") else []
            },
        }
        for r in routers
    ]

# API Endpoint: Factory Reset Router
@app.post("/routers/{device_id}/factory_reset")
def factory_reset(device_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Performs a remote factory reset on a router.
    Uses vendor adapter's reset_device() to trigger the operation.
    """
    router = db.query(Device).filter(Device.device_id == device_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")

    adapter = get_vendor_adapter(router.model)
    if not adapter:
        raise HTTPException(status_code=400, detail="Unsupported router model")

    def reset_task():
        result = adapter.reset_device(router.ip_address, router.credentials)
        print(f"[Factory Reset] {router.device_id}: {result}")

    background_tasks.add_task(reset_task)
    return {"message": f"Factory reset triggered for {router.device_id}"}


# OPTIONAL: Synchronization Endpoint (Periodic Poll)
@app.get("/routers/{device_id}/sync")
def sync_router_config(device_id: str, db: Session = Depends(get_db)):
    """
    Sync router’s live configuration into the controller database.
    This can be run periodically to detect manual changes.
    """
    router = db.query(Device).filter(Device.device_id == device_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")

    adapter = get_vendor_adapter(router.model)
    if not adapter:
        raise HTTPException(status_code=400, detail="No adapter for this router type")

    try:
        live_conf = adapter.fetch_config(router.ip_address, router.credentials)
        router.last_sync = datetime.utcnow()
        router.last_known_config = live_conf
        db.commit()
        return {"device_id": device_id, "status": "synced", "config": live_conf}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")

#Audit listing endpoint
@app.get("/audit/logs")
def list_audit_logs(limit: int = 200, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    # only admin can view full audit trail
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    rows = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [{"id": r.id, "username": r.username, "action": r.action, "target_type": r.target_type, "target_id": r.target_id, "details": r.details, "timestamp": r.timestamp.isoformat() if r.timestamp else None} for r in rows]

#Mass deployment configuration endpoint
@app.post("/deploy", summary="Mass deploy configuration fragment")
def mass_deploy(payload: Dict[str, Any], background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """
    payload: { "device_ids": [...], "fragment": {...}, "dry_run": false }
    Requires user with config privileges (current_user).
    Returns immediate ack and schedules background work.
    """
    device_ids = payload.get("device_ids") or []
    fragment = payload.get("fragment") or {}
    dry_run = bool(payload.get("dry_run", False))

    if not isinstance(device_ids, list) or not fragment:
        raise HTTPException(status_code=400, detail="device_ids (list) and fragment (object) required")

    # permission check
    if not getattr(current_user, "can_configure_device", False) and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Insufficient privileges")

    # create audit record
    log_audit_db(db, getattr(current_user, "username", None), "mass_deploy", target_type="devices", target_id=",".join(device_ids), details={"dry_run": dry_run, "fragment": fragment})

    # schedule background tasks per device
    for did in device_ids:
        if dry_run:
            # in dry-run we just log event
            background_tasks.add_task(log_event_db, db, f"Dry-run deploy for {did}", device_id=did)
        else:
            background_tasks.add_task(_apply_config_to_device, db, did, fragment, getattr(current_user, "username", None))
            # optionally call vendor adapter in background (best-effort)
            def _call_adapter(did_local, frag):
                try:
                    r = db.query(Device).filter(Device.device_id == did_local).first()
                    if r and r.model:
                        adapter = get_vendor_adapter(r.model)
                        if adapter and hasattr(adapter, "apply_config"):
                            adapter.apply_config(r.ip_address, frag)
                except Exception:
                    pass
            background_tasks.add_task(_call_adapter, did, fragment)
    log_config_deployed(db, getattr(current_user, "username", None), device_ids, fragment)
            
    return {"status": "accepted", "scheduled": len(device_ids), "dry_run": dry_run}

#    Transmission Stations API
stations_router = APIRouter(prefix="/stations", tags=["Stations"])

@stations_router.get("/")
def list_stations(db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    return db.query(TransmissionStation).filter(TransmissionStation.company_id == current_user.company_id).options(joinedload(TransmissionStation.sectors)).all()

@stations_router.post("/")
def create_station(payload: Dict[str, Any], db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    station = TransmissionStation(
        name=payload["name"],
        location=payload.get("location"),
        is_gateway=payload.get("is_gateway", False),
        company_id=current_user.company_id,
        station_type=payload.get("station_type", "primary"),
        parent_id=payload.get("parent_id"),
        link_device_id=payload.get("link_device_id"),
        device_model=payload.get("device_model")
    )

    # Validate MAC uniqueness for the main device
    main_mac = payload.get("main_device_mac")
    if main_mac:
        existing_mac = db.query(Device).filter(Device.mac_address == main_mac).first()
        if existing_mac:
            raise HTTPException(status_code=400, detail="Main device MAC address already exists in system.")

    db.add(station)
    db.flush() # Get station.id before creating devices

    # Create the Main Station Device
    if station.device_model:
        main_device_id = f"STN-{station.id}-{str(uuid.uuid4())[:4]}"
        main_dev = Device(
            device_id=main_device_id,
            mac_address=main_mac or "",
            ip_address=payload.get("main_device_ip"),
            model=station.device_model,
            name=f"{station.name} (Main)",
            device_type="infrastructure",
            company_id=current_user.company_id,
            status="online",
            station_id=station.id
        )
        db.add(main_dev)
        db.add(ConfigHistory(
            device_id=main_device_id,
            note="station_init",
            config_snapshot={
                "hostname": station.name,
                "type": "station_main",
                "ip": main_dev.ip_address
            }
        ))

    # If this is a gateway station, create a gateway device
    if station.is_gateway and payload.get("gateway_mac"):
        device_id = f"gateway-{str(uuid.uuid4())[:8]}"
        gateway_device = Device(
            device_id=device_id,
            mac_address=payload.get("gateway_mac", ""),
            ip_address=payload.get("gateway_ip"),
            ip_type=payload.get("gateway_ip_type", "dhcp"),
            netmask=payload.get("gateway_netmask") if payload.get("gateway_ip_type") == "static" else None,
            pppoe_username=payload.get("gateway_pppoe_username") if payload.get("gateway_ip_type") == "pppoe" else None,
            pppoe_password=payload.get("gateway_pppoe_password") if payload.get("gateway_ip_type") == "pppoe" else None,
            model=station.device_model,
            name=f"{station.name} Gateway",
            device_type="gateway",
            company_id=current_user.company_id,
            status="online",
            station_id=station.id,
        )
        db.add(gateway_device)
        db.add(ConfigHistory(
            device_id=device_id,
            note="initial",
            config_snapshot={
                "hostname": device_id,
                "interfaces": {"wan": {"ip": gateway_device.ip_address or "0.0.0.0", "netmask": gateway_device.netmask or "255.255.255.0", "is_up": True}},
                "ssid": gateway_device.ssid,
                "model": gateway_device.model,
                "gateway": True
            }
        ))
    
    try:
        db.commit()
        if station.device_model:
            perform_auto_backup(db, main_device_id, "Initial Station Device Backup")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return station

@stations_router.put("/{station_id}")
def update_station(station_id: int, payload: Dict[str, Any], db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    station = db.query(TransmissionStation).filter(
        TransmissionStation.id == station_id,
        TransmissionStation.company_id == current_user.company_id
    ).first()
    
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")

    # Basic updates
    station.name = payload.get("name", station.name)
    station.location = payload.get("location", station.location)
    station.station_type = payload.get("station_type", station.station_type)
    station.device_model = payload.get("device_model", station.device_model)
    station.parent_id = payload.get("parent_id")
    station.link_device_id = payload.get("link_device_id")
    
    # Hierarchy validation: ensure we don't link a station to itself
    if station.parent_id == station.id:
        station.parent_id = None

    try:
        db.commit()
        db.refresh(station)
        log_activity(db, "station_updated", message=f"Station '{station.name}' updated", severity="INFO")
        return station
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@stations_router.delete("/{station_id}")
def delete_station(station_id: int, db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    station = db.query(TransmissionStation).filter(
        TransmissionStation.id == station_id,
        TransmissionStation.company_id == current_user.company_id
    ).first()

    if not station:
        raise HTTPException(status_code=404, detail="Station not found")

    # Safeguard: Check if other stations depend on this one as an uplink
    dependent_stations = db.query(TransmissionStation).filter(TransmissionStation.parent_id == station_id).count()
    if dependent_stations > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot delete station: {dependent_stations} other station(s) depend on this as an uplink."
        )

    try:
        station_name = station.name
        db.delete(station)
        db.commit()
        log_activity(db, "station_deleted", message=f"Station '{station_name}' and its sectors were deleted", severity="WARNING")
        return {"success": True, "message": "Station deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@stations_router.post("/{station_id}/sectors")
def add_sector(station_id: int, payload: Dict[str, Any], db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    sector = Sector(
        name=payload["name"],
        station_id=station_id,
        mac_address=payload.get("mac_address"),
        device_model=payload.get("device_model"),
        horn_orientation=payload.get("horn_orientation"),
        ip_type=payload.get("ip_type", "dhcp"),
        ip_address=payload.get("ip_address") if payload.get("ip_type") == "static" else None,
        netmask=payload.get("netmask") if payload.get("ip_type") == "static" else None
    )
    db.add(sector)
    db.commit()
    db.refresh(sector)

    # Create a virtual sector device entry so we can backup sectors like other station devices.
    synthetic_mac = sector.mac_address or f"02:00:{station_id & 0xff:02x}:{sector.id & 0xff:02x}:{(sector.id >> 8) & 0xff:02x}:{(sector.id >> 16) & 0xff:02x}"
    device = Device(
        device_id=f"SEC-{sector.id}",
        mac_address=synthetic_mac,
        name=sector.name,
        ip_address=sector.ip_address,
        model=sector.device_model,
        device_type="sector",
        company_id=current_user.company_id,
        status="online",
        station_id=station_id,
        sector_id=sector.id,
        ip_type=sector.ip_type,
        netmask=sector.netmask
    )
    db.add(device)
    db.add(ConfigHistory(
        device_id=device.device_id,
        note="initial",
        config_snapshot={
            "hostname": device.device_id,
            "interfaces": {"lan": {"ip": device.ip_address or "0.0.0.0", "netmask": device.netmask or "255.255.255.0", "is_up": True}},
            "ssid": device.ssid,
            "model": device.model,
            "station_id": station_id,
            "device_type": device.device_type,
            "sector_id": sector.id
        }
    ))
    db.commit()
    perform_auto_backup(db, device.device_id, "Initial Auto-Backup")
    return {"success": True, "message": "Sector created", "sector_id": sector.id, "sector": sector, "device_id": device.device_id}

@stations_router.get("/{station_id}/devices")
def list_station_devices(station_id: int, db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    """
    Get all devices attached to a specific station.
    Returns devices in a format suitable for dropdowns and lists.
    """
    devices = db.query(Device).filter(
        Device.station_id == station_id,
        Device.company_id == current_user.company_id
    ).all()
    
    out = []
    for d in devices:
        out.append({
            "device_id": d.device_id,
            "name": d.name,
            "device_type": d.device_type,
            "model": d.model,
            "status": d.status,
            "ip_address": d.ip_address,
            "mac_address": d.mac_address,
            "sector_id": d.sector_id,
            "parent_device_id": d.parent_device_id
        })
    
    return out

@stations_router.post("/{station_id}/devices")
def add_station_device(station_id: int, payload: Dict[str, Any], db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    """
    Create a device within a station. Handles special case where device_type='sector'.
    """
    try:
        device_type = payload.get("device_type", "").lower()
        device_name = payload.get("name", "")
        
        if not device_name:
            raise HTTPException(status_code=400, detail="Device name is required")
        
        # Verify station exists
        station = db.query(TransmissionStation).filter(TransmissionStation.id == station_id).first()
        if not station:
            raise HTTPException(status_code=404, detail="Station not found")
        
        if device_type == "sector":
            # Create a sector record and a matching virtual device row so it can be backed up like other devices.
            sector = Sector(
                name=device_name,
                station_id=station_id,
                mac_address=payload.get("mac_address"),
                device_model=payload.get("model") or payload.get("device_model"),
                horn_orientation=payload.get("horn_orientation"),
                ip_type=payload.get("ip_type", "dhcp"),
                ip_address=payload.get("ip_address") if payload.get("ip_type") == "static" else None,
                netmask=payload.get("netmask") if payload.get("ip_type") == "static" else None
            )
            db.add(sector)
            db.commit()
            db.refresh(sector)

            synthetic_mac = sector.mac_address or f"02:00:{station_id & 0xff:02x}:{sector.id & 0xff:02x}:{(sector.id >> 8) & 0xff:02x}:{(sector.id >> 16) & 0xff:02x}"
            device = Device(
                device_id=f"SEC-{sector.id}",
                mac_address=synthetic_mac,
                name=sector.name,
                ip_address=sector.ip_address,
                model=sector.device_model,
                device_type="sector",
                company_id=current_user.company_id,
                status="online",
                station_id=station_id,
                sector_id=sector.id,
                ip_type=sector.ip_type,
                netmask=sector.netmask
            )
            db.add(device)
            db.add(ConfigHistory(
                device_id=device.device_id,
                note="initial",
                config_snapshot={
                    "hostname": device.device_id,
                    "interfaces": {"lan": {"ip": device.ip_address or "0.0.0.0", "netmask": device.netmask or "255.255.255.0", "is_up": True}},
                    "ssid": device.ssid,
                    "model": device.model,
                    "station_id": station_id,
                    "device_type": device.device_type,
                    "sector_id": sector.id
                }
            ))
            db.commit()
            perform_auto_backup(db, device.device_id, "Initial Auto-Backup")
            return {"success": True, "message": "Sector created", "sector_id": sector.id, "sector": sector, "device_id": device.device_id}
        else:
            # Create a regular device (radio, switch, backhaul, ap, camera, router, etc.)
            # Generate a unique device_id
            import uuid
            device_id = f"{device_type}-{str(uuid.uuid4())[:8]}"
            
            device = Device(
                device_id=device_id,
                mac_address=payload.get("mac_address", ""),
                ip_address=payload.get("ip_address"),
                ip_type=payload.get("ip_type", "dhcp"),
                netmask=payload.get("netmask") if payload.get("ip_type") == "static" else None,
                pppoe_username=payload.get("pppoe_username") if payload.get("ip_type") == "pppoe" else None,
                pppoe_password=payload.get("pppoe_password") if payload.get("ip_type") == "pppoe" else None,
                model=payload.get("model"),
                name=device_name,
                device_type=device_type,
                company_id=current_user.company_id,
                status="online",
                station_id=station_id,  # Set station_id for all devices added to station
                parent_device_id=payload.get("parent_device_id"),
            )
            
            # Handle sector_id for radio devices
            if device_type == "radio":
                sector_id = payload.get("sector_id")
                if not sector_id:
                    raise HTTPException(status_code=400, detail="Sector is required for radio devices")
                device.sector_id = sector_id
                device.frequency = payload.get("frequency")
            
            # Handle other device-specific fields
            if device_type == "switch":
                pass 
            elif device_type == "backhaul":
                device.ssid = payload.get("link_partner")  # Store link partner in ssid temporarily
            elif device_type == "ap":
                device.ssid = payload.get("channel")  # Store channel in ssid temporarily
            
            db.add(device)
            db.add(ConfigHistory(
                device_id=device.device_id,
                note="initial",
                config_snapshot={
                    "hostname": device.device_id,
                    "interfaces": {"lan": {"ip": device.ip_address or "0.0.0.0", "netmask": device.netmask or "255.255.255.0", "is_up": True}},
                    "ssid": device.ssid,
                    "model": device.model,
                    "station_id": station_id,
                    "device_type": device_type
                }
            ))
            db.commit()
            perform_auto_backup(db, device.device_id, "Initial Auto-Backup")
            return {"success": True, "message": "Device created", "device_id": device.device_id, "device": device}
            
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error creating device: {str(e)}")

@stations_router.put("/{station_id}/devices/{device_id}")
def update_station_device(station_id: int, device_id: str, payload: Dict[str, Any], db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    """
    Update a device attached to a station.
    """
    try:
        # Verify station exists
        station = db.query(TransmissionStation).filter(TransmissionStation.id == station_id).first()
        if not station:
            raise HTTPException(status_code=404, detail="Station not found")
        
        # Get the device
        device = db.query(Device).filter(
            Device.device_id == device_id,
            Device.station_id == station_id,
            Device.company_id == current_user.company_id
        ).first()
        
        if not device:
            raise HTTPException(status_code=404, detail="Device not found in this station")
        
        # Update device fields
        if "name" in payload:
            device.name = payload["name"]
        if "model" in payload:
            device.model = payload["model"]
        if "mac_address" in payload:
            device.mac_address = payload["mac_address"]
        if "ip_address" in payload:
            device.ip_address = payload["ip_address"]
        if "ip_type" in payload:
            device.ip_type = payload["ip_type"]
        if "netmask" in payload:
            device.netmask = payload["netmask"]
        if "pppoe_username" in payload:
            device.pppoe_username = payload["pppoe_username"]
        if "pppoe_password" in payload:
            device.pppoe_password = payload["pppoe_password"]
        
        db.add(device)
        db.commit()
        return {"success": True, "message": "Device updated", "device_id": device.device_id}
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error updating device: {str(e)}")

@stations_router.delete("/{station_id}/devices/{device_id}")
def delete_station_device(station_id: int, device_id: str, db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    """
    Delete a device from a station. Does not delete backups or dependent devices.
    """
    try:
        # Verify station exists
        station = db.query(TransmissionStation).filter(TransmissionStation.id == station_id).first()
        if not station:
            raise HTTPException(status_code=404, detail="Station not found")
        
        # Get the device
        device = db.query(Device).filter(
            Device.device_id == device_id,
            Device.station_id == station_id,
            Device.company_id == current_user.company_id
        ).first()
        
        if not device:
            raise HTTPException(status_code=404, detail="Device not found in this station")
        
        # Just delete the device, not its backups or dependent devices
        db.delete(device)
        db.commit()
        return {"success": True, "message": "Device deleted", "device_id": device_id}
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error deleting device: {str(e)}")

@stations_router.put("/{station_id}/sectors/{sector_id}")
def update_station_sector(station_id: int, sector_id: int, payload: Dict[str, Any], db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    try:
        station = db.query(TransmissionStation).filter(TransmissionStation.id == station_id).first()
        if not station:
            raise HTTPException(status_code=404, detail="Station not found")

        sector = db.query(Sector).filter(
            Sector.id == sector_id,
            Sector.station_id == station_id
        ).first()
        if not sector:
            raise HTTPException(status_code=404, detail="Sector not found")

        if "name" in payload:
            sector.name = payload["name"]
        if "device_model" in payload:
            sector.device_model = payload["device_model"]
        if "mac_address" in payload:
            sector.mac_address = payload["mac_address"]
        if "horn_orientation" in payload:
            sector.horn_orientation = payload["horn_orientation"]
        if "ip_type" in payload:
            sector.ip_type = payload["ip_type"]
            if sector.ip_type != "static":
                sector.ip_address = None
                sector.netmask = None
        if "ip_address" in payload and sector.ip_type == "static":
            sector.ip_address = payload["ip_address"]
        if "netmask" in payload and sector.ip_type == "static":
            sector.netmask = payload["netmask"]

        db.add(sector)
        device = db.query(Device).filter(Device.device_id == f"SEC-{sector.id}").first()
        if device:
            device.name = sector.name
            device.model = sector.device_model
            device.mac_address = sector.mac_address
            device.ip_type = sector.ip_type
            device.ip_address = sector.ip_address
            device.netmask = sector.netmask
            db.add(device)

        db.commit()
        return {"success": True, "message": "Sector updated", "sector_id": sector.id}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error updating sector: {str(e)}")

@stations_router.delete("/{station_id}/sectors/{sector_id}")
def delete_station_sector(station_id: int, sector_id: int, db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    try:
        station = db.query(TransmissionStation).filter(TransmissionStation.id == station_id).first()
        if not station:
            raise HTTPException(status_code=404, detail="Station not found")

        sector = db.query(Sector).filter(
            Sector.id == sector_id,
            Sector.station_id == station_id
        ).first()
        if not sector:
            raise HTTPException(status_code=404, detail="Sector not found")

        radios = db.query(Device).filter(Device.sector_id == sector_id, Device.device_type == "radio").count()
        if radios:
            raise HTTPException(status_code=400, detail="Cannot delete sector while radios are still assigned")

        device = db.query(Device).filter(Device.device_id == f"SEC-{sector.id}").first()
        if device:
            db.delete(device)

        db.delete(sector)
        db.commit()
        return {"success": True, "message": "Sector deleted", "sector_id": sector_id}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error deleting sector: {str(e)}")


app.include_router(stations_router)

#user role server endpoint
@app.get("/me")
def me(current_user: AuthUser = Depends(get_current_user)):
    company_name = current_user.company.name if current_user.company else None
    return {
        "username": current_user.username,
        "role": current_user.role,
        "email": current_user.email,
        "phone_number": current_user.phone_number,
        "company_name": company_name,
        "ui_theme": current_user.ui_theme,
        "theme_accent": current_user.theme_accent,
        "capabilities": {"can_add_device": current_user.can_add_device, "can_delete_device": current_user.can_delete_device, "can_configure_device": current_user.can_configure_device}
    }

@app.put("/me/theme")
def update_my_theme(theme: str = Query(..., regex="^(light|dark)$"), db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    """
    Toggle between light and dark mode.
    """
    current_user.ui_theme = theme
    db.commit()
    return {"status": "success", "theme": theme}

# --- Tools Endpoints ---
class PingRequest(BaseModel):
    host: str

@app.post("/tools/ping", summary="Ping a host")
def tool_ping(payload: PingRequest):
    host = payload.host
    # Basic validation to prevent command injection
    if not re.match(r"^[a-zA-Z0-9.:-]+$", host):
            return {"output": "Invalid host format."}

    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '4', host]
    
    try:
        res = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15)
        return {"output": res.stdout}
    except Exception as e:
        return {"output": f"Error executing ping: {str(e)}"}

class TraceRequest(BaseModel):
    host: str

@app.post("/tools/traceroute", summary="Traceroute to a host")
def tool_traceroute(payload: TraceRequest):
    host = payload.host
    # Basic validation to prevent command injection
    if not re.match(r"^[a-zA-Z0-9.:-]+$", host):
            return {"output": "Invalid host format."}

    param = '-d' # -d for Windows to not resolve addresses to hostnames
    command = ['tracert', param, host] if platform.system().lower() == 'windows' else ['traceroute', host]
    
    try:
        res = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        return {"output": res.stdout}
    except Exception as e:
        return {"output": f"Error executing traceroute: {str(e)}"}

#    Reports & Analytics Endpoints

class ReportSchedule(BaseModel):
    report_type: str
    frequency: str
    email: str

@app.get("/reports/usage")
def get_usage_report(db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    if not current_user.company_id:
        return {"status": "error", "message": "No company context"}
    
    # Simulated usage data based on real device counts
    total_devices = db.query(Device).filter(Device.company_id == current_user.company_id).count()
    online_devices = db.query(Device).filter(Device.company_id == current_user.company_id, Device.status == "online").count()
    
    if total_devices == 0:
        return {
            "status": "success",
            "data": {
                "total_bandwidth": "0 GB",
                "active_devices_avg": 0,
                "peak_usage_time": "N/A",
                "uptime_avg": "0%"
            }
        }

    # Calculate stable proportional bandwidth
    bw = round(online_devices * 1.8, 1)
    return {
        "status": "success",
        "data": {
            "total_bandwidth": f"{bw} GB",
            "active_devices_avg": int(online_devices * 0.85),
            "peak_usage_time": "14:00 - 16:00",
            "uptime_avg": "99.9%"
        }
    }

@app.get("/reports/compliance")
def get_compliance_report(db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    if not current_user.company_id:
        return {"status": "error", "message": "No company context"}

    devices = db.query(Device).filter(Device.company_id == current_user.company_id).all()
    total = len(devices)
    # Mock compliance checks
    outdated = sum(1 for d in devices if getattr(d, "firmware_version", "1.0.0") != "2.0.0") 
    weak_creds = sum(1 for d in devices if "admin" in (d.credentials or "")) 

    return {
        "status": "success",
        "data": {
            "compliant_devices": total - outdated - weak_creds,
            "outdated_firmware": outdated,
            "weak_credentials": weak_creds,
            "compliance_score": int(((total - outdated - weak_creds) / total * 100) if total > 0 else 100)
        }
    }

@app.get("/reports/export")
def export_report(report_type: str, format: str, db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user), preview: bool = Query(False)):
    if format not in ["csv", "pdf"]:
        raise HTTPException(status_code=400, detail="Invalid format")
    
    def gen_csv():
        buf = StringIO()
        writer = csv.writer(buf)
        if report_type == "usage":
            # Fetch actual usage summary metrics
            usage = get_usage_report(db, current_user)["data"]
            writer.writerow(["--- NETWORK USAGE & TRENDS REPORT ---"])
            writer.writerow(["Metric", "Value"])
            writer.writerow(["Total Bandwidth", usage["total_bandwidth"]])
            writer.writerow(["Avg Active Devices", usage["active_devices_avg"]])
            writer.writerow(["Peak Usage Time", usage["peak_usage_time"]])
            writer.writerow(["System Uptime", usage["uptime_avg"]])
            writer.writerow([]) # Spacer
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)

            writer.writerow(["Date", "Bandwidth_GB", "Active_Devices", "Uptime"])
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)
            
            online_devices = db.query(Device).filter(Device.company_id == current_user.company_id, Device.status == "online").count()
            total_devices = db.query(Device).filter(Device.company_id == current_user.company_id).count()
            for i in range(7):
                bw = round(online_devices * 1.8 * (0.9 + (random.random() * 0.2)), 1) if total_devices > 0 else 0
                active = int(online_devices * 0.85) if total_devices > 0 else 0
                writer.writerow([(datetime.utcnow() - timedelta(days=i)).date(), bw, active, "99.9%"])
                yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        elif report_type == "compliance":
            # Fetch actual compliance summary metrics
            comp = get_compliance_report(db, current_user)["data"]
            writer.writerow(["--- SECURITY COMPLIANCE REPORT ---"])
            writer.writerow(["Metric", "Value"])
            writer.writerow(["Compliance Score", f"{comp['compliance_score']}%"])
            writer.writerow(["Compliant Devices", comp["compliant_devices"]])
            writer.writerow(["Outdated Firmware", comp["outdated_firmware"]])
            writer.writerow(["Weak Credentials", comp["weak_credentials"]])
            writer.writerow([]) # Spacer
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)

            writer.writerow(["DeviceID", "Model", "Firmware", "Compliant", "Issues"])
            devices = db.query(Device).filter(Device.company_id == current_user.company_id).all()
            for d in devices:
                fw = getattr(d, "firmware_version", "1.0.0")
                is_weak = "admin" in (d.credentials or "")
                is_outdated = fw != "2.0.0"
                issues = [i for i, cond in [("Outdated", is_outdated), ("Weak Creds", is_weak)] if cond]
                writer.writerow([d.device_id, d.model or "Generic", fw, "Yes" if not issues else "No", "; ".join(issues)])
                yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        
    if format == "csv":
        headers = {"Content-Disposition": f"attachment; filename={report_type}_report.csv"}
        return StreamingResponse(gen_csv(), media_type="text/csv", headers=headers)
    else:
        # Mock PDF response
        return StreamingResponse(iter([f"%PDF-1.4\n%Mock PDF content for {report_type} report"]), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={report_type}_report.pdf"})

@app.post("/reports/schedule")
def schedule_report(schedule: ReportSchedule, db: Session = Depends(get_db), current_user: AuthUser = Depends(get_current_user)):
    # In a real app, save to DB. Here we just log.
    logger.info(f"Scheduled {schedule.report_type} report ({schedule.frequency}) for {schedule.email}")
    return {"status": "success", "message": f"{schedule.report_type} report scheduled {schedule.frequency}"}

# APP REGISTRATION: Registers router endpoints. 
app.include_router(router_api)
app.include_router(auth_router, tags=["auth"])
app.include_router(user_router, tags=["users"])
app.include_router(backup_router, tags=["backups"])
app.include_router(router, tags=["clients"])
app.include_router(alerts_router, tags=["alerts"])
