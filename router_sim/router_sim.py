# router_sim.py
"""
Router simulator (updated)

Features (enhanced):
- Keeps local JSON store (devices.json) and backups/
- Optional sync with FastAPI controller (API_BASE). If API unreachable, operates locally.
- Simulates DHCP leases and basic network events in background threads per device.
- CLI preserved: create/view/update/delete devices, push/backup/restore configs, factory reset.
- Watches manual_changes.json for external edits and applies them dynamically.
- Posts logs and DHCP assignments to API when available (best-effort).
"""

import json
import os
import threading
import time
import requests
import traceback
import random
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import uuid

# -----------------------
# Config
# -----------------------
DEVICES_FILE = "devices.json"
MANUAL_CHANGES_FILE = "manual_changes.json"
BACKUP_DIR = "backups"
LOGS_FILE = "sim_logs.json"

POLL_INTERVAL = 2.0  # seconds for manual_changes polling
DHCP_SIM_INTERVAL = 12.0  # secs between DHCP batches per device (sim)
EVENT_SIM_INTERVAL = 18.0  # secs between event logs per device

# API controller base URL (set to empty string to disable)
API_BASE = os.environ.get("RF_API_BASE", "").rstrip("/")  # e.g., "http://127.0.0.1:8000"

# Time format helper
def now_ts():
    return datetime.utcnow().isoformat() + "Z"


# -----------------------
# Utilities: storage
# -----------------------
def ensure_store():
    if not os.path.exists(DEVICES_FILE):
        with open(DEVICES_FILE, "w") as f:
            json.dump({}, f, indent=2)
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    if not os.path.exists(MANUAL_CHANGES_FILE):
        with open(MANUAL_CHANGES_FILE, "w") as f:
            json.dump({}, f, indent=2)
    if not os.path.exists(LOGS_FILE):
        with open(LOGS_FILE, "w") as f:
            json.dump([], f, indent=2)


def load_devices() -> Dict[str, Any]:
    with open(DEVICES_FILE, "r") as f:
        try:
            return json.load(f)
        except Exception:
            return {}


def save_devices(devices: Dict[str, Any]):
    with open(DEVICES_FILE, "w") as f:
        json.dump(devices, f, indent=2)


def append_log_local(entry: Dict[str, Any]):
    # store rolling logs in JSON
    try:
        with open(LOGS_FILE, "r") as f:
            arr = json.load(f)
    except Exception:
        arr = []
    arr.append(entry)
    # keep last 1000
    arr = arr[-1000:]
    with open(LOGS_FILE, "w") as f:
        json.dump(arr, f, indent=2)


