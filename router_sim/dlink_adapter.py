# adapters/dlink_adapter.py
"""
D-Link Router Adapter
=====================
Auto-detects whether Telnet or HTTP interface is available and uses the best option.
Supports:
- Login / authentication
- Get basic router status
- Update WiFi SSID and password
- Reboot router
"""

import requests
import telnetlib
import socket
from bs4 import BeautifulSoup
from contextlib import closing

try: import telnetlib TELNET_AVAILABLE = True except 
Exception: telnetlib = None TELNET_AVAILABLE = False
class DLinkAdapter:
    def __init__(self, host="192.168.0.1", username="admin", password=""):
        self.host = host
        self.username = username
        self.password = password
        self.protocol = None
        self.session = requests.Session()
        self.base_url = f"http://{self.host}"
        self.telnet_port = 23
        self.http_port = 80

    # ---------------------- Utility ---------------------- #
    def is_port_open(self, port, timeout=1):
        """Check if a TCP port is open."""
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((self.host, port)) == 0

    def detect_protocol(self):
        """Determine if Telnet or HTTP interface is available."""
        telnet_open = self.is_port_open(self.telnet_port)
        http_open = self.is_port_open(self.http_port)
        if telnet_open:
            self.protocol = "telnet"
        elif http_open:
            self.protocol = "http"
        else:
            self.protocol = None
        print(f"[DLinkAdapter] Detected protocol: {self.protocol}")
        return self.protocol

    # ---------------------- TELNET ---------------------- #
    def _telnet_login(self):
        """Login via Telnet."""
        try:
            self.tn = telnetlib.Telnet(self.host, self.telnet_port, timeout=5)
            self.tn.read_until(b"Login: ")
            self.tn.write(self.username.encode('ascii') + b"\n")
            self.tn.read_until(b"Password: ")
            self.tn.write(self.password.encode('ascii') + b"\n")
            return True
        except Exception as e:
            print(f"[Telnet] Login failed: {e}")
            return False

    def _telnet_exec(self, cmd):
        """Execute a Telnet command and read response."""
        try:
            self.tn.write(cmd.encode('ascii') + b"\n")
            output = self.tn.read_until(b"#", timeout=3)
            return output.decode(errors="ignore")
        except Exception as e:
            return str(e)

    def _telnet_close(self):
        """Close Telnet session."""
        try:
            self.tn.write(b"exit\n")
            self.tn.close()
        except Exception:
            pass

    # ---------------------- HTTP ---------------------- #
    def _http_login(self):
        """Login via HTTP."""
        try:
            login_data = {
                "username": self.username,
                "password": self.password
            }
            r = self.session.post(f"{self.base_url}/login.cgi", data=login_data, timeout=5)
            if r.status_code == 200:
                return True
            return False
        except Exception as e:
            print(f"[HTTP] Login error: {e}")
            return False

    # ---------------------- Common Methods ---------------------- #
    def login(self):
        """Try to login using the detected protocol."""
        if not self.protocol:
            self.detect_protocol()

        if self.protocol == "telnet":
            return self._telnet_login()
        elif self.protocol == "http":
            return self._http_login()
        else:
            print("[DLinkAdapter] No available protocol detected.")
            return False

    def get_status(self):
        """Retrieve router status info (SSID, etc.)."""
        if self.protocol == "telnet":
            try:
                resp = self._telnet_exec("wlctl ssid")
                return {"status": "online", "ssid": resp.strip()}
            except Exception as e:
                return {"error": f"Telnet status error: {e}"}

        elif self.protocol == "http":
            try:
                r = self.session.get(f"{self.base_url}/Status_Wireless.shtml", timeout=5)
                soup = BeautifulSoup(r.text, "html.parser")
                ssid_field = soup.find("input", {"name": "ssid"})
                ssid = ssid_field["value"] if ssid_field else "Unknown"
                return {"status": "online", "ssid": ssid}
            except Exception as e:
                return {"error": f"HTTP status error: {e}"}

        else:
            return {"error": "No communication protocol available."}

    def update_wifi(self, ssid, password):
        """Update SSID and WiFi password using available protocol."""
        if self.protocol == "telnet":
            try:
                self._telnet_exec(f"wlctl ssid {ssid}")
                self._telnet_exec(f"wlctl wpa_psk {password}")
                self._telnet_exec("save")
                return {"success": True, "protocol": "telnet"}
            except Exception as e:
                return {"success": False, "error": f"Telnet config error: {e}"}

        elif self.protocol == "http":
            try:
                data = {"ssid": ssid, "pskValue": password, "save": "Apply"}
                r = self.session.post(f"{self.base_url}/Wireless_Basic.asp", data=data, timeout=5)
                if r.status_code == 200:
                    return {"success": True, "protocol": "http"}
                return {"success": False, "error": f"HTTP {r.status_code}"}
            except Exception as e:
                return {"success": False, "error": f"HTTP config error: {e}"}

        else:
            return {"success": False, "error": "No available protocol"}

    def reboot(self):
        """Reboot router."""
        if self.protocol == "telnet":
            try:
                self._telnet_exec("reboot")
                return {"success": True, "protocol": "telnet"}
            except Exception as e:
                return {"success": False, "error": f"Telnet reboot error: {e}"}

        elif self.protocol == "http":
            try:
                r = self.session.get(f"{self.base_url}/reboot.cgi", timeout=5)
                if r.status_code == 200:
                    return {"success": True, "protocol": "http"}
                return {"success": False, "error": f"HTTP {r.status_code}"}
            except Exception as e:
                return {"success": False, "error": f"HTTP reboot error: {e}"}

        else:
            return {"success": False, "error": "No communication protocol available."}

def push_config(ip, credentials, config):
    """
    Applies new configuration settings to a D-Link router.
    """
    try:
        session = requests.Session()
        login_url = f"http://{ip}/login.cgi"
        data = {"username": credentials["user"], "password": credentials["pass"]}
        session.post(login_url, data=data)

        # Example: change SSID
        if "ssid" in config:
            payload = {"ssid": config["ssid"]}
            session.post(f"http://{ip}/WirelessSettings.cgi", data=payload)

        return {"status": "success", "applied": config}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

def fetch_status(ip, credentials):
    """
    Retrieve router stats (uptime, clients, etc.)
    """
    try:
        session = requests.Session()
        login_url = f"http://{ip}/login.cgi"
        data = {"username": credentials["user"], "password": credentials["pass"]}
        session.post(login_url, data=data)

        r = session.get(f"http://{ip}/Status_Wireless.shtml")
        soup = BeautifulSoup(r.text, "html.parser")
        ssid = soup.find("input", {"name": "ssid"})["value"]

        return {"ssid": ssid, "status": "online"}
    except Exception as e:
        return {"status": "offline", "error": str(e)}
