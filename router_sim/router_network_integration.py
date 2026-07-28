# router_network_integration.py
import sys
from router_sim.router_sim import Router
from netmiko import ConnectHandler
# from napalm import get_network_driver   # uncomment if you want NAPALM too

class RouterWithNetmiko(Router):
    def __init__(self, device_type="cisco_ios", ip="192.168.1.1"):
        super().__init__()
        self.device_params = {
            "device_type": device_type,
            "host": ip,
            "username": self.username,
            "password": self.password,
        }

    def push_config(self, commands):
        """
        Push configuration commands to a real router via SSH using Netmiko.
        commands = list of CLI commands
        """
        print(f"\nConnecting to {self.device_params['host']}...\n")
        try:
            connection = ConnectHandler(**self.device_params)
            output = connection.send_config_set(commands)
            print(output)
            connection.disconnect()
        except Exception as e:
            print(f"Connection failed: {e}")

# Example usage
if __name__ == "__main__":
    router = RouterWithNetmiko(ip="192.168.1.10")  # Example router IP
    router.show_config()

    # Push real commands (if connected to a Cisco/Juniper/etc. device)
    router.push_config([
        "hostname MyRouter",
        "interface GigabitEthernet0/0",
        "ip address 192.168.1.2 255.255.255.0",
        "no shutdown"
    ])
