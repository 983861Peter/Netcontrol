# credentials.py
"""
Simple credential provider module.

This module simulates a separate secure credentials source.
In a real system this would call a secret manager (Vault, AWS Secrets Manager, etc.).
Here we expose a function get_credentials(device_id) that returns a dict.
"""

_CREDENTIAL_STORE = {
    "router-001": {
        "username": "admin",
        "password": "admin123",
        "ssh_key": None
    },
    "router-002": {
        "username": "admin2",
        "password": "passw0rd!",
        "ssh_key": None
    }
}
ROUTER_USERNAME = "admin"
ROUTER_PASSWORD = "password123"

def get_credentials(device_id: str):
    """
    Return credentials for a device id, or None if not found.
    """
    return _CREDENTIAL_STORE.get(device_id)
import sys
print(sys.executable)
import netmiko
print(netmiko.__version__)  # Should print the version number