# sync_engine.py
"""
Configuration Sync Engine
=========================
Periodically verifies that router configurations match database records.
If discrepancies are detected (e.g., factory reset), re-applies stored configs.
"""

import threading
import time
import json
import requests
from router_sim.dlink_adapter import DLinkAdapter

SYNC_INTERVAL = 120  # seconds between sync checks
API_BASE_URL = "http://127.0.0.1:8080"  # change to your FastAPI base URL


def fetch_routers_from_api():
    """Retrieve list of routers from FastAPI backend."""
    try:
        resp = requests.get(f"{API_BASE_URL}/routers")
        if resp.status_code == 200:
            return resp.json()
        print(f"[Sync] Failed to fetch routers. HTTP {resp.status_code}")
    except Exception as e:
        print(f"[Sync] API fetch error: {e}")
    return []


def compare_configs(local_config, remote_config):
    """Compare config dictionaries and return True if they differ."""
    return json.dumps(local_config, sort_keys=True) != json.dumps(remote_config, sort_keys=True)


def sync_device(router):
    """Sync one router's configuration with its stored record."""
    try:
        print(f"[Sync] Checking router {router['device_id']} ({router['ip']})...")
        adapter = DLinkAdapter(router["ip"], "admin", "")
        if not adapter.login():
            print(f"[Sync] Router {router['device_id']} unreachable.")
            return

        live_status = adapter.get_status()
        ssid_live = live_status.get("ssid", "")
        ssid_stored = router["config"].get("ssid", "")

        if ssid_live != ssid_stored:
            print(f"[Sync] Config mismatch on {router['device_id']} → Reapplying...")
            adapter.update_wifi(ssid_stored, router["config"].get("wifi_password", "changeme"))
            log_event(router["device_id"], "SYNC", f"SSID restored to {ssid_stored}")
        else:
            print(f"[Sync] {router['device_id']} is in sync.")
    except Exception as e:
        print(f"[Sync] Error syncing {router['device_id']}: {e}")


def log_event(device_id, event_type, message):
    """Send event log to API."""
    payload = {"device_id": device_id, "event": event_type, "message": message}
    try:
        requests.post(f"{API_BASE_URL}/logs", json=payload)
    except Exception as e:
        print(f"[Sync] Log send failed: {e}")


def sync_loop(interval=SYNC_INTERVAL):
    """Continuous configuration sync loop."""
    while True:
        routers = fetch_routers_from_api()
        for router in routers:
            sync_device(router)
        time.sleep(interval)


def start_sync_service(interval=SYNC_INTERVAL):
    """Start background sync thread."""
    thread = threading.Thread(target=sync_loop, args=(interval,), daemon=True)
    thread.start()
    print("[Sync] Background configuration sync started.")
