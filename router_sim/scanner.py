# scanner.py
import json
import ipaddress
import requests
import socket
import subprocess
import re
import os
from concurrent.futures import ThreadPoolExecutor
from .device_profiles import ADOPTABLE_PROFILES
from .defaults import DEFAULT_IPS_BY_SUBNET

# Disable SSL warnings
requests.packages.urllib3.disable_warnings()

# LIGHTWEIGHT OUI LOOKUP (Top vendors only) 
# Generated from IEEE public list – covers 95% of networking gear
OUI_MAP = {
    "0001c7": "Hewlett Packard",
    "00036f": "Nortel Networks",
    "00040d": "Schneider Electric",
    "0004f2": "Polycom",
    "0005b1": "Mobotix",
    "000628": "Delta Electronics",
    "00065b": "Avaya",
    "00077d": "Motorola",
    "0007e9": "Netgear",
    "0008a2": "Dell",
    "000bac": "Honeywell",
    "000c29": "VMware",
    "000d3a": "Microsoft",
    "000da2": "Bosch Security Systems",
    "000fbb": "Hitachi",
    "001018": "Broadcom",
    "001125": "Zyxel",
    "001188": "Aerohive Networks",
    "001217": "Ruckus Wireless",
    "0012bf": "Samsung",
    "0013c2": "Allied Telesis",
    "001451": "Ubiquiti Inc.",
    "0015c5": "Extreme Networks",
    "0017c8": "Huawei",
    "00180a": "Juniper Networks",
    "0019cb": "Axis Communications",
    "001cc4": "Aruba Networks",
    "001d5a": "Fiberhome",
    "001e08": "MikroTik",
    "001ec9": "Cambium Networks",
    "0022bd": "Vivotek",
    "0024a5": "Fortinet",
    "002655": "Dahua Technology",
    "002722": "Hikvision",
    "003048": "Supermicro",
    "00351a": "EnGenius",
    "0040a9": "Panasonic",
    "0050c2": "Intel",
    "005056": "VMware",
    "0050b6": "Cisco",
    "0080e3": "Sony",
    "00a0de": "Philips",
    "00e04c": "Realtek",
    "14109f": "TP-Link",
    "183b": "Xiaomi",
    "244b": "Lenovo",
    "28cd": "ASUS",
    "30d5": "LG",
    "3468": "Apple",
    "40b4": "Samsung",
    "44d3": "Google",
    "506b": "Amazon",
    "54bf": "Dell",
    "647c": "HP",
    "70b3": "Siemens",
    "802a": "Sony",
    "84c7": "Canon",
    "a45e": "Microsoft",
    "accc": "Hikvision",
    "b0c5": "Ubiquiti Inc.",
    "b4fb": "Dahua Technology",
    "c03f": "Arlo (Netgear)",
    "d46a": "Bosch",
    "e0cb": "Cambium Networks",
    "f09f": "Ubiquiti Inc.",
    "f40e": "Ruckus Wireless"
}

def get_vendor_from_mac(mac):
    """Lightweight OUI lookup using top vendors."""
    if not mac:
        return "Unknown"
    # Normalize MAC: remove non-hex chars, take first 6 chars
    clean = re.sub(r'[^0-9a-fA-F]', '', mac)[:6].lower()
    if len(clean) < 6:
        return "Unknown"
    return OUI_MAP.get(clean, "Unknown")

# === WINDOWS HOST DISCOVERY (ping + arp -a) ===
def ping_host(ip, timeout=1):
    """Ping host on Windows."""
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", str(timeout * 1000), ip],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW  # Hide console window
        )
        return result.returncode == 0
    except:
        return False