# -----------------------
# API helpers (best-effort)
# -----------------------
def api_post(path: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not API_BASE:
        return None
    try:
        url = API_BASE + path
        r = requests.post(url, json=payload, timeout=6)
        if r.status_code in (200, 201):
            try:
                return r.json()
            except Exception:
                return {"status_text": r.text}
        else:
            # return error info
            return {"__error__": r.status_code, "text": r.text}
    except Exception as e:
        return None


def api_get(path: str) -> Optional[Dict[str, Any]]:
    if not API_BASE:
        return None
    try:
        url = API_BASE + path
        r = requests.get(url, timeout=6)
        if r.status_code == 200:
            try:
                return r.json()
            except Exception:
                return {"text": r.text}
        else:
            return {"__error__": r.status_code, "text": r.text}
    except Exception:
        return None


def api_available() -> bool:
    if not API_BASE:
        return False
    try:
        r = requests.get(API_BASE + "/", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# -----------------------
# RouterSim class (local simulation)
# -----------------------
class RouterSim:
    def __init__(self, device_id: str, ip: str, model: str = "SimRouter-1"):
        self.device_id = device_id
        self.ip = ip
        self.model = model
        self.status = "online"
        self.api_id: Optional[Any] = None  # id assigned by controller API when synced
        # default config
        self.config = {
            "hostname": device_id,
            "interfaces": {
                "lan": {"ip": ip, "netmask": "255.255.255.0"},
                "wan": {"ip": None, "netmask": None}
            },
            "dhcp": {"enabled": True, "range_start": "192.168.1.100", "range_end": "192.168.1.200"},
            "ssid": "DefaultSSID",
            "wifi_password": "changeme"
        }
        self.config_history = []  # list of (ts, config)
        self._record_config("initial")
        # simulation threads
        self._dhcp_thread: Optional[threading.Thread] = None
        self._event_thread: Optional[threading.Thread] = None
        self._running = False

    def _record_config(self, note=""):
        self.config_history.append({"ts": now_ts(), "note": note, "config": deepcopy(self.config)})

    def to_dict(self):
        return {
            "device_id": self.device_id,
            "ip": self.ip,
            "model": self.model,
            "status": self.status,
            "api_id": self.api_id,
            "config": self.config,
            "config_history": self.config_history
        }

    def apply_config(self, new_conf: Dict[str, Any], note: str = "applied"):
        changed = False
        for k, v in new_conf.items():
            if k not in self.config or self.config[k] != v:
                self.config[k] = v
                changed = True
        if changed:
            self._record_config(note)
            # attempt to notify controller
            try:
                if api_available():
                    # prefer a "config fragment" endpoint if exists
                    api_post(f"/devices/{self.device_id}/config", {"fragment": new_conf, "note": note})
            except Exception:
                pass
        return changed

    def backup_config(self):
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        fname = f"{BACKUP_DIR}/{self.device_id}_backup_{ts}.json"
        payload = {"device_id": self.device_id, "ts": now_ts(), "config": deepcopy(self.config)}
        with open(fname, "w") as f:
            json.dump(payload, f, indent=2)
        # attempt to store backup to controller (best-effort)
        try:
            if api_available():
                api_post(f"/devices/{self.device_id}/backup", {"note": "auto-backup", "config": payload})
        except Exception:
            pass
        return fname

    def restore_config(self, backup_file: str):
        if not os.path.exists(backup_file):
            raise FileNotFoundError("Backup file not found.")
        with open(backup_file, "r") as f:
            payload = json.load(f)
        if payload.get("device_id") != self.device_id:
            raise ValueError("Backup file does not belong to this device.")
        self.config = payload["config"]
        self._record_config(f"restored from {os.path.basename(backup_file)}")
        # notify controller
        try:
            if api_available():
                api_post(f"/devices/{self.device_id}/config", {"fragment": self.config, "note": "restore"})
        except Exception:
            pass

    def factory_reset(self):
        self.config = {
            "hostname": self.device_id,
            "interfaces": {"lan": {"ip": self.ip, "netmask": "255.255.255.0"}, "wan": {"ip": None, "netmask": None}},
            "dhcp": {"enabled": True, "range_start": "192.168.1.100", "range_end": "192.168.1.200"},
            "ssid": "DefaultSSID",
            "wifi_password": "changeme"
        }
        self._record_config("factory_reset")
        self.status = "online"
        # clear local DHCP leases for this device in local store (the DeviceStore manages persistence)
        return True

    def info(self):
        return {
            "device_id": self.device_id,
            "ip": self.ip,
            "model": self.model,
            "status": self.status,
            "hostname": self.config.get("hostname"),
            "ssid": self.config.get("ssid")
        }

    # --------------------
    # Simulation: DHCP & Events
    # --------------------
    def _dhcp_cycle(self):
        """
        Loop that simulates DHCP activity. For each cycle we:
        - optionally create a few leases locally
        - attempt to post to controller /dhcp/assign if API available
        """
        while self._running:
            try:
                dhcp = self.config.get("dhcp", {})
                if dhcp.get("enabled", True):
                    # create 0..3 leases per cycle
                    new_leases = []
                    count = 0
                    for i in range(random.randint(0, 3)):
                        ip = self._random_pool_ip(dhcp.get("range_start"), dhcp.get("range_end"))
                        mac = self._random_mac()
                        expiry = (datetime.utcnow() + timedelta(minutes=random.randint(10, 180))).isoformat() + "Z"
                        lease = {"ip": ip, "mac": mac, "expiry": expiry, "ts": now_ts()}
                        new_leases.append(lease)
                        count += 1
                        # try to notify controller DHCP endpoint (best effort)
                        try:
                            if api_available():
                                api_post("/dhcp/assign", {"router_id": self.device_id, "ip_address": ip, "mac_address": mac, "lease_duration_minutes": 60})
                                # note: some controllers expect numeric router IDs; we keep best-effort
                        except Exception:
                            pass
                    if count:
                        append_log_local({"ts": now_ts(), "device": self.device_id, "event": f"Assigned {count} DHCP leases (simulated)", "leases": new_leases})
                # sleep until next dhcp cycle
                time.sleep(DHCP_SIM_INTERVAL)
            except Exception as e:
                append_log_local({"ts": now_ts(), "device": self.device_id, "event": "dhcp_cycle_error", "error": repr(e)})
                time.sleep(5)

    def _event_cycle(self):
        """
        Periodically generate simulated events: network load, latency, reboots (rare).
        """
        while self._running:
            try:
                # basic simulated metrics
                load = random.randint(1, 98)
                latency = round(random.uniform(1.0, 120.0), 2)
                msg = f"simulated load={load}%, latency={latency}ms"
                append_log_local({"ts": now_ts(), "device": self.device_id, "event": "metric", "message": msg})
                # attempt to post event to controller logs endpoint
                try:
                    if api_available():
                        # Best-effort: try multiple potential endpoints depending on backend
                        if API_BASE:
                            # try /logs/{router_id} POST if exists
                            api_post(f"/logs/{self.device_id}", {"timestamp": now_ts(), "message": msg, "alert_level": "info"})
                            # or /devices/{device_id}/events? depending on API
                            api_post(f"/devices/{self.device_id}/events", {"message": msg, "level": "info"})
                except Exception:
                    pass

                # small chance of a reboot/reset (rare)
                if random.random() < 0.02:
                    append_log_local({"ts": now_ts(), "device": self.device_id, "event": "reboot", "message": "Simulated reboot"})
                    self.factory_reset()
                    # notify controller reset endpoint if exists
                    try:
                        if api_available():
                            api_post(f"/router/{self.device_id}/reset", {"message": "simulated reboot"})
                            api_post(f"/devices/{self.device_id}/factory-reset", {})
                    except Exception:
                        pass
                time.sleep(EVENT_SIM_INTERVAL)
            except Exception as e:
                append_log_local({"ts": now_ts(), "device": self.device_id, "event": "event_cycle_error", "error": repr(e)})
                time.sleep(5)

    def _random_mac(self):
        return "AA:BB:%02X:%02X:%02X" % (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

    def _random_pool_ip(self, start: str, end: str):
        # simple conversion: assume /24 like pools; works for typical ranges
        try:
            s = list(map(int, start.split(".")))
            e = list(map(int, end.split(".")))
            # iterate middle octet assumption
            if s[0:3] == e[0:3]:
                low = s[3]
                high = e[3]
                if low > high:
                    low, high = high, low
                return f"{s[0]}.{s[1]}.{s[2]}.{random.randint(low, high)}"
            else:
                # fallback: return start
                return start
        except Exception:
            return start

    def start_simulation(self):
        if self._running:
            return
        self._running = True
        self._dhcp_thread = threading.Thread(target=self._dhcp_cycle, daemon=True)
        self._event_thread = threading.Thread(target=self._event_cycle, daemon=True)
        self._dhcp_thread.start()
        self._event_thread.start()
        append_log_local({"ts": now_ts(), "device": self.device_id, "event": "simulation_started"})
        # notify controller if possible
        try:
            if api_available():
                api_post("/events", {"message": f"Simulation started for {self.device_id}"})
        except Exception:
            pass

    def stop_simulation(self):
        if not self._running:
            return
        self._running = False
        append_log_local({"ts": now_ts(), "device": self.device_id, "event": "simulation_stopped"})
        # threads are daemon so will stop


# -----------------------
# Device store (local JSON + optional API sync)
# -----------------------
class DeviceStore:
    def __init__(self):
        ensure_store()
        self.devices: Dict[str, RouterSim] = {}
        raw = load_devices()
        for dev_id, obj in raw.items():
            r = RouterSim(dev_id, obj.get("ip", "0.0.0.0"), obj.get("model", "SimRouter-1"))
            r.config = obj.get("config", r.config)
            r.config_history = obj.get("config_history", r.config_history)
            r.status = obj.get("status", "online")
            r.api_id = obj.get("api_id")
            self.devices[dev_id] = r
        # active simulation handles
        self._simulators: Dict[str, RouterSim] = self.devices.copy()

    def persist(self):
        data = {did: r.to_dict() for did, r in self.devices.items()}
        save_devices(data)

    def add_device(self, device_id: str, ip: str, model="SimRouter-1"):
        if device_id in self.devices:
            raise ValueError("Device already exists.")
        r = RouterSim(device_id, ip, model)
        self.devices[device_id] = r
        # attempt to register with controller if available
        try:
            if api_available():
                payload = {"device_id": device_id, "ip": ip, "model": model}
                res = api_post("/routers", payload) or api_post("/devices", payload)
                # controller might return assigned id or info
                if res and isinstance(res, dict):
                    # try to find an id; common keys: id, device_id, router_id
                    for key in ("id", "device_id", "router_id", "api_id"):
                        if key in res:
                            r.api_id = res[key]
                            break
                    # some controllers return message only — ignore
        except Exception:
            pass
        self.persist()
        return r

    def remove_device(self, device_id: str):
        if device_id not in self.devices:
            raise ValueError("Device not found.")
        # attempt to notify controller
        try:
            if api_available():
                api_post(f"/routers/{device_id}/delete", {"device_id": device_id})
                api_post(f"/devices/{device_id}", {})  # maybe DELETE on /devices/{id}
        except Exception:
            pass
        del self.devices[device_id]
        self.persist()

    def get(self, device_id: str) -> Optional[RouterSim]:
        return self.devices.get(device_id)

    def list_devices(self):
        return [r.info() for r in self.devices.values()]

    def start_sim_for(self, device_id: str):
        r = self.get(device_id)
        if not r:
            raise ValueError("Not found.")
        r.start_simulation()
        self.persist()

    def stop_sim_for(self, device_id: str):
        r = self.get(device_id)
        if not r:
            raise ValueError("Not found.")
        r.stop_simulation()
        self.persist()


# -----------------------
# Manual changes watcher
# -----------------------
class ManualChangeWatcher(threading.Thread):
    def __init__(self, store: DeviceStore, poll_interval=POLL_INTERVAL):
        super().__init__(daemon=True)
        self.store = store
        self.poll_interval = poll_interval
        self._last_mtime = None

    def run(self):
        while True:
            try:
                mtime = os.path.getmtime(MANUAL_CHANGES_FILE)
            except FileNotFoundError:
                time.sleep(self.poll_interval)
                continue
            if self._last_mtime is None:
                self._last_mtime = mtime
            if mtime != self._last_mtime:
                self._last_mtime = mtime
                self.apply_manual_changes()
            time.sleep(self.poll_interval)

    def apply_manual_changes(self):
        try:
            with open(MANUAL_CHANGES_FILE, "r") as f:
                payload = json.load(f)
        except Exception as e:
            append_log_local({"ts": now_ts(), "event": "manual_watch_read_error", "error": repr(e)})
            return
        # payload expected: { "device_id": { <config_fragment> }, ... }
        applied_any = False
        for dev_id, conf in payload.items():
            r = self.store.get(dev_id)
            if not r:
                append_log_local({"ts": now_ts(), "event": "manual_watch_no_device", "device": dev_id})
                continue
            changed = r.apply_config(conf, note="manual_change_file")
            if changed:
                append_log_local({"ts": now_ts(), "device": dev_id, "event": "manual_change_applied"})
                applied_any = True
        if applied_any:
            self.store.persist()


# -----------------------
# CLI
# -----------------------
def print_menu():
    print("\nRouter Simulator Menu")
    print("1) List devices")
    print("2) Add device")
    print("3) Remove device")
    print("4) Show device details")
    print("5) Push config (apply config fragment)")
    print("6) Backup config")
    print("7) Restore config from backup")
    print("8) Factory reset device")
    print("9) Edit device config manually (interactive input)")
    print("10) View config history")
    print("11) Open manual_changes.json sample (to edit externally)")
    print("12) Start simulation for device")
    print("13) Stop simulation for device")
    print("14) Sync store to API controller (best-effort)")
    print("15) Show API status")
    print("0) Exit")


def interactive():
    store = DeviceStore()
    watcher = ManualChangeWatcher(store)
    watcher.start()

    print("Router Simulator started. Manual changes are read from", MANUAL_CHANGES_FILE)
    while True:
        print_menu()
        choice = input("Select option: ").strip()
        if choice == "1":
            devices = store.list_devices()
            print(json.dumps(devices, indent=2))
        elif choice == "2":
            did = input("Device ID (e.g., router-001): ").strip()
            ip = input("IP address: ").strip()
            model = input("Model name (optional): ").strip() or "SimRouter-1"
            try:
                store.add_device(did, ip, model)
                print("Added", did)
            except Exception as e:
                print("Error:", e)
        elif choice == "3":
            did = input("Device ID to remove: ").strip()
            try:
                store.remove_device(did)
                print("Removed", did)
            except Exception as e:
                print("Error:", e)
        elif choice == "4":
            did = input("Device ID: ").strip()
            r = store.get(did)
            if not r:
                print("Not found.")
            else:
                print(json.dumps(r.to_dict(), indent=2))
        elif choice == "5":
            did = input("Device ID: ").strip()
            r = store.get(did)
            if not r:
                print("Not found.")
                continue
            print("Enter JSON fragment to apply (example: {\"ssid\": \"MyNet\", \"wifi_password\": \"newpass\"})")
            frag = input("Fragment JSON: ").strip()
            try:
                frag_obj = json.loads(frag)
            except Exception as e:
                print("Invalid JSON:", e)
                continue
            changed = r.apply_config(frag_obj, note="cli_push")
            if changed:
                store.persist()
                print("Config applied.")
            else:
                print("No changes detected.")
        elif choice == "6":
            did = input("Device ID: ").strip()
            r = store.get(did)
            if not r:
                print("Not found.")
                continue
            fname = r.backup_config()
            print("Backup saved to", fname)
        elif choice == "7":
            did = input("Device ID: ").strip()
            r = store.get(did)
            if not r:
                print("Not found.")
                continue
            bf = input("Backup file path: ").strip()
            try:
                r.restore_config(bf)
                store.persist()
                print("Restored from", bf)
            except Exception as e:
                print("Error restoring:", e)
        elif choice == "8":
            did = input("Device ID: ").strip()
            r = store.get(did)
            if not r:
                print("Not found.")
                continue
            confirm = input("Confirm factory reset? This wipes custom config (yes/no): ").strip().lower()
            if confirm == "yes":
                r.factory_reset()
                store.persist()
                print("Factory reset performed.")
            else:
                print("Cancelled.")
        elif choice == "9":
            did = input("Device ID: ").strip()
            r = store.get(did)
            if not r:
                print("Not found.")
                continue
            print("Current config:")
            print(json.dumps(r.config, indent=2))
            print("Enter JSON fragment to merge into config (e.g., change SSID or DHCP range):")
            frag = input("Fragment JSON: ").strip()
            try:
                frag_obj = json.loads(frag)
            except Exception as e:
                print("Invalid JSON:", e)
                continue
            r.apply_config(frag_obj, note="manual_cli_edit")
            store.persist()
            print("Manual edit applied.")
        elif choice == "10":
            did = input("Device ID: ").strip()
            r = store.get(did)
            if not r:
                print("Not found.")
                continue
            print("Config history (most recent first):")
            for entry in reversed(r.config_history[-10:]):
                print("----")
                print("ts:", entry["ts"], "note:", entry.get("note"))
                print(json.dumps(entry["config"], indent=2))
        elif choice == "11":
            sample = {
                "router-001": {
                    "ssid": "ManualNet",
                    "wifi_password": "manual1234"
                }
            }
            print("Manual changes file is", MANUAL_CHANGES_FILE)
            with open(MANUAL_CHANGES_FILE, "w") as f:
                json.dump(sample, f, indent=2)
            print("Wrote sample to manual_changes.json. Edit it externally and save; watcher will apply changes.")
        elif choice == "12":
            did = input("Device ID: ").strip()
            try:
                store.start_sim_for(did)
                print("Simulation started for", did)
            except Exception as e:
                print("Error:", e)
        elif choice == "13":
            did = input("Device ID: ").strip()
            try:
                store.stop_sim_for(did)
                print("Simulation stopped for", did)
            except Exception as e:
                print("Error:", e)
        elif choice == "14":
            # sync local devices to controller (best-effort)
            try:
                print("Attempting to sync devices to API at", API_BASE or "<disabled>")
                if not api_available():
                    print("API is not reachable.")
                else:
                    for did, r in store.devices.items():
                        payload = {"device_id": r.device_id, "ip": r.ip, "model": r.model}
                        res = api_post("/routers", payload) or api_post("/devices", payload)
                        print("Synced", did, "->", res)
                        append_log_local({"ts": now_ts(), "device": did, "event": "sync_attempt", "result": res})
                    print("Sync attempt complete.")
            except Exception as e:
                print("Sync error:", e)
        elif choice == "15":
            print("API base:", API_BASE or "<disabled>")
            print("API reachable:", api_available())
        elif choice == "0":
            print("Exiting.")
            # stop all sims
            for r in store.devices.values():
                r.stop_simulation()
            break
        else:
            print("Unknown option.")


if __name__ == "__main__":
    # ensure store files exist
    ensure_store()
    # start CLI
    interactive()
