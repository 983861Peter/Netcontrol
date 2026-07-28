# core/config_manager.py
import json
import sqlite3
from datetime import datetime

DB_PATH = "network_system.db"

class ConfigManager:
    """Handles configuration backup and restore."""

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Ensure the configuration table exists."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS router_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            router_ip TEXT,
            config_json TEXT,
            timestamp TEXT
        )
        """)
        conn.commit()
        conn.close()

    def backup_config(self, router_ip: str, config: dict):
        """Save current router configuration."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT INTO router_configs (router_ip, config_json, timestamp) VALUES (?, ?, ?)",
                (router_ip, json.dumps(config), datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_latest_config(self, router_ip: str) -> dict | None:
        """Retrieve most recent backup for a router."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT config_json FROM router_configs WHERE router_ip=? ORDER BY timestamp DESC LIMIT 1", (router_ip,))
        row = c.fetchone()
        conn.close()
        return json.loads(row[0]) if row else None

    def restore_config(self, router_ip: str, device_comm):
        """Restore backed-up config to the router."""
        config = self.get_latest_config(router_ip)
        if not config:
            return {"error": "No backup found"}
        return device_comm.configure(config.get("commands", []))