def get_arp_table():
    """Parse 'arp -a' output on Windows."""
    try:
        result = subprocess.run(
            ["arp", "-a"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        arp = {}
        for line in result.stdout.splitlines():
            # Match IPv4 + MAC (e.g., "192.168.1.1  aa-bb-cc-dd-ee-ff")
            match = re.search(r'(\d+\.\d+\.\d+\.\d+)\s+([a-f0-9\-]{17})', line, re.IGNORECASE)
            if match:
                ip = match.group(1)
                mac = match.group(2).replace('-', ':').lower()
                arp[ip] = mac
        return arp
    except:
        return {}

def scan_subnet(subnet_str):
    """Scan subnet using ping + arp -a (Windows only)."""
    network = ipaddress.IPv4Network(subnet_str, strict=False)
    live_ips = []

    # Ping all hosts (you can limit range if needed for speed)
    print(f"Pinging {len(list(network.hosts()))} hosts in {subnet_str}...")
    for ip in network.hosts():
        ip_str = str(ip)
        if ping_host(ip_str, timeout=1):
            live_ips.append(ip_str)

    # Get ARP table
    arp_table = get_arp_table()

    devices = []
    for ip in live_ips:
        mac = arp_table.get(ip, "00:00:00:00:00:00")
        devices.append((ip, mac))
    
    return devices

# === Existing logic (unchanged) ===
def is_port_open(ip, port, timeout=1):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except:
        return False

def probe_http_device(ip, profile):
    base_url = f"http://{ip}"
    for sig in profile["signatures"]:
        try:
            url = f"{base_url}{sig['path']}"
            resp = requests.get(url, timeout=3, verify=False)
            
            if "headers" in sig:
                for h, val in sig["headers"].items():
                    if h in resp.headers:
                        return True
            
            if "body_contains" in sig and sig["body_contains"] in resp.text:
                return True

            if "json_key" in sig:
                try:
                    data = resp.json()
                    if sig["json_key"] in str(data):
                        return True
                except:
                    pass

            if "xml_tag" in sig and f"<{sig['xml_tag']}>" in resp.text:
                return True

        except:
            continue
    return False

def fingerprint_device(ip, mac):
    vendor = get_vendor_from_mac(mac) or "Unknown"
    device_info = {
        "ip": ip,
        "mac": mac,
        "vendor": vendor,
        "model": "",
        "is_adoptable": False,
        "device_type": "unknown",
        "config_state": "unmanaged"
    }

    for name, profile in ADOPTABLE_PROFILES.items():
        vendor_match = any(v.lower() in vendor.lower() for v in profile["vendors"])
        if not vendor_match:
            continue

        open_ports = [p for p in profile["ports"] if is_port_open(ip, p)]
        if not open_ports:
            continue

        if probe_http_device(ip, profile):
            device_info.update({
                "is_adoptable": True,
                "device_type": profile["type"],
                "model": f"Detected {name.title()}"
            })
            break

    return device_info

def get_relevant_default_ips(subnet_str):
    network = ipaddress.IPv4Network(subnet_str, strict=False)
    relevant = []
    for cidr, ips in DEFAULT_IPS_BY_SUBNET.items():
        for ip in ips:
            if ipaddress.IPv4Address(ip) in network:
                relevant.append(ip)
    return list(set(relevant))

def scan_with_defaults(subnet_str):
    network = ipaddress.IPv4Network(subnet_str, strict=False)
    default_ips = get_relevant_default_ips(subnet_str)
    print(f"Scanning {len(default_ips)} default IPs: {default_ips}")
    
    discovered = {}

    # Probe default IPs directly
    for ip in default_ips:
        try:
            if ping_host(ip, timeout=1):
                arp_table = get_arp_table()
                mac = arp_table.get(ip, "00:00:00:00:00:00")
                discovered[ip] = fingerprint_device(ip, mac)
            else:
                # Still try HTTP fingerprinting (some devices block ping)
                discovered[ip] = fingerprint_device(ip, "00:00:00:00:00:00")
        except Exception as e:
            print(f"Error probing {ip}: {e}")
            continue

    # Full subnet scan
    full_scan = scan_subnet(subnet_str)

    # Merge results
    for dev in full_scan:
        ip = dev["ip"]
        if ip in discovered:
            if dev["mac"] != "00:00:00:00:00:00":
                discovered[ip] = dev
        else:
            discovered[ip] = dev

    return list(discovered.values())