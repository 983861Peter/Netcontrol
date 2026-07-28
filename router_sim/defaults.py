# defaults.py
# DEFAULT_IPS_BY_SUBNET = {
#     "192.168.1.0/24": [
#         "192.168.1.20",   # Ubiquiti
#         "192.168.1.64",   # Hikvision
#         "192.168.1.108",  # Dahua
#         "192.168.1.1",    # Generic (Aruba, Ruckus, etc.)
#         "192.168.1.2",
#     ]
# },


# 1. Common Default IP Addresses by Vendor

# | Vendor | Device Type | Default IP | Notes |
# |-------|-------------|-----------|------|
# | **Ubiquiti** | UniFi AP / Switch / Gateway | `192.168.1.20` | HTTP/SSH enabled; requires adoption |
# | **Hikvision** | IP Camera / NVR | `192.168.1.64` | Often responds to ONVIF/ISAPI |
# | **Dahua** | IP Camera / NVR | `192.168.1.108` | Web UI on port 80 |
# | **TP-Link** | Business AP / Switch | `192.168.0.254` or `192.168.1.254` | Varies by model |
# | **MikroTik** | RouterOS Devices | `192.168.88.1` | LAN IP; WinBox enabled |
# | **Cisco Meraki** | MR/MX/MS (if unclaimed) | `192.168.128.128` | Only during initial setup |
# | **Aruba (HPE)** | Instant AP | `192.168.1.1` or DHCP-only | Some models use `192.168.10.1` |
# | **Cambium** | PTP/PMP Radios | `192.168.0.1` | Web UI on port 80 |
# | **Axis Communications** | Network Cameras | `192.168.0.90` | Uses AXIS IP Utility, but responds to HTTP |
# | **Bosch** | Security Cameras | `192.168.100.100` | Often requires Bosch Config Manager |
# | **EnGenius** | Cloud APs | `192.168.0.1` | Web UI accessible |
# | **Ruckus** | ZoneFlex APs | `192.168.0.1` or `192.168.10.1` | Varies by series |
# | **Netgear** | Business Switches/APs | `192.168.0.239` | ProSAFE line |

# >  **Note**: Most vendors use **`192.168.1.x`**, **`192.168.0.x`**, or **`192.168.88.x`** subnets by default.



# defaults.py
DEFAULT_IPS_BY_SUBNET = {
    "192.168.1.0/24": [
        "192.168.1.20",   # Ubiquiti
        "192.168.1.64",   # Hikvision
        "192.168.1.108",  # Dahua
        "192.168.1.1",    # Generic (Aruba, Ruckus, etc.)
        "192.168.1.254",  # TP-Link
    ],
    "192.168.0.0/24": [
        "192.168.0.1",    # Cambium, EnGenius, Ruckus
        "192.168.0.90",   # Axis
        "192.168.0.239",  # Netgear
        "192.168.0.254",  # TP-Link
    ],
    "192.168.88.0/24": [
        "192.168.88.1",   # MikroTik
    ],
    "192.168.128.0/24": [
        "192.168.128.128", # Cisco Meraki (setup mode)
    ],
    "192.168.100.0/24": [
        "192.168.100.100", # Bosch
    ],
    "192.168.10.0/24": [
        "192.168.10.1",    # Aruba IAP, Ruckus
    ]
}