"""
Device Discovery Service (Scanner Agent for One ISP)
====================================================
Continuously scans a configured subnet inside one ISP’s network.
When a new device is detected, it registers it to the central backend API.

Assumptions:
- This script runs INSIDE one specific ISP's network (e.g., VM in their NOC).
- The ISP has a unique identifier (ISP_ID) known to the SaaS platform.
"""

import threading
import time
import subprocess
import re
import requests
import socket
import ipaddress
from contextlib import closing
import platform
from typing import List, Dict, Optional


#    CONFIGURATION
ISP_ID = "ISP-KE-001"  # set per ISP during deployment (via config file/env)

# Central SaaS‑style API (multi‑tenant platform)
API_BASE_URL = "https://your-saas‑platform.com/api"  # or the internal gateway
API_TOKEN = "YOUR_API_TOKEN_HERE"  # per‑ISP or per‑agent token

# Scan interval and subnet (set to the ISP's CPE/radio VLAN)
DISCOVERY_INTERVAL = 60  # seconds between scans
TARGET_SUBNET = "10.100.10.0/24"  # e.g., radio/vendors VLAN; change as needed

# ARP timeout and port‑check timeout
ARP_TIMEOUT = 3
PORT_CHECK_TIMEOUT = 2


#    OS‑specific ARP helpers
def get_arp_table_windows() -> List[Dict[str, str]]:
    p = subprocess.run(["arp", "-a"], capture_output=True, text=True)
    lines = p.stdout.splitlines()
    results = []
    for line in lines:
        m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F\-:]{17})\s+(\w+)", line)
        if m:
            ip = m.group(1)
            mac = m.group(2).replace("-", ":").lower()
            results.append({"ip": ip, "mac": mac})
    return results


def get_arp_table_unix() -> List[Dict[str, str]]:
    p = subprocess.run(["arp", "-n"], capture_output=True, text=True)
    lines = p.stdout.splitlines()
    results = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 4:
            ip = parts[0]
            mac = parts[2].lower()
            results.append({"ip": ip, "mac": mac})
    return results


def get_local_arp_entries() -> List[Dict[str, str]]:
    if platform.system().lower().startswith("win"):
        return get_arp_table_windows()
    else:
        return get_arp_table_unix()


def filter_devices_by_subnet(devices: List[Dict[str, str]], subnet_str: str) -> List[Dict[str, str]]:
    """
    Keep only devices whose IPs fall into the configured subnet.
    e.g., 10.100.10.1 is in 10.100.10.0/24.
    """
    network = ipaddress.ip_network(subnet_str, strict=False)
    keep = []
    for d in devices:
        try:
            ip = ipaddress.ip_address(d["ip"])
            if ip in network:
                keep.append(d)
        except Exception:
            pass
    return keep


def discovery_scan() -> List[Dict[str, str]]:
    """
    Scans the local ARP table, filters by TARGET_SUBNET, and returns
    devices visible to this scanner agent.
    """
    entries = get_local_arp_entries()
    filtered = filter_devices_by_subnet(entries, TARGET_SUBNET)
    return filtered


#    Utility Functions
def is_port_open(ip: str, port: int, timeout: float = PORT_CHECK_TIMEOUT) -> bool:
    """Check if a specific TCP port is open on the given IP."""
    try:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((ip, port)) == 0
    except Exception:
        return False


def detect_device_model(ip: str) -> str:
    """Detect if a device matches common router/CPE ports."""
    protocols = {
        "HTTP": is_port_open(ip, 80, 2),
        "HTTPS": is_port_open(ip, 443, 2),
        "SSH": is_port_open(ip, 22, 2),
        "TELNET": is_port_open(ip, 23, 2),
        "MICROTIK_API": is_port_open(ip, 8728, 2),  # common for MikroTik
    }
    for proto, status in protocols.items():
        if status:
            return f"Router/CPE ({proto})"
    return "Unknown"


#    API Registration
def register_device_with_api(device: Dict[str, str]):
    """
    Register a discovered device (MAC‑centric) to the central SaaS platform.
    Request body is annotated by ISP_ID so the platform knows which tenant this belongs to.
    """
    model = detect_device_model(device["ip"])

    payload = {
        "isp_id": ISP_ID,            # ← this scopes the device to one ISP only
        "device_id": f"cpe-{device['mac'].replace(':', '')[:12]}".lower(),
        "ip": device["ip"],
        "mac": device["mac"],
        "model": model,
        "agent_timestamp": time.time(),
    }

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            f"{API_BASE_URL}/v1/agents/discover",  # your endpoint for scanner agents
            json=payload,
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            print(f"[Discovery] Registered device {payload['device_id']} (ISP={ISP_ID}).")
        elif response.status_code == 409:
            print(f"[Discovery] Device {payload['device_id']} already exists.")
        else:
            print(f"[Discovery] API registration failed: {response.status_code} {response.text}")
    except Exception as e:
        print(f"[Discovery] API registration error: {e}")


#    Agents’ Background Loop
def discovery_loop(interval: int = DISCOVERY_INTERVAL, subnet: str = TARGET_SUBNET):
    """
    Continuously scans the configured subnet, finds new devices, and registers them.
    This runs inside ONE ISP’s network; the central platform never scans directly.
    """
    known_devices = set()  # MACs already seen by this agent

    while True:
        print(f"[Discovery] Scanning subnet {subnet} for ISP {ISP_ID}...")

        arp_devices = discovery_scan()  # ARP‑based discovery, filtered by subnet
        for dev in arp_devices:
            mac = dev["mac"]
            ip = dev["ip"]

            # Optional: confirm device is still alive via ping
            try:
                p = subprocess.run(
                    ["ping", "-c", "1", "-W", "2", ip],
                    capture_output=True, text=True
                )
                is_alive = p.returncode == 0
            except Exception:
                is_alive = False

            if not is_alive:
                continue  # Skip dead entries

            if mac not in known_devices:
                known_devices.add(mac)
                print(f"[Discovery] New active device in ISP {ISP_ID}: {dev}")
                register_device_with_api(dev)

        time.sleep(interval)


def start_discovery_service(interval: int = DISCOVERY_INTERVAL, subnet: str = TARGET_SUBNET):
    """
    Start the scanner agent in the background as a daemon thread.
    This should be deployed once per ISP, inside their own network.
    """
    thread = threading.Thread(
        target=discovery_loop,
        args=(interval, subnet),
        daemon=True
    )
    thread.start()
    print(f"[Discovery] Scanner agent started for ISP {ISP_ID} (subnet={subnet}).")


#    For local testing or debug run
if __name__ == "__main__":
    print("[Discovery] Standalone scanner agent (one ISP network). Press Ctrl+C to stop.")
    start_discovery_service()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n[Discovery] Scanner agent stopped.")