# device_profiles.py
ADOPTABLE_PROFILES = {
    "ubiquiti": {
        "vendors": ["Ubiquiti", "UBNT"],
        "ports": [80, 443],
        "signatures": [
            {"path": "/", "headers": {"X-UBNT-VERSION": "*"}},
            {"path": "/api/model", "json_key": "model"},
        ],
        "type": "wifi_ap"
    },
    "hikvision": {
        "vendors": ["Hikvision", "Hangzhou"],
        "ports": [80, 8080],
        "signatures": [
            {"path": "/ISAPI/System/deviceInfo", "xml_tag": "deviceName"},
        ],
        "type": "camera"
    },
    "dahua": {
        "vendors": ["Dahua"],
        "ports": [80],
        "signatures": [
            {"path": "/cgi-bin/guest/login", "body_contains": "Dahua"},
        ],
        "type": "camera"
    },
    "cambium": {
        "vendors": ["Cambium"],
        "ports": [80],
        "signatures": [
            {"path": "/cgi-bin/luci", "body_contains": "Cambium"},
        ],
        "type": "wireless"
    }
}