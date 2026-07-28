# event_engine.py
"""
Event Logging & Alert Engine
============================
Handles centralized event recording and alert dispatch for the
network management system. Integrates with FastAPI backend
and other system modules like discovery_service or sync_engine.

Features:
- Event logging with severity levels
- Alerts for anomalies or critical changes
- API fallback to local storage if backend is unreachable
"""

import os
import json
import time
import threading
import requests
from datetime import datetime

# Configuration
API_BASE_URL = "http://127.0.0.1:8080"  # Backend URL for /logs endpoint
LOCAL_LOG_FILE = "event_logs.json"
ALERT_LEVELS = ["INFO", "NOTICE", "WARNING", "ALERT", "CRITICAL"]

# --------------- Core Logging Engine --------------- #
def log_event(source, device_id, severity, message, to_api=True):
    """Log an event with optional API push."""
    timestamp = datetime.utcnow().isoformat() + "Z"
    event_data = {
        "timestamp": timestamp,
        "source": source,
        "device_id": device_id,
        "severity": severity,
        "message": message,
    }

    print(f"[{severity}] {timestamp} | {device_id} | {message}")

    # Try to send to API
    if to_api:
        try:
            r = requests.post(f"{API_BASE_URL}/logs", json=event_data, timeout=3)
            if r.status_code != 200:
                print(f"[EventEngine] API log failed ({r.status_code}), saving locally.")
                save_local_log(event_data)
        except Exception:
            print("[EventEngine] Backend unreachable, saving log locally.")
            save_local_log(event_data)
    else:
        save_local_log(event_data)


def save_local_log(entry):
    """Save log locally if API push fails."""
    if not os.path.exists(LOCAL_LOG_FILE):
        with open(LOCAL_LOG_FILE, "w") as f:
            json.dump([], f)

    with open(LOCAL_LOG_FILE, "r+") as f:
        logs = json.load(f)
        logs.append(entry)
        f.seek(0)
        json.dump(logs, f, indent=2)


# --------------- Alert Management --------------- #
ALERT_QUEUE = []

def raise_alert(source, device_id, severity, message):
    """Raise an alert event and queue for notifications."""
    if severity not in ALERT_LEVELS:
        severity = "WARNING"
    ALERT_QUEUE.append({
        "source": source,
        "device_id": device_id,
        "severity": severity,
        "message": message,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })
    log_event(source, device_id, severity, message)
    print(f"[AlertEngine] Queued alert: {severity} | {message}")


# --------------- Background Alert Dispatcher --------------- #
def alert_dispatch_loop(interval=60):
    """Periodically check for alerts and send notifications."""
    while True:
        if ALERT_QUEUE:
            pending = list(ALERT_QUEUE)
            ALERT_QUEUE.clear()
            for alert in pending:
                dispatch_alert(alert)
        time.sleep(interval)


def dispatch_alert(alert):
    """Send alert to notification channel (future-ready)."""
    try:
        # In production, this could send to email, webhook, or dashboard socket
        print(f"[Notify] Alert from {alert['device_id']} | {alert['severity']} | {alert['message']}")
        # Placeholder: You can add webhook/email integration here later
    except Exception as e:
        print(f"[AlertEngine] Failed to dispatch alert: {e}")


def start_alert_engine(interval=60):
    """Start the alert engine in the background."""
    thread = threading.Thread(target=alert_dispatch_loop, args=(interval,), daemon=True)
    thread.start()
    print("[AlertEngine] Background alert service started.")
