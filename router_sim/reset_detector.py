# reset_detector.py
from datetime import datetime
from .db import SessionLocal
from .models import Device
import hashlib
import json
from typing import Any

# thresholds & tuning
UPTIME_RESET_THRESHOLD = 5  # seconds (if uptime drops to < threshold we call it a reboot)
SUSPECT_SCORE_THRESHOLD = 2  # number of indicators required to declare reset

def hash_config(config_obj: dict) -> str:
    """Return stable hash string for a config dict (sorted). Be tolerant of non-serializable values."""
    if config_obj is None:
        config_obj = {}
    try:
        # use default=str so datetime/other objects won't raise TypeError
        txt = json.dumps(config_obj, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        # fallback to a stable repr if json.dumps fails
        txt = str(config_obj)
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()

def _to_seconds(val):
    """Normalize uptime-like values to a float (seconds) or return None."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(val)
    except Exception:
        return None

def evaluate_device_reset(dev: Device, scanned_info: dict) -> tuple[bool, dict[str, Any]]:
    """
    Given existing device DB object and freshly-scanned info, return:
    (is_reset_detected: bool, details: {indicator: value,...})
    scanned_info can include: ip, mac, uptime (secs), config (dict), hostname, credentials_ok (bool)
    """
    indicators = {}
    score = 0

    # 1) Uptime decreased or small after being large -> reboot
    new_uptime = _to_seconds(scanned_info.get("uptime"))
    old_uptime = _to_seconds(getattr(dev, "uptime", None))
    if new_uptime is not None and old_uptime is not None:
        if new_uptime < old_uptime:
            indicators["uptime_drop"] = {"old": old_uptime, "new": new_uptime}
            score += 1

    # 2) Uptime is small (near 0) but device was seen earlier
    if new_uptime is not None and new_uptime < UPTIME_RESET_THRESHOLD and getattr(dev, "last_seen", None):
        indicators["uptime_small_after_seen"] = {"uptime": new_uptime}
        score += 1

    # 3) IP changed significantly (different subnet / different IP)
    new_ip = scanned_info.get("ip")
    old_ip = getattr(dev, "ip_address", None)
    if new_ip and old_ip and new_ip != old_ip:
        indicators["ip_changed"] = {"old": old_ip, "new": new_ip}
        score += 1

    # 4) Hostname reverted or different (if provided)
    old_name = getattr(dev, "name", None)
    new_hostname = scanned_info.get("hostname")
    if new_hostname and new_hostname != old_name:
        indicators["hostname_changed"] = {"old": old_name, "new": new_hostname}
        score += 1

    # 5) Config hash mismatch
    new_conf = scanned_info.get("config")
    if new_conf is not None:
        try:
            new_hash = hash_config(new_conf)
            if getattr(dev, "last_config_hash", None) and new_hash != dev.last_config_hash:
                indicators["config_hash_mismatch"] = {"old": dev.last_config_hash, "new": new_hash}
                score += 1
        except Exception:
            # don't let hashing failures break detection
            pass

    # 6) Credentials invalid (scanner test)
    if scanned_info.get("credentials_ok") is False:
        indicators["credentials_invalid"] = True
        score += 1

    is_reset = score >= SUSPECT_SCORE_THRESHOLD
    return is_reset, {"score": score, "indicators": indicators}
