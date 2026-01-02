"""
WiFi Sniffer Configuration
==========================
Centralized configuration for the WiFi Sniffer application.
"""

import os
from pathlib import Path

# ============== OpenWrt Configuration ==============
OPENWRT_HOST = "192.168.1.1"
OPENWRT_USER = "root"
OPENWRT_PASSWORD = None  # None = no password (OpenWrt default), or set "your_password"
SSH_KEY_PATH = None  # Set path to SSH key if needed
SSH_PORT = 22

# ============== Interface Mapping ==============
# Default values - will be auto-detected on connection
DEFAULT_INTERFACES = {
    "2G": "ath0",
    "5G": "ath2",
    "6G": "ath1"
}

# UCI wireless interface mapping (OpenWrt) - will be auto-detected
DEFAULT_UCI_WIFI_MAP = {
    "2G": "wifi0",  # 2.4G radio
    "5G": "wifi2",  # 5G radio
    "6G": "wifi1"   # 6G radio
}

# ============== Download Configuration ==============
DOWNLOADS_FOLDER = str(Path.home() / "Downloads")

# ============== Server Configuration ==============
SERVER_PORT = int(os.environ.get('FLASK_PORT', 5000))
SERVER_HOST = '0.0.0.0'
DEBUG_MODE = True

# ============== Channel Configuration ==============
CHANNELS = {
    "2G": list(range(1, 15)),  # Channels 1-14
    "5G": [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165],
    "6G": [1, 5, 9, 13, 17, 21, 25, 29, 33, 37, 41, 45, 49, 53, 57, 61, 65, 69, 73, 77, 81, 85, 89, 93, 97, 101, 105, 109, 113, 117, 121, 125, 129, 133, 137, 141, 145, 149, 153, 157, 161, 165, 169, 173, 177, 181, 185, 189, 193, 197, 201, 205, 209, 213, 217, 221, 225, 229, 233]
}

BANDWIDTHS = {
    "2G": ["HT20", "HT40"],
    "5G": ["EHT20", "EHT40", "EHT80", "EHT160"],
    "6G": ["EHT20", "EHT40", "EHT80", "EHT160", "EHT320"]
}

# ============== Cache Configuration ==============
CONNECTION_CACHE_TTL = 5  # seconds
INTERFACE_CACHE_TTL = 300  # 5 minutes
STATUS_UPDATE_INTERVAL = 3  # seconds

# ============== SSH Connection Pool ==============
SSH_POOL_SIZE = 3
SSH_CONNECT_TIMEOUT = 10
SSH_COMMAND_TIMEOUT = 30
