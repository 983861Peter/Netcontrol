# discovery_service.py
"""
Device Discovery Service (Auto-Register Version)
================================================
Continuously scans the local network for reachable devices.
When a new device is detected, it automatically registers it to the FastAPI backend.

"""

import threading
import time
import subprocess
import re
import requests
import socket
from contextlib import closing
import platform
from .db import SessionLocal
from .models import Device
from datetime import datetime

API_BASE_URL = "http://127.0.0.1:8080" 
DISCOVERY_INTERVAL = 60  # seconds between scans
ARP_REGEX = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s+([\w-]+)\s+([\w:]+)", re.IGNORECASE)

def get_arp_table_windows():
    p = subprocess.run(["arp", "-a"], capture_output=True, text=True)
    lines = p.stdout.splitlines()
    results = []
    # Windows arp -a outputs lines with IP and MAC; parse generically
    for line in lines:
        m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F\-:]{17})\s+(\w+)", line)
        if m:
            ip = m.group(1)
            mac = m.group(2).replace("-", ":").lower()
            results.append((ip, mac))
    return results

def get_arp_table_unix():
    p = subprocess.run(["arp", "-n"], capture_output=True, text=True)
    lines = p.stdout.splitlines()
    results = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 4:
            ip = parts[0]
            mac = parts[2].lower()
            results.append((ip, mac))
    return results

def get_local_arp_entries():
    if platform.system().lower().startswith("win"):
        return get_arp_table_windows()
    else:
        return get_arp_table_unix()

def discovery_scan():
    """
    Scans local ARP table and returns list of discovered devices:
        [{ ip: '192.168.1.2', mac: 'aa:bb:cc:dd:ee:ff' }, ...]
    """
    entries = get_local_arp_entries()
    out = []
    for ip, mac in entries:
        out.append({"ip": ip, "mac": mac})
    return out

def discovery_and_update_db():
    db = SessionLocal()
    try:
        found = discovery_scan()
        for item in found:
            ip = item["ip"]
            mac = item["mac"]
            dev = db.query(Device).filter(Device.mac_address == mac).first()
            now = datetime.utcnow()
            if dev:
                # update ip and last_seen
                dev.ip_address = ip
                dev.last_seen = now
                dev.status = "online"
            else:
                # create a minimal record for now; name=mac placeholder
                newd = Device(device_id=f"unknown-{mac.replace(':','')[:8]}",
                                mac_address=mac,
                                name=f"{mac}",
                                ip_address=ip,
                                status="online",
                                created_at=now,
                                last_seen=now)
                db.add(newd)
        db.commit()
    finally:
        db.close()

# --------------- Utility Functions --------------- #
def is_port_open(ip, port, timeout=1):
    """Check if a specific TCP port is open."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((ip, port)) == 0


def list_arp_devices():
    """Extract reachable devices from the ARP table."""
    try:
        result = subprocess.check_output("arp -a", shell=True, text=True)
        devices = []
        for line in result.splitlines():
            ip_match = re.search(r"\(([\d\.]+)\)", line)
            mac_match = re.search(r"(([0-9a-f]{2}[:-]){5}[0-9a-f]{2})", line, re.I)
            if ip_match and mac_match:
                ip = ip_match.group(1)
                mac = mac_match.group(1).lower()
                devices.append({"ip": ip, "mac": mac})
        return devices
    except Exception as e:
        print(f"[Discovery] ARP scan failed: {e}")
        return []


def ping_device(ip):
    """Ping device to confirm it's alive."""
    try:
        output = subprocess.run(["ping", "-n", "1", "-w", "500", ip],
                                capture_output=True, text=True)
        return output.returncode == 0
    except Exception:
        return False


def detect_device_model(ip):
    """Detect if a device matches known router ports (HTTP, Telnet, SSH)."""
    try:
        protocols = {
            "HTTP": is_port_open(ip, 80),
            "HTTPS": is_port_open(ip, 443),
            "Telnet": is_port_open(ip, 23),
            "SSH": is_port_open(ip, 22)
        }
        for proto, status in protocols.items():
            if status:
                return proto
        return "Unknown"
    except Exception:
        return "Unknown"


# --------------- API Callback Integration --------------- #
def register_device_with_api(device):
    """
    Automatically register new devices to the FastAPI backend.
    This assumes /routers expects fields: device_id, ip, model.
    """
    try:
        model = detect_device_model(device["ip"])
        payload = {
            "device_id": f"auto-{device['mac'].replace(':', '')[-6:]}",
            "ip": device["ip"],
            "model": f"Detected-{model}",
        }
        print(f"[Discovery] Registering device with API: {payload}")
        response = requests.post(f"{API_BASE_URL}/routers", json=payload, timeout=5)
        if response.status_code == 200:
            print(f"[Discovery] Device {payload['device_id']} registered successfully.")
        elif response.status_code == 409:
            print(f"[Discovery] Device {payload['device_id']} already exists.")
        else:
            print(f"[Discovery] Registration failed: {response.status_code}")
    except Exception as e:
        print(f"[Discovery] API registration error: {e}")


# --------------- Discovery Loop --------------- #
def discovery_loop(interval=DISCOVERY_INTERVAL):
    """Continuously scan the network and auto-register new devices."""
    known_devices = set()
    while True:
        print("[Discovery] Scanning network for devices...")
        arp_devices = list_arp_devices()
        for dev in arp_devices:
            if ping_device(dev["ip"]) and dev["mac"] not in known_devices:
                known_devices.add(dev["mac"])
                print(f"[Discovery] New active device found: {dev}")
                register_device_with_api(dev)
        time.sleep(interval)


def start_discovery_service(interval=DISCOVERY_INTERVAL):
    """Start background discovery loop as a daemon thread."""
    thread = threading.Thread(target=discovery_loop, args=(interval,), daemon=True)
    thread.start()
    print("[Discovery] Background discovery service started.")


# --------------- Optional Debug Run --------------- #
if __name__ == "__main__":
    print("[Discovery] Standalone discovery mode. Press Ctrl+C to stop.")
    start_discovery_service()
    while True:
        time.sleep(60)
