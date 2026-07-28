# router_sim/__init__.py
"""
router_sim package initializer.
This package contains modules for:
- Router simulation and API logic
- Device communication adapters
- Network discovery and sync engines
- Authentication and user management
"""

__version__ = "1.0.0"
__author__ = "Your Name"

# Optional: expose key modules at package level
from .router_api import app
from .router_sim import RouterSim, DeviceStore
from .models import Base
from .db import engine
from .dlink_adapter import DLinkAdapter
__all__ = ["app", "RouterSim", "DeviceStore", "DLinkAdapter"]