"""Fix SQLite database issues."""
import sqlite3
import os
from pathlib import Path

DB_FILE = "network_mgmt.db"  # Adjust if your DB file is named differently

def fix_db():
    if not os.path.exists(DB_FILE):
        print(f"{DB_FILE} not found, nothing to fix.")
        return
    
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)
        cursor = conn.cursor()
        
        # Check database integrity
        print("Checking database integrity...")
        result = cursor.execute("PRAGMA integrity_check").fetchone()
        print(f"Integrity check result: {result}")
        
        # Vacuum (cleanup and compact)
        print("Running VACUUM...")
        cursor.execute("VACUUM")
        
        # Analyze (update statistics)
        print("Running ANALYZE...")
        cursor.execute("ANALYZE")
        
        conn.commit()
        conn.close()
        print(f"✓ {DB_FILE} cleaned and optimized")
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == "__main__":
    fix_db()