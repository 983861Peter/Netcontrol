# core/anomaly_monitor.py
import threading
import time
from .device_comm import RouterDevice

class AnomalyMonitor:
    """Continuously checks routers for anomalies (like offline state)."""

    def __init__(self, routers: list[dict], interval: int = 30):
        self.routers = routers
        self.interval = interval
        self.running = False

    def check_router(self, router):
        device = RouterDevice(router["ip"])
        status = device.fetch_status()
        if not status["reachable"]:
            print(f"[ALERT] Router {router['ip']} is unreachable!")
        return status

    def start_monitoring(self):
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop_monitoring(self):
        self.running = False

    def _run(self):
        while self.running:
            for router in self.routers:
                self.check_router(router)
            time.sleep(self.interval)
