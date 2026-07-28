# core/device_comm.py
import subprocess
import paramiko
import time

class RouterDevice:
    """
    Handles communication with routers/APs.
    Can be extended to support various brands.
    """

    def __init__(self, ip_address, username="admin", password="admin", device_type="generic"):
        self.ip = ip_address
        self.username = username
        self.password = password
        self.device_type = device_type

    def ping(self) -> bool:
        """Check if device is reachable."""
        try:
            result = subprocess.run(
                ["ping", "-c", "1", self.ip],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2
            )
            return result.returncode == 0
        except Exception:
            return False

    def ssh_command(self, command: str) -> str:
        """Send SSH command to router."""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.ip, username=self.username, password=self.password, timeout=5)
            stdin, stdout, stderr = ssh.exec_command(command)
            output = stdout.read().decode()
            ssh.close()
            return output
        except Exception as e:
            return f"SSH Error: {e}"

    def configure(self, config_commands: list[str]) -> dict:
        """Apply a list of configuration commands."""
        results = {}
        for cmd in config_commands:
            results[cmd] = self.ssh_command(cmd)
            time.sleep(0.3)
        return results

    def fetch_status(self) -> dict:
        """Fetch basic status metrics from the device."""
        reachable = self.ping()
        return {
            "ip": self.ip,
            "reachable": reachable,
            "device_type": self.device_type,
            "last_checked": time.strftime("%Y-%m-%d %H:%M:%S")
        }
