# discovery_engine.py
"""
Enhanced network discovery module with HTTP fingerprinting.

Performs:
- ICMP ping scan
- MAC and vendor lookup
- Optional HTTP(S) banner and title analysis

Dependencies:
    pip install requests beautifulsoup4
"""
import subprocess
import ipaddress
import platform
import re
from typing import List, Dict, Optional
import socket
import requests
from bs4 import BeautifulSoup
import threading
import json

CALLBACK_URL = "http://127.0.0.1:8080/auto_provision"
def ping_ip(ip: str) -> bool:
    """Ping a single IP to check if it’s alive."""
    cmd = ["ping", "-n", "1", "-w", "200", ip] if platform.system().lower() == "windows" else ["ping", "-c", "1", "-W", "1", ip]
    try:
        subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def get_mac(ip: str) -> str:
    """Try to get MAC address for an IP (Windows/Linux)."""
    try:
        output = subprocess.check_output(["arp", "-a"], text=True)
        pattern = re.compile(rf"{re.escape(ip)}.*?([0-9a-fA-F:.-]{{17}})")
        match = pattern.search(output)
        return match.group(1).replace("-", ":") if match else "Unknown"
    except Exception:
        return "Unknown"

def identify_model(mac: str) -> str:
    """Identify device model/vendor by MAC prefix."""
    oui_map = {
        "00:1A:1E": "Ruijie",
        "00:0C:43": "Cisco",
        "D8:EB:97": "TP-Link",
        "B0:4E:26": "D-Link",
        "C0:25:E9": "MikroTik",
        "C0:25:E9": "MikroTik",
        "F4:28:53": "Huawei",
        "44:D9:E7": "Ubiquiti",
    }
    prefix = mac.upper()[:8]
    for k, v in oui_map.items():
        if prefix.startswith(k):
            return v
    return "Unknown"

def http_fingerprint(ip: str) -> Dict[str, str]:
    """Attempt to detect device info via HTTP(S) banner or HTML title."""
    info = {"http_title": "N/A", "firmware": "N/A", "brand_hint": "Unknown"}
    for port in [80, 8080, 443]:
        url = f"http://{ip}:{port}" if port != 443 else f"https://{ip}"
        try:
            resp = requests.get(url, timeout=1, verify=False)
            title = BeautifulSoup(resp.text, "html.parser").title
            info["http_title"] = title.text.strip() if title else "No Title"
            server = resp.headers.get("Server", "")
            if "Mikrotik" in server or "RouterOS" in resp.text:
                info["brand_hint"] = "MikroTik"
            elif "TP-Link" in resp.text:
                info["brand_hint"] = "TP-Link"
            elif "D-Link" in resp.text:
                info["brand_hint"] = "D-Link"
            elif "Ruijie" in resp.text:
                info["brand_hint"] = "Ruijie"
            elif "Ubiquiti" in resp.text or "UniFi" in resp.text:
                info["brand_hint"] = "Ubiquiti"
            # Attempt firmware extraction
            firmware_match = re.search(r"Firmware[^\d]*(\d[\w\.\-_]+)", resp.text, re.I)
            if firmware_match:
                info["firmware"] = firmware_match.group(1)
            return info
        except requests.RequestException:
            continue
    return info

def detect_reset_state(info: Dict[str, str]) -> str:
    """
    Determine if a device is in factory-default state.
    Uses HTTP title, brand, and content inspection heuristics.
    """
    html = info.get("raw_html", "").lower()
    title = info.get("http_title", "").lower()

    reset_keywords = [
        "setup wizard", "quick setup", "default ssid",
        "login to router", "admin/admin", "factory default",
        "configure your router", "welcome to d-link", "initial configuration"
    ]

    # If any default phrase or title pattern matches, it’s likely reset
    for kw in reset_keywords:
        if kw in html or kw in title:
            return "reset"

    # No default indicators found; assume configured
    return "configured"

def trigger_auto_provision(device_info: Dict):
    """Call back to the controller API when a reset device is detected."""
    try:
        print(f"[CALLBACK] Triggering auto-provision for {device_info['ip']} ...")
        requests.post(CALLBACK_URL, json=device_info, timeout=3)
    except Exception as e:
        print(f"[CALLBACK ERROR] {e}")

def scan_network(subnet: str) -> List[Dict]:
    """Scan a subnet for reachable devices with HTTP banner analysis."""
    results = []
    net = ipaddress.ip_network(subnet, strict=False)
    print(f"[*] Starting enhanced scan on subnet {subnet} ...")

    for ip in net.hosts():
        ip_str = str(ip)
        if not ping_ip(ip_str):
            continue

        mac = get_mac(ip_str)
        vendor = identify_model(mac)
        http_info = http_fingerprint(ip_str)
        state = detect_reset_state(http_info)

        device_info = {
            "ip": ip_str,
            "mac": mac,
            "vendor": vendor,
            "brand_hint": http_info["brand_hint"],
            "http_title": http_info["http_title"],
            "firmware": http_info["firmware"],
            "status": "active",
            "config_state": state
        }

        results.append(device_info)

        if state == "reset":
            # Launch callback asynchronously to avoid blocking the scan
            threading.Thread(target=trigger_auto_provision, args=(device_info,)).start()

        print(f"[+] Found device: {device_info}")
        results.append(device_info)

    print(f"[*] Discovery complete. Found {len(results)} device(s).")
    return results