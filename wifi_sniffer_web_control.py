"""
WiFi Sniffer Web Control Panel
================================
Web-based control panel for capturing WiFi sniffer logs from OpenWrt system.
Supports 2.4G, 5G, and 6G band capture with start/stop controls.

Author: AI Assistant
Version: 1.0
"""

from flask import Flask, render_template_string, request, jsonify, send_file
import paramiko
import threading
import os
import time
import re
from datetime import datetime
from pathlib import Path
import socket

app = Flask(__name__)

# ============== Configuration ==============
OPENWRT_HOST = "192.168.1.1"
OPENWRT_USER = "root"
OPENWRT_PASSWORD = None  # None = no password (OpenWrt default), or set "your_password"
SSH_KEY_PATH = None  # Set path to SSH key if needed
SSH_PORT = 22

# Interface mapping (default values - will be auto-detected on connection)
INTERFACES = {
    "2G": "ath0",
    "5G": "ath2", 
    "6G": "ath1"
}

# UCI wireless interface mapping (OpenWrt) - will be auto-detected
UCI_WIFI_MAP = {
    "2G": "wifi0",  # 2.4G radio
    "5G": "wifi2",  # 5G radio
    "6G": "wifi1"   # 6G radio
}

# Auto-detection status
interface_detection_status = {
    "detected": False,
    "last_detection": None,
    "detection_method": None,
    "detected_mapping": None
}

# Download folder (Windows Downloads)
DOWNLOADS_FOLDER = str(Path.home() / "Downloads")

# ============== Global State ==============
capture_status = {
    "2G": {"running": False, "start_time": None, "packets": 0},
    "5G": {"running": False, "start_time": None, "packets": 0},
    "6G": {"running": False, "start_time": None, "packets": 0}
}

capture_threads = {}
ssh_connections = {}

# ============== File Split Configuration ==============
# Split capture files by size to prevent oversized files during long captures
file_split_config = {
    "enabled": False,           # Enable/disable file splitting
    "size_mb": 200,             # Split file size in MB (default 200MB)
}

# ============== Channel Configuration ==============
# Default channels for each band
channel_config = {
    "2G": {"channel": 6, "bandwidth": "HT40"},
    "5G": {"channel": 36, "bandwidth": "EHT160"},
    "6G": {"channel": 37, "bandwidth": "EHT320"}
}

# Available channels
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

def detect_interface_mapping():
    """
    Auto-detect the interface mapping by querying the OpenWrt device.
    This function detects which athX interface corresponds to which band (2G/5G/6G)
    by checking the frequency/channel information from iwconfig and uci config.
    """
    global INTERFACES, UCI_WIFI_MAP, interface_detection_status
    
    print("[DETECT] Starting interface auto-detection...")
    
    try:
        # Method 1: Use iwconfig to get frequency for each interface
        # iwconfig output shows frequency which tells us the band
        success, stdout, stderr = run_ssh_command(
            "iwconfig 2>/dev/null | grep -E '^ath[0-2]|Frequency'",
            timeout=10
        )
        
        if success and stdout.strip():
            # Parse iwconfig output to map interfaces to bands
            detected = {}
            lines = stdout.strip().split('\n')
            current_iface = None
            
            for line in lines:
                line = line.strip()
                if line.startswith('ath'):
                    current_iface = line.split()[0]
                elif 'Frequency' in line and current_iface:
                    # Extract frequency, e.g., "Frequency:2.437 GHz" or "Frequency:5.18 GHz"
                    import re
                    freq_match = re.search(r'Frequency[:\s]*(\d+\.?\d*)', line)
                    if freq_match:
                        freq = float(freq_match.group(1))
                        if freq < 3:  # 2.4 GHz band
                            detected[current_iface] = "2G"
                        elif freq < 6:  # 5 GHz band
                            detected[current_iface] = "5G"
                        else:  # 6 GHz band
                            detected[current_iface] = "6G"
                        print(f"[DETECT] {current_iface}: {freq} GHz -> {detected[current_iface]}")
            
            if len(detected) >= 3:
                # Reverse the mapping: from {iface: band} to {band: iface}
                new_interfaces = {}
                for iface, band in detected.items():
                    new_interfaces[band] = iface
                
                # Check if we detected all three bands
                if "2G" in new_interfaces and "5G" in new_interfaces and "6G" in new_interfaces:
                    INTERFACES = new_interfaces
                    interface_detection_status["detected"] = True
                    interface_detection_status["last_detection"] = datetime.now()
                    interface_detection_status["detection_method"] = "iwconfig_frequency"
                    interface_detection_status["detected_mapping"] = dict(INTERFACES)
                    print(f"[DETECT] Success via iwconfig! Mapping: {INTERFACES}")
                    
                    # Now detect UCI radio mapping
                    detect_uci_wifi_mapping()
                    return True
        
        # Method 2: Use UCI config to detect based on channel/hwmode
        print("[DETECT] Method 1 failed, trying UCI config method...")
        success, stdout, stderr = run_ssh_command(
            "uci show wireless | grep -E 'wifi[0-2]\\.(channel|htmode|band|hwmode)'",
            timeout=10
        )
        
        if success and stdout.strip():
            uci_data = {}
            for line in stdout.strip().split('\n'):
                # Parse lines like: wireless.wifi0.channel='6'
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.replace('wireless.', '')
                    value = value.strip("'\"")
                    
                    parts = key.split('.')
                    if len(parts) == 2:
                        radio, prop = parts
                        if radio not in uci_data:
                            uci_data[radio] = {}
                        uci_data[radio][prop] = value
            
            print(f"[DETECT] UCI data: {uci_data}")
            
            # Determine band for each radio based on channel/hwmode/band
            new_uci_map = {}
            for radio, config in uci_data.items():
                band = None
                
                # Check 'band' property first (newer OpenWrt)
                if 'band' in config:
                    band_val = config['band'].lower()
                    if band_val == '2g':
                        band = "2G"
                    elif band_val == '5g':
                        band = "5G"
                    elif band_val == '6g':
                        band = "6G"
                
                # Check hwmode if band not detected
                if not band and 'hwmode' in config:
                    hwmode = config['hwmode'].lower()
                    if 'g' in hwmode and 'a' not in hwmode:
                        band = "2G"
                    elif 'a' in hwmode:
                        # Could be 5G or 6G, need to check channel
                        channel = int(config.get('channel', 0))
                        if channel > 0:
                            if channel <= 14:
                                band = "2G"
                            elif channel <= 177:
                                band = "5G"
                            else:
                                band = "6G"
                
                # Check channel if still not determined
                if not band and 'channel' in config:
                    try:
                        channel = int(config['channel'])
                        if channel <= 14:
                            band = "2G"
                        elif channel <= 177:
                            band = "5G"
                        else:
                            band = "6G"
                    except:
                        pass
                
                # Check htmode for EHT320 which is 6G specific
                if not band and 'htmode' in config:
                    htmode = config['htmode'].upper()
                    if 'EHT320' in htmode:
                        band = "6G"
                    elif 'EHT160' in htmode or 'VHT160' in htmode:
                        band = "5G"  # Most likely 5G
                    elif 'HT20' in htmode or 'HT40' in htmode:
                        band = "2G"  # Most likely 2.4G
                
                if band:
                    new_uci_map[band] = radio
                    print(f"[DETECT] {radio} -> {band}")
            
            # Also need to detect interface mapping from UCI
            if len(new_uci_map) >= 3:
                UCI_WIFI_MAP.update(new_uci_map)
                
                # Try to get interface mapping from UCI
                success, stdout, stderr = run_ssh_command(
                    "uci show wireless | grep -E 'default_radio[0-2].*ifname'",
                    timeout=10
                )
                
                if success and stdout.strip():
                    for line in stdout.strip().split('\n'):
                        if 'ifname=' in line:
                            # Extract radio number and interface name
                            import re
                            match = re.search(r'default_radio(\d)', line)
                            iface_match = re.search(r"ifname='?(ath\d)'?", line)
                            if match and iface_match:
                                radio_num = match.group(1)
                                iface = iface_match.group(1)
                                radio = f"wifi{radio_num}"
                                
                                # Find which band this radio is
                                for band, uci_radio in UCI_WIFI_MAP.items():
                                    if uci_radio == radio:
                                        INTERFACES[band] = iface
                                        print(f"[DETECT] {band} -> {iface} (from UCI)")
                
                interface_detection_status["detected"] = True
                interface_detection_status["last_detection"] = datetime.now()
                interface_detection_status["detection_method"] = "uci_config"
                interface_detection_status["detected_mapping"] = dict(INTERFACES)
                print(f"[DETECT] Success via UCI! Mapping: {INTERFACES}")
                return True
        
        print("[DETECT] Auto-detection failed, using default mapping")
        return False
        
    except Exception as e:
        print(f"[DETECT] Error during detection: {e}")
        return False


def detect_uci_wifi_mapping():
    """Detect the UCI radio mapping (wifi0/wifi1/wifi2) based on detected interfaces"""
    global UCI_WIFI_MAP
    
    try:
        # Query UCI to find which wifiX corresponds to which band
        success, stdout, stderr = run_ssh_command(
            "uci show wireless | grep -E 'wifi[0-2]\\.(channel|band)'",
            timeout=10
        )
        
        if success and stdout.strip():
            uci_data = {}
            for line in stdout.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.replace('wireless.', '')
                    value = value.strip("'\"")
                    
                    parts = key.split('.')
                    if len(parts) == 2:
                        radio, prop = parts
                        if radio not in uci_data:
                            uci_data[radio] = {}
                        uci_data[radio][prop] = value
            
            # Map radios to bands based on channel
            for radio, config in uci_data.items():
                try:
                    channel = int(config.get('channel', 0))
                    if channel > 0:
                        if channel <= 14:
                            UCI_WIFI_MAP["2G"] = radio
                        elif channel <= 177:
                            UCI_WIFI_MAP["5G"] = radio
                        else:
                            UCI_WIFI_MAP["6G"] = radio
                        print(f"[UCI DETECT] {radio} (CH{channel}) -> {get_band_from_channel(channel)}")
                except:
                    pass
            
            print(f"[UCI DETECT] UCI mapping: {UCI_WIFI_MAP}")
            
    except Exception as e:
        print(f"[UCI DETECT] Error: {e}")


def get_band_from_channel(channel):
    """Get band name from channel number"""
    if channel <= 14:
        return "2G"
    elif channel <= 177:
        return "5G"
    else:
        return "6G"


# ============== SSH helpers (Windows/OpenSSH compatibility) ==============
_SSH_PUBKEY_ACCEPT_OPTION = None  # "PubkeyAcceptedAlgorithms" | "PubkeyAcceptedKeyTypes" | None


def _ssh_creationflags():
    """Hide console window on Windows when spawning ssh."""
    import subprocess
    import sys
    if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return subprocess.CREATE_NO_WINDOW
    return 0


def _ssh_null_device_path():
    """Return a null device path compatible with the current OS."""
    import sys
    return "NUL" if sys.platform == "win32" else "/dev/null"


def _detect_pubkey_accept_option():
    """
    Detect which ssh_config option is supported by the local OpenSSH client.
    - Newer OpenSSH: PubkeyAcceptedAlgorithms
    - Older OpenSSH (e.g., OpenSSH_for_Windows_8.1p1): PubkeyAcceptedKeyTypes
    """
    global _SSH_PUBKEY_ACCEPT_OPTION
    if _SSH_PUBKEY_ACCEPT_OPTION is not None:
        return _SSH_PUBKEY_ACCEPT_OPTION

    import subprocess

    creationflags = _ssh_creationflags()
    for opt in ("PubkeyAcceptedAlgorithms", "PubkeyAcceptedKeyTypes"):
        try:
            # -G prints final configuration without connecting; it fails fast for bad options.
            probe = subprocess.run(
                ["ssh", "-G", "-o", f"{opt}=+ssh-rsa", "dummy"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=creationflags,
            )
            if probe.returncode == 0:
                _SSH_PUBKEY_ACCEPT_OPTION = opt
                return _SSH_PUBKEY_ACCEPT_OPTION
        except Exception:
            continue

    _SSH_PUBKEY_ACCEPT_OPTION = None
    return None


def _find_ssh_executable():
    """Find the ssh executable path on Windows."""
    import shutil
    
    # Try to find ssh in PATH first
    ssh_path = shutil.which("ssh")
    if ssh_path:
        return ssh_path
    
    # Common Windows SSH locations
    possible_paths = [
        r"C:\Windows\System32\OpenSSH\ssh.exe",
        r"C:\Program Files\OpenSSH\ssh.exe",
        r"C:\Program Files (x86)\OpenSSH\ssh.exe",
        r"C:\Users\{}\AppData\Local\Microsoft\WindowsApps\ssh.exe".format(os.environ.get("USERNAME", "")),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # Fallback to just "ssh" and hope it's in PATH
    return "ssh"


def _build_ssh_base_cmd(timeout=None, batch_mode=True, include_pubkey_accept=True):
    """Build SSH command line for connecting to OpenWrt/Dropbear."""
    # Find SSH executable
    ssh_exe = _find_ssh_executable()
    
    # Use minimal options that work best with Dropbear
    ssh_cmd = [
        ssh_exe,
        "-o", "StrictHostKeyChecking=no",
        "-o", "HostKeyAlgorithms=+ssh-rsa",
    ]

    if timeout is not None:
        ssh_cmd += ["-o", f"ConnectTimeout={timeout}"]

    if batch_mode:
        ssh_cmd += ["-o", "BatchMode=yes"]

    if SSH_PORT != 22:
        ssh_cmd += ["-p", str(SSH_PORT)]
    
    if SSH_KEY_PATH:
        ssh_cmd += ["-i", SSH_KEY_PATH]

    ssh_cmd += [f"{OPENWRT_USER}@{OPENWRT_HOST}"]
    return ssh_cmd


def run_ssh_command(command, timeout=30):
    """Run SSH command using system ssh (best compatibility with OpenWrt/Dropbear)"""
    return _run_ssh_command_system_no_batch(command, timeout)


def _run_ssh_command_system_no_batch(command, timeout=30):
    """Run SSH command using system ssh (best compatibility with OpenWrt/Dropbear)"""
    import subprocess

    # Build command without BatchMode for better compatibility
    ssh_cmd = _build_ssh_base_cmd(timeout=timeout, batch_mode=False, include_pubkey_accept=True) + [command]

    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 5,  # Give a bit more time than SSH's ConnectTimeout
        )
        
        if result.returncode == 0:
            return True, result.stdout, result.stderr

        return False, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timeout"
    except Exception as e:
        return False, "", str(e)


def run_ssh_command_background(command):
    """Start SSH command in background using system ssh"""
    return _run_ssh_background_system(command)


def _run_ssh_background_system(command):
    """Start SSH command in background using system ssh"""
    import subprocess

    # Use batch_mode=False for better compatibility with Dropbear (no password)
    ssh_cmd = _build_ssh_base_cmd(timeout=10, batch_mode=False, include_pubkey_accept=True) + [command]

    # Hide console window on Windows
    creationflags = _ssh_creationflags()

    try:
        process = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,  # Prevent stdin blocking
            creationflags=creationflags
        )
        return process
    except Exception as e:
        print(f"[SSH] Failed to start command: {e}")
        return None


def download_file_scp(remote_path, local_path):
    """Download file using system ssh (best compatibility with OpenWrt/Dropbear)"""
    return _download_file_system(remote_path, local_path)


def _download_file_system(remote_path, local_path):
    """Download file using system ssh cat pipe (better Dropbear compatibility)"""
    import subprocess

    # Use SSH + cat to pipe binary file content
    # Use batch_mode=False for better compatibility with Dropbear (no password)
    ssh_cmd = _build_ssh_base_cmd(timeout=10, batch_mode=False, include_pubkey_accept=True) + [f"cat {remote_path}"]

    # Hide console window on Windows
    creationflags = _ssh_creationflags()

    try:
        print(f"[DOWNLOAD] Downloading {remote_path} to {local_path}")
        with open(local_path, 'wb') as f:
            result = subprocess.run(ssh_cmd, stdout=f, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, timeout=120, creationflags=creationflags)
        
        if result.returncode == 0 and os.path.exists(local_path):
            size = os.path.getsize(local_path)
            print(f"[DOWNLOAD] Success: {size} bytes")
            return size > 0
        else:
            print(f"[DOWNLOAD] Failed: {result.stderr.decode() if result.stderr else 'Unknown error'}")
            return False
    except Exception as e:
        print(f"[DOWNLOAD] Error: {e}")
        return False


def get_ssh_client():
    """Legacy paramiko client - kept for compatibility but may not work with old Dropbear"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    print(f"[SSH] Attempting paramiko connection to {OPENWRT_USER}@{OPENWRT_HOST}:{SSH_PORT}")
    
    try:
        # Try with look_for_keys which will use ed25519 key if available
        client.connect(
            hostname=OPENWRT_HOST,
            port=SSH_PORT,
            username=OPENWRT_USER,
            password=OPENWRT_PASSWORD if OPENWRT_PASSWORD else '',
            timeout=15,
            allow_agent=True,
            look_for_keys=True,
        )
        print(f"[SSH] Paramiko connected successfully")
        return client
    except Exception as e:
        print(f"[SSH] Paramiko connection failed: {e}")
        return None


def test_connection():
    """Test SSH connection to OpenWrt using system ssh"""
    global last_connection_error
    last_connection_error = None
    
    print(f"[SSH] Testing connection to {OPENWRT_HOST}...")
    
    success, stdout, stderr = run_ssh_command("echo connected", timeout=10)
    
    if success and "connected" in stdout:
        print("[SSH] Connection test: SUCCESS")
        
        # Auto-detect interface mapping if not yet detected
        if not interface_detection_status["detected"]:
            detect_interface_mapping()
        
        return True
    else:
        last_connection_error = stderr or "Connection failed"
        print(f"[SSH] Connection test: FAILED - {last_connection_error}")
        return False


# Store last error for debugging
last_connection_error = None

# Time sync status
time_sync_status = {
    "last_sync": None,
    "offset_seconds": None,
    "success": False
}


def sync_openwrt_time():
    """Sync OpenWrt system time with local PC time"""
    global time_sync_status
    
    try:
        # Get current PC time in the format OpenWrt expects
        pc_time = datetime.now()
        
        # Format for OpenWrt date command: "YYYY-MM-DD HH:MM:SS"
        time_str = pc_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # First, get OpenWrt's current time to calculate offset
        success, stdout, stderr = run_ssh_command("date '+%Y-%m-%d %H:%M:%S'", timeout=10)
        
        openwrt_time_before = None
        if success and stdout.strip():
            try:
                openwrt_time_before = datetime.strptime(stdout.strip(), "%Y-%m-%d %H:%M:%S")
                offset = (pc_time - openwrt_time_before).total_seconds()
                time_sync_status["offset_seconds"] = offset
                print(f"[TIME SYNC] OpenWrt time before sync: {stdout.strip()}")
                print(f"[TIME SYNC] PC time: {time_str}")
                print(f"[TIME SYNC] Offset: {offset:.1f} seconds")
            except Exception as e:
                print(f"[TIME SYNC] Could not parse OpenWrt time: {e}")
        
        # Set the time on OpenWrt
        # Using date -s for BusyBox compatibility
        set_cmd = f'date -s "{time_str}"'
        success, stdout, stderr = run_ssh_command(set_cmd, timeout=10)
        
        if success:
            # Verify the time was set correctly
            success, stdout, stderr = run_ssh_command("date '+%Y-%m-%d %H:%M:%S'", timeout=10)
            print(f"[TIME SYNC] OpenWrt time after sync: {stdout.strip()}")
            
            time_sync_status["last_sync"] = pc_time
            time_sync_status["success"] = True
            
            return True, f"Time synced: {time_str}"
        else:
            time_sync_status["success"] = False
            return False, f"Failed to set time: {stderr}"
            
    except Exception as e:
        time_sync_status["success"] = False
        return False, f"Time sync error: {str(e)}"


def get_time_info():
    """Get current time info from both PC and OpenWrt"""
    pc_time = datetime.now()
    
    success, stdout, stderr = run_ssh_command("date '+%Y-%m-%d %H:%M:%S'", timeout=10)
    
    openwrt_time = None
    offset = None
    
    if success and stdout.strip():
        try:
            openwrt_time = datetime.strptime(stdout.strip(), "%Y-%m-%d %H:%M:%S")
            offset = (pc_time - openwrt_time).total_seconds()
        except:
            pass
    
    return {
        "pc_time": pc_time.strftime("%Y-%m-%d %H:%M:%S"),
        "openwrt_time": stdout.strip() if success else "Unknown",
        "offset_seconds": offset,
        "synced": abs(offset) < 2 if offset is not None else False
    }


def start_capture_thread(band, auto_sync_time=True):
    """Start packet capture for specified band"""
    global capture_status
    
    interface = INTERFACES.get(band)
    if not interface:
        return False, f"Unknown band: {band}"
    
    if capture_status[band]["running"]:
        return False, f"{band} capture already running"
    
    try:
        # Auto-sync time before starting capture (only for first band if starting multiple)
        if auto_sync_time:
            # Check if any other band is already capturing - if so, time was already synced
            other_bands_running = any(
                capture_status[b]["running"] for b in ["2G", "5G", "6G"] if b != band
            )
            if not other_bands_running:
                print(f"[CAPTURE] Syncing time before starting {band} capture...")
                sync_success, sync_msg = sync_openwrt_time()
                if sync_success:
                    print(f"[CAPTURE] Time sync successful: {sync_msg}")
                else:
                    print(f"[CAPTURE] Time sync warning: {sync_msg} (continuing anyway)")
        
        # Remote file path
        remote_path = f"/tmp/{band}.pcap"
        
        # Build tcpdump command based on file split settings
        # -C option: rotate file after reaching specified size (in millions of bytes)
        if file_split_config["enabled"]:
            size_mb = file_split_config["size_mb"]
            tcpdump_cmd = f"tcpdump -i {interface} -U -s0 -w {remote_path} -C {size_mb}"
            print(f"[CAPTURE] File splitting enabled: {size_mb}MB per file")
        else:
            tcpdump_cmd = f"tcpdump -i {interface} -U -s0 -w {remote_path}"
            print(f"[CAPTURE] Continuous capture (no file splitting)")
        
        # Combined command: kill existing tcpdump for THIS interface only, remove old file, start tcpdump
        # Using subshell to properly daemonize tcpdump on BusyBox/OpenWrt
        # NOTE: We only kill tcpdump for this specific interface, not all tcpdump processes
        cmd = f"""
            PID=$(ps | grep "tcpdump -i {interface}" | grep -v grep | awk '{{print $1}}')
            [ -n "$PID" ] && kill $PID 2>/dev/null
            rm -f {remote_path} {remote_path}[0-9]* 
            ({tcpdump_cmd} &)
            sleep 1
            ps | grep "tcpdump -i {interface}" | grep -v grep && echo 'TCPDUMP_STARTED' || echo 'TCPDUMP_FAILED'
        """
        
        success, stdout, stderr = run_ssh_command(cmd, timeout=15)
        
        print(f"[CAPTURE] {band} start result: success={success}, stdout={stdout}, stderr={stderr}")
        
        if not success or "TCPDUMP_FAILED" in stdout:
            return False, f"Failed to start tcpdump: {stderr or stdout}"
        
        if "TCPDUMP_STARTED" not in stdout:
            return False, "tcpdump verification failed"
        
        capture_status[band]["running"] = True
        capture_status[band]["start_time"] = datetime.now()
        capture_status[band]["packets"] = 0
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitor_capture, args=(band,))
        monitor_thread.daemon = True
        monitor_thread.start()
        
        return True, f"{band} capture started on {interface}"
    
    except Exception as e:
        return False, f"Error starting capture: {str(e)}"


def monitor_capture(band):
    """Monitor packet count for a capture"""
    global capture_status
    
    while capture_status[band]["running"]:
        try:
            remote_path = f"/tmp/{band}.pcap"
            success, stdout, stderr = run_ssh_command(f"ls -la {remote_path} 2>/dev/null | awk '{{print $5}}'", timeout=5)
            if success and stdout.strip():
                try:
                    size = int(stdout.strip())
                    capture_status[band]["packets"] = size // 100  # Rough packet estimate
                except:
                    pass
        except:
            pass
        time.sleep(3)


def stop_capture(band):
    """Stop packet capture and download file(s)"""
    global capture_status
    
    if not capture_status[band]["running"]:
        return False, f"{band} capture not running", None
    
    try:
        # Kill tcpdump for THIS interface only (not all tcpdump processes)
        interface = INTERFACES.get(band)
        kill_cmd = f"PID=$(ps | grep 'tcpdump -i {interface}' | grep -v grep | awk '{{print $1}}'); [ -n \"$PID\" ] && kill $PID 2>/dev/null || true"
        run_ssh_command(kill_cmd, timeout=10)
        time.sleep(2)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        remote_path = f"/tmp/{band}.pcap"
        
        # Check if file splitting was enabled - list all matching files
        success, stdout, stderr = run_ssh_command(f"ls -1 {remote_path}* 2>/dev/null", timeout=5)
        
        if not success or not stdout.strip():
            capture_status[band]["running"] = False
            capture_status[band]["start_time"] = None
            return False, "No capture file found on router", None
        
        # Parse the list of files
        remote_files = [f.strip() for f in stdout.strip().split('\n') if f.strip()]
        print(f"[CAPTURE] Found {len(remote_files)} capture file(s) for {band}")
        
        downloaded_files = []
        total_size = 0
        
        if len(remote_files) == 1:
            # Single file - download with standard naming
            local_filename = f"{band}_sniffer_{timestamp}.pcap"
            local_path = os.path.join(DOWNLOADS_FOLDER, local_filename)
            
            if download_file_scp(remote_files[0], local_path):
                if os.path.exists(local_path):
                    file_size = os.path.getsize(local_path)
                    total_size = file_size
                    downloaded_files.append(local_filename)
        else:
            # Multiple files (split mode) - download each with numbered naming
            for i, remote_file in enumerate(remote_files):
                # Create filename: 2G_sniffer_20231222_143000_part001.pcap
                part_num = i + 1
                local_filename = f"{band}_sniffer_{timestamp}_part{part_num:03d}.pcap"
                local_path = os.path.join(DOWNLOADS_FOLDER, local_filename)
                
                print(f"[CAPTURE] Downloading part {part_num}/{len(remote_files)}: {remote_file}")
                
                if download_file_scp(remote_file, local_path):
                    if os.path.exists(local_path):
                        file_size = os.path.getsize(local_path)
                        total_size += file_size
                        downloaded_files.append(local_filename)
        
        # Remove all remote files
        run_ssh_command(f"rm -f {remote_path}*", timeout=5)
        
        capture_status[band]["running"] = False
        capture_status[band]["start_time"] = None
        
        if downloaded_files:
            if len(downloaded_files) == 1:
                return True, f"Saved: {downloaded_files[0]} ({total_size:,} bytes)", os.path.join(DOWNLOADS_FOLDER, downloaded_files[0])
            else:
                # Format size nicely
                if total_size > 1024 * 1024 * 1024:
                    size_str = f"{total_size / (1024*1024*1024):.2f} GB"
                elif total_size > 1024 * 1024:
                    size_str = f"{total_size / (1024*1024):.1f} MB"
                else:
                    size_str = f"{total_size:,} bytes"
                return True, f"Saved {len(downloaded_files)} files ({size_str} total)", DOWNLOADS_FOLDER
        else:
            return False, "Download failed", None
    
    except Exception as e:
        capture_status[band]["running"] = False
        capture_status[band]["start_time"] = None
        return False, f"Error stopping capture: {str(e)}", None


def stop_all_captures():
    """Stop all running captures"""
    results = {}
    for band in ["2G", "5G", "6G"]:
        if capture_status[band]["running"]:
            success, msg, path = stop_capture(band)
            results[band] = {"success": success, "message": msg, "path": path}
    return results


def set_channel(band, channel, bandwidth=None):
    """Set channel for specified band (updates local config only, use apply_config to commit)"""
    channel_config[band]["channel"] = channel
    if bandwidth:
        channel_config[band]["bandwidth"] = bandwidth
    return True, f"Config updated for {band}: CH{channel} {bandwidth or ''}"


def apply_channel_config(band):
    """Apply channel configuration to OpenWrt using UCI commands"""
    uci_radio = UCI_WIFI_MAP.get(band)
    if not uci_radio:
        return False, f"Unknown band: {band}"
    
    channel = channel_config[band]["channel"]
    bandwidth = channel_config[band]["bandwidth"]
    
    # Build UCI commands
    commands = [
        f"uci set wireless.{uci_radio}.channel={channel}",
        f"uci set wireless.{uci_radio}.htmode={bandwidth}",
    ]
    
    # Execute UCI set commands
    for cmd in commands:
        success, stdout, stderr = run_ssh_command(cmd, timeout=10)
        if not success:
            return False, f"Failed to execute: {cmd} - {stderr}"
        print(f"[UCI] {cmd}")
    
    return True, f"{band} config set: CH{channel} {bandwidth}"


def apply_all_and_restart_wifi():
    """Apply all channel configurations and restart wifi"""
    results = {"success": True, "messages": [], "bands": {}}
    
    # Apply config for each band
    for band in ["2G", "5G", "6G"]:
        success, msg = apply_channel_config(band)
        results["bands"][band] = {"success": success, "message": msg}
        results["messages"].append(f"{band}: {msg}")
        if not success:
            results["success"] = False
    
    if not results["success"]:
        return results
    
    # Commit UCI changes
    print("[UCI] Committing changes...")
    success, stdout, stderr = run_ssh_command("uci commit wireless", timeout=10)
    if not success:
        results["success"] = False
        results["messages"].append(f"UCI commit failed: {stderr}")
        return results
    
    results["messages"].append("UCI changes committed")
    
    # Restart wifi (this will take time)
    print("[WIFI] Restarting wifi interfaces...")
    results["messages"].append("Restarting wifi interfaces...")
    
    success, stdout, stderr = run_ssh_command("wifi", timeout=60)
    if not success:
        results["success"] = False
        results["messages"].append(f"Wifi restart failed: {stderr}")
        return results
    
    # Wait for interfaces to come back up
    results["messages"].append("Waiting for interfaces to initialize...")
    
    # Poll for interfaces to be ready (max 30 seconds)
    max_wait = 30
    start_time = time.time()
    interfaces_ready = False
    
    while time.time() - start_time < max_wait:
        time.sleep(3)
        success, stdout, stderr = run_ssh_command("iwconfig 2>/dev/null | grep -E '^ath[0-2]'", timeout=10)
        if success and "ath0" in stdout and "ath1" in stdout and "ath2" in stdout:
            interfaces_ready = True
            break
        print(f"[WIFI] Waiting for interfaces... ({int(time.time() - start_time)}s)")
    
    if interfaces_ready:
        results["messages"].append("All interfaces ready!")
        
        # Get current channel info
        success, stdout, stderr = run_ssh_command("iwconfig 2>/dev/null | grep -E 'Frequency|^ath'", timeout=10)
        if success:
            results["interface_status"] = stdout
    else:
        results["success"] = False
        results["messages"].append("Timeout waiting for interfaces to come up")
    
    return results


def get_current_wifi_config():
    """Get current channel configuration from OpenWrt"""
    config = {}
    
    for band, uci_radio in UCI_WIFI_MAP.items():
        success, stdout, stderr = run_ssh_command(
            f"uci get wireless.{uci_radio}.channel; uci get wireless.{uci_radio}.htmode",
            timeout=10
        )
        if success:
            lines = stdout.strip().split('\n')
            if len(lines) >= 2:
                config[band] = {
                    "channel": int(lines[0]) if lines[0].isdigit() else lines[0],
                    "bandwidth": lines[1]
                }
    
    return config


# ============== HTML Template ==============
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WiFi Sniffer Control Panel</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #0a0e17;
            --bg-card: #111827;
            --bg-card-hover: #1a2332;
            --accent-2g: #22c55e;
            --accent-5g: #3b82f6;
            --accent-6g: #a855f7;
            --accent-warning: #f59e0b;
            --accent-danger: #ef4444;
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --border-color: #1e293b;
            --glow-2g: rgba(34, 197, 94, 0.3);
            --glow-5g: rgba(59, 130, 246, 0.3);
            --glow-6g: rgba(168, 85, 247, 0.3);
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Space Grotesk', sans-serif;
            background: var(--bg-dark);
            color: var(--text-primary);
            min-height: 100vh;
            background-image: 
                radial-gradient(ellipse at 20% 0%, rgba(34, 197, 94, 0.08) 0%, transparent 50%),
                radial-gradient(ellipse at 80% 0%, rgba(59, 130, 246, 0.08) 0%, transparent 50%),
                radial-gradient(ellipse at 50% 100%, rgba(168, 85, 247, 0.08) 0%, transparent 50%);
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        header {
            text-align: center;
            margin-bottom: 3rem;
        }
        
        h1 {
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent-2g), var(--accent-5g), var(--accent-6g));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 0.5rem;
        }
        
        .subtitle {
            color: var(--text-secondary);
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.9rem;
        }
        
        .connection-status {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            background: var(--bg-card);
            border-radius: 2rem;
            margin-top: 1rem;
            border: 1px solid var(--border-color);
        }
        
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        
        .status-dot.connected { background: var(--accent-2g); box-shadow: 0 0 10px var(--glow-2g); }
        .status-dot.disconnected { background: var(--accent-danger); box-shadow: 0 0 10px rgba(239, 68, 68, 0.3); }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .main-controls {
            display: flex;
            justify-content: center;
            gap: 1rem;
            margin-bottom: 2rem;
            flex-wrap: wrap;
        }
        
        .btn {
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 600;
            padding: 0.75rem 2rem;
            border: none;
            border-radius: 0.5rem;
            cursor: pointer;
            transition: all 0.3s ease;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .btn-start-all {
            background: linear-gradient(135deg, var(--accent-2g), var(--accent-5g));
            color: white;
        }
        
        .btn-start-all:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(34, 197, 94, 0.3);
        }
        
        .btn-stop-all {
            background: var(--accent-danger);
            color: white;
        }
        
        .btn-stop-all:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(239, 68, 68, 0.3);
        }
        
        .btn-refresh {
            background: var(--bg-card);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
        }
        
        .btn-refresh:hover {
            background: var(--bg-card-hover);
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
            gap: 1.5rem;
        }
        
        .card {
            background: var(--bg-card);
            border-radius: 1rem;
            border: 1px solid var(--border-color);
            overflow: hidden;
            transition: all 0.3s ease;
        }
        
        .card:hover {
            transform: translateY(-4px);
            border-color: var(--text-secondary);
        }
        
        .card-2g:hover { box-shadow: 0 20px 40px var(--glow-2g); border-color: var(--accent-2g); }
        .card-5g:hover { box-shadow: 0 20px 40px var(--glow-5g); border-color: var(--accent-5g); }
        .card-6g:hover { box-shadow: 0 20px 40px var(--glow-6g); border-color: var(--accent-6g); }
        
        .card-header {
            padding: 1.5rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--border-color);
        }
        
        .band-label {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        
        .band-icon {
            width: 50px;
            height: 50px;
            border-radius: 0.75rem;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 1.2rem;
        }
        
        .band-icon-2g { background: linear-gradient(135deg, var(--accent-2g), #15803d); }
        .band-icon-5g { background: linear-gradient(135deg, var(--accent-5g), #1d4ed8); }
        .band-icon-6g { background: linear-gradient(135deg, var(--accent-6g), #7c3aed); }
        
        .band-info h3 {
            font-size: 1.25rem;
            margin-bottom: 0.25rem;
        }
        
        .band-info .interface {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            color: var(--text-secondary);
        }
        
        .status-badge {
            padding: 0.35rem 0.75rem;
            border-radius: 2rem;
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        
        .status-idle { background: var(--border-color); color: var(--text-secondary); }
        .status-running { background: rgba(34, 197, 94, 0.2); color: var(--accent-2g); animation: pulse 1.5s infinite; }
        
        .card-body {
            padding: 1.5rem;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
            margin-bottom: 1.5rem;
        }
        
        .stat-item {
            background: rgba(0, 0, 0, 0.3);
            padding: 1rem;
            border-radius: 0.5rem;
            text-align: center;
        }
        
        .stat-value {
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.5rem;
            font-weight: 600;
        }
        
        .stat-label {
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-top: 0.25rem;
        }
        
        .channel-config {
            margin-bottom: 1.5rem;
            padding: 1rem;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 0.5rem;
        }
        
        .channel-config label {
            display: block;
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
        }
        
        .config-row {
            display: flex;
            gap: 0.5rem;
        }
        
        .config-row select {
            flex: 1;
            padding: 0.5rem;
            background: var(--bg-dark);
            border: 1px solid var(--border-color);
            border-radius: 0.35rem;
            color: var(--text-primary);
            font-family: 'JetBrains Mono', monospace;
        }
        
        .config-row select:focus {
            outline: none;
            border-color: var(--accent-5g);
        }
        
        .btn-apply-config {
            padding: 0.5rem 1rem;
            background: var(--bg-dark);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            border-radius: 0.35rem;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .btn-apply-config:hover {
            border-color: var(--accent-5g);
            background: var(--bg-card-hover);
        }
        
        .card-actions {
            display: flex;
            gap: 0.75rem;
        }
        
        .btn-capture {
            flex: 1;
            padding: 0.75rem;
            border: none;
            border-radius: 0.5rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
        }
        
        .btn-start {
            background: rgba(34, 197, 94, 0.2);
            color: var(--accent-2g);
            border: 1px solid var(--accent-2g);
        }
        
        .btn-start:hover {
            background: var(--accent-2g);
            color: white;
        }
        
        .btn-stop {
            background: rgba(239, 68, 68, 0.2);
            color: var(--accent-danger);
            border: 1px solid var(--accent-danger);
        }
        
        .btn-stop:hover {
            background: var(--accent-danger);
            color: white;
        }
        
        .btn-disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        /* Notification */
        .notification {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            padding: 1rem 1.5rem;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
            animation: slideIn 0.3s ease;
            max-width: 400px;
            z-index: 1000;
        }
        
        .notification.success { border-color: var(--accent-2g); }
        .notification.error { border-color: var(--accent-danger); }
        
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        
        /* Section Title */
        .section-title {
            font-size: 1.2rem;
            font-weight: 600;
            margin: 2rem 0 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        /* Download Path */
        .download-path {
            text-align: center;
            margin-top: 2rem;
            padding: 1rem;
            background: var(--bg-card);
            border-radius: 0.5rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            color: var(--text-secondary);
        }
        
        .download-path strong {
            color: var(--accent-5g);
        }
        
        /* Loading overlay */
        .loading-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(10, 14, 23, 0.8);
            z-index: 999;
            justify-content: center;
            align-items: center;
        }
        
        .loading-overlay.active {
            display: flex;
        }
        
        .spinner {
            width: 50px;
            height: 50px;
            border: 3px solid var(--border-color);
            border-top-color: var(--accent-5g);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        /* Mobile responsive */
        @media (max-width: 768px) {
            .container { padding: 1rem; }
            h1 { font-size: 1.75rem; }
            .grid { grid-template-columns: 1fr; }
            .main-controls { flex-direction: column; }
            .btn { width: 100%; justify-content: center; }
        }
    </style>
</head>
<body>
    <div class="loading-overlay" id="loadingOverlay">
        <div class="spinner"></div>
    </div>
    
    <div class="container">
        <header>
            <h1>📡 WiFi Sniffer Control Panel</h1>
            <p class="subtitle">OpenWrt Monitor Mode Packet Capture</p>
            <div class="connection-status" onclick="diagnoseConnection()" style="cursor: pointer;" title="Click to diagnose">
                <div class="status-dot {{ 'connected' if connected else 'disconnected' }}" id="connectionDot"></div>
                <span id="connectionText">{{ '192.168.1.1 Connected' if connected else '192.168.1.1 Disconnected - Click to diagnose' }}</span>
            </div>
            
            <!-- Interface Mapping Status -->
            <div class="interface-mapping-status" style="margin-top: 0.75rem; display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.5rem 1rem; background: var(--bg-card); border-radius: 2rem; border: 1px solid var(--border-color); font-size: 0.85rem; flex-wrap: wrap;">
                <span style="color: var(--text-secondary);">🔗 Interface:</span>
                <span id="mapping2G" style="font-family: 'JetBrains Mono', monospace; color: var(--accent-2g);">2G={{ interfaces['2G'] }}</span>
                <span style="color: var(--text-secondary);">|</span>
                <span id="mapping5G" style="font-family: 'JetBrains Mono', monospace; color: var(--accent-5g);">5G={{ interfaces['5G'] }}</span>
                <span style="color: var(--text-secondary);">|</span>
                <span id="mapping6G" style="font-family: 'JetBrains Mono', monospace; color: var(--accent-6g);">6G={{ interfaces['6G'] }}</span>
                <span id="detectionBadge" style="padding: 0.2rem 0.5rem; border-radius: 1rem; font-size: 0.75rem; font-weight: 600; {{ 'background: rgba(34, 197, 94, 0.2); color: var(--accent-2g);' if detection_status.detected else 'background: rgba(148, 163, 184, 0.2); color: var(--text-secondary);' }}">{{ '✓ Auto-detected' if detection_status.detected else 'Default' }}</span>
                <button onclick="redetectInterfaces()" style="background: none; border: 1px solid var(--border-color); color: var(--text-secondary); padding: 0.25rem 0.5rem; border-radius: 0.25rem; cursor: pointer; font-size: 0.75rem;" title="Re-detect interface mapping">🔍 Detect</button>
            </div>
            
            <!-- Time Sync Status -->
            <div class="time-sync-status" id="timeSyncStatus" style="margin-top: 0.75rem; display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.5rem 1rem; background: var(--bg-card); border-radius: 2rem; border: 1px solid var(--border-color); font-size: 0.85rem;">
                <span style="color: var(--text-secondary);">🕐 PC:</span>
                <span id="pcTime" style="font-family: 'JetBrains Mono', monospace;">--:--:--</span>
                <span style="color: var(--text-secondary);">| OpenWrt:</span>
                <span id="openwrtTime" style="font-family: 'JetBrains Mono', monospace;">--:--:--</span>
                <span id="timeOffsetBadge" style="padding: 0.2rem 0.5rem; border-radius: 1rem; font-size: 0.75rem; font-weight: 600;">--</span>
                <button onclick="manualSyncTime()" style="background: none; border: 1px solid var(--border-color); color: var(--text-secondary); padding: 0.25rem 0.5rem; border-radius: 0.25rem; cursor: pointer; font-size: 0.75rem;" title="Sync OpenWrt time with PC">🔄 Sync</button>
            </div>
            {% if not connected %}
            <div style="margin-top: 1rem; padding: 1rem; background: rgba(239, 68, 68, 0.1); border: 1px solid #ef4444; border-radius: 0.5rem; max-width: 600px; margin-left: auto; margin-right: auto;">
                <p style="color: #ef4444; margin-bottom: 0.5rem; font-weight: 600;">⚠️ SSH Connection Failed</p>
                <p style="color: var(--text-secondary); font-size: 0.85rem; margin-bottom: 0;">
                    Please check: OpenWrt router is on, IP is 192.168.1.1, and SSH is enabled.<br>
                    Click on "Disconnected" above for detailed diagnosis.
                </p>
            </div>
            {% endif %}
        </header>
        
        <!-- File Split Settings -->
        <div class="file-split-settings" style="display: flex; justify-content: center; align-items: center; gap: 1rem; margin-bottom: 1.5rem; padding: 1rem; background: var(--bg-card); border-radius: 0.75rem; border: 1px solid var(--border-color); flex-wrap: wrap;">
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <label class="toggle-switch" style="position: relative; display: inline-block; width: 50px; height: 26px;">
                    <input type="checkbox" id="fileSplitEnabled" onchange="updateFileSplit()" style="opacity: 0; width: 0; height: 0;">
                    <span class="toggle-slider" style="position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: var(--border-color); transition: 0.3s; border-radius: 26px;"></span>
                </label>
                <span style="font-weight: 500;">Split Files by Size</span>
            </div>
            <div id="fileSplitSizeContainer" style="display: flex; align-items: center; gap: 0.5rem; opacity: 0.5;">
                <span style="color: var(--text-secondary);">Max size:</span>
                <select id="fileSplitSize" onchange="updateFileSplit()" style="padding: 0.4rem 0.75rem; background: var(--bg-dark); border: 1px solid var(--border-color); border-radius: 0.35rem; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;">
                    <option value="50">50 MB</option>
                    <option value="100">100 MB</option>
                    <option value="200" selected>200 MB</option>
                    <option value="500">500 MB</option>
                    <option value="1000">1 GB</option>
                </select>
                <span style="color: var(--text-secondary); font-size: 0.85rem;">per file</span>
            </div>
            <div id="fileSplitStatus" style="font-size: 0.85rem; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace;">
                📁 Continuous capture (no split)
            </div>
        </div>
        
        <style>
            .toggle-switch input:checked + .toggle-slider {
                background: linear-gradient(135deg, var(--accent-2g), var(--accent-5g));
            }
            .toggle-switch .toggle-slider:before {
                position: absolute;
                content: "";
                height: 20px;
                width: 20px;
                left: 3px;
                bottom: 3px;
                background-color: white;
                transition: 0.3s;
                border-radius: 50%;
            }
            .toggle-switch input:checked + .toggle-slider:before {
                transform: translateX(24px);
            }
        </style>
        
        <div class="main-controls">
            <button class="btn btn-start-all" onclick="startAll()">
                <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/>
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                Start All Captures
            </button>
            <button class="btn btn-stop-all" onclick="stopAll()">
                <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z"/>
                </svg>
                Stop All & Download
            </button>
            <button class="btn btn-refresh" onclick="refreshStatus()">
                <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                </svg>
                Refresh
            </button>
            <button class="btn btn-apply-all" onclick="applyAllConfig()" style="background: linear-gradient(135deg, #f59e0b, #d97706); color: white;">
                <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
                </svg>
                Apply Config & Restart WiFi
            </button>
        </div>
        
        <div class="grid">
            <!-- 2.4G Card -->
            <div class="card card-2g">
                <div class="card-header">
                    <div class="band-label">
                        <div class="band-icon band-icon-2g">2.4G</div>
                        <div class="band-info">
                            <h3>2.4 GHz Band</h3>
                            <span class="interface" id="iface-2g">{{ interfaces['2G'] }}</span>
                        </div>
                    </div>
                    <span class="status-badge {{ 'status-running' if status['2G']['running'] else 'status-idle' }}" id="status-2g">
                        {{ 'CAPTURING' if status['2G']['running'] else 'IDLE' }}
                    </span>
                </div>
                <div class="card-body">
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="stat-value" id="duration-2g">{{ status['2G']['duration'] or '--:--' }}</div>
                            <div class="stat-label">Duration</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value" id="packets-2g">{{ status['2G']['packets'] }}</div>
                            <div class="stat-label">Est. Packets</div>
                        </div>
                    </div>
                    <div class="channel-config">
                        <label>Channel Configuration</label>
                        <div class="config-row">
                            <select id="channel-2g">
                                {% for ch in channels['2G'] %}
                                <option value="{{ ch }}" {{ 'selected' if ch == channel_config['2G']['channel'] else '' }}>CH {{ ch }}</option>
                                {% endfor %}
                            </select>
                            <select id="bandwidth-2g">
                                {% for bw in bandwidths['2G'] %}
                                <option value="{{ bw }}" {{ 'selected' if bw == channel_config['2G']['bandwidth'] else '' }}>{{ bw }}</option>
                                {% endfor %}
                            </select>
                            <button class="btn-apply-config" onclick="applyConfig('2G')">Apply</button>
                        </div>
                    </div>
                    <div class="card-actions">
                        <button class="btn-capture btn-start {{ 'btn-disabled' if status['2G']['running'] else '' }}" 
                                onclick="startCapture('2G')" {{ 'disabled' if status['2G']['running'] else '' }}>
                            <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                                <path d="M8 5v14l11-7z"/>
                            </svg>
                            Start
                        </button>
                        <button class="btn-capture btn-stop {{ '' if status['2G']['running'] else 'btn-disabled' }}" 
                                onclick="stopCapture('2G')" {{ '' if status['2G']['running'] else 'disabled' }}>
                            <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                                <rect x="6" y="6" width="12" height="12"/>
                            </svg>
                            Stop & Save
                        </button>
                    </div>
                </div>
            </div>
            
            <!-- 5G Card -->
            <div class="card card-5g">
                <div class="card-header">
                    <div class="band-label">
                        <div class="band-icon band-icon-5g">5G</div>
                        <div class="band-info">
                            <h3>5 GHz Band</h3>
                            <span class="interface" id="iface-5g">{{ interfaces['5G'] }}</span>
                        </div>
                    </div>
                    <span class="status-badge {{ 'status-running' if status['5G']['running'] else 'status-idle' }}" id="status-5g">
                        {{ 'CAPTURING' if status['5G']['running'] else 'IDLE' }}
                    </span>
                </div>
                <div class="card-body">
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="stat-value" id="duration-5g">{{ status['5G']['duration'] or '--:--' }}</div>
                            <div class="stat-label">Duration</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value" id="packets-5g">{{ status['5G']['packets'] }}</div>
                            <div class="stat-label">Est. Packets</div>
                        </div>
                    </div>
                    <div class="channel-config">
                        <label>Channel Configuration</label>
                        <div class="config-row">
                            <select id="channel-5g">
                                {% for ch in channels['5G'] %}
                                <option value="{{ ch }}" {{ 'selected' if ch == channel_config['5G']['channel'] else '' }}>CH {{ ch }}</option>
                                {% endfor %}
                            </select>
                            <select id="bandwidth-5g">
                                {% for bw in bandwidths['5G'] %}
                                <option value="{{ bw }}" {{ 'selected' if bw == channel_config['5G']['bandwidth'] else '' }}>{{ bw }}</option>
                                {% endfor %}
                            </select>
                            <button class="btn-apply-config" onclick="applyConfig('5G')">Apply</button>
                        </div>
                    </div>
                    <div class="card-actions">
                        <button class="btn-capture btn-start {{ 'btn-disabled' if status['5G']['running'] else '' }}" 
                                onclick="startCapture('5G')" {{ 'disabled' if status['5G']['running'] else '' }}>
                            <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                                <path d="M8 5v14l11-7z"/>
                            </svg>
                            Start
                        </button>
                        <button class="btn-capture btn-stop {{ '' if status['5G']['running'] else 'btn-disabled' }}" 
                                onclick="stopCapture('5G')" {{ '' if status['5G']['running'] else 'disabled' }}>
                            <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                                <rect x="6" y="6" width="12" height="12"/>
                            </svg>
                            Stop & Save
                        </button>
                    </div>
                </div>
            </div>
            
            <!-- 6G Card -->
            <div class="card card-6g">
                <div class="card-header">
                    <div class="band-label">
                        <div class="band-icon band-icon-6g">6G</div>
                        <div class="band-info">
                            <h3>6 GHz Band</h3>
                            <span class="interface" id="iface-6g">{{ interfaces['6G'] }}</span>
                        </div>
                    </div>
                    <span class="status-badge {{ 'status-running' if status['6G']['running'] else 'status-idle' }}" id="status-6g">
                        {{ 'CAPTURING' if status['6G']['running'] else 'IDLE' }}
                    </span>
                </div>
                <div class="card-body">
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="stat-value" id="duration-6g">{{ status['6G']['duration'] or '--:--' }}</div>
                            <div class="stat-label">Duration</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value" id="packets-6g">{{ status['6G']['packets'] }}</div>
                            <div class="stat-label">Est. Packets</div>
                        </div>
                    </div>
                    <div class="channel-config">
                        <label>Channel Configuration</label>
                        <div class="config-row">
                            <select id="channel-6g">
                                {% for ch in channels['6G'] %}
                                <option value="{{ ch }}" {{ 'selected' if ch == channel_config['6G']['channel'] else '' }}>CH {{ ch }}</option>
                                {% endfor %}
                            </select>
                            <select id="bandwidth-6g">
                                {% for bw in bandwidths['6G'] %}
                                <option value="{{ bw }}" {{ 'selected' if bw == channel_config['6G']['bandwidth'] else '' }}>{{ bw }}</option>
                                {% endfor %}
                            </select>
                            <button class="btn-apply-config" onclick="applyConfig('6G')">Apply</button>
                        </div>
                    </div>
                    <div class="card-actions">
                        <button class="btn-capture btn-start {{ 'btn-disabled' if status['6G']['running'] else '' }}" 
                                onclick="startCapture('6G')" {{ 'disabled' if status['6G']['running'] else '' }}>
                            <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                                <path d="M8 5v14l11-7z"/>
                            </svg>
                            Start
                        </button>
                        <button class="btn-capture btn-stop {{ '' if status['6G']['running'] else 'btn-disabled' }}" 
                                onclick="stopCapture('6G')" {{ '' if status['6G']['running'] else 'disabled' }}>
                            <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                                <rect x="6" y="6" width="12" height="12"/>
                            </svg>
                            Stop & Save
                        </button>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="download-path">
            📁 Capture files will be saved to: <strong>{{ download_path }}</strong>
            <div id="splitFileNote" style="font-size: 0.8rem; margin-top: 0.5rem; color: var(--text-secondary); display: none;">
                💡 When file split is enabled, files will be named: <code style="background: rgba(0,0,0,0.3); padding: 0.2rem 0.4rem; border-radius: 0.25rem;">{BAND}_sniffer_{timestamp}_part001.pcap</code>
            </div>
        </div>
    </div>
    
    <div id="notification" class="notification" style="display: none;">
        <span id="notificationText"></span>
    </div>
    
    <!-- Config Apply Modal -->
    <div id="configModal" class="modal-overlay" style="display: none;">
        <div class="modal-content">
            <h3 style="margin-bottom: 1rem; color: var(--accent-warning);">
                <svg width="24" height="24" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="vertical-align: middle; margin-right: 0.5rem;">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
                </svg>
                Applying Configuration
            </h3>
            <div id="configStatus" style="font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; background: rgba(0,0,0,0.3); padding: 1rem; border-radius: 0.5rem; max-height: 300px; overflow-y: auto;">
                <div class="config-line">Preparing to apply configuration...</div>
            </div>
            <div id="configSpinner" style="text-align: center; margin-top: 1rem;">
                <div class="spinner" style="margin: 0 auto;"></div>
                <p style="color: var(--text-secondary); margin-top: 0.5rem;">Please wait, WiFi interfaces restarting...</p>
            </div>
            <div id="configComplete" style="display: none; text-align: center; margin-top: 1rem;">
                <button class="btn btn-start-all" onclick="closeConfigModal()" style="padding: 0.75rem 2rem;">
                    ✓ Configuration Complete - Start Capture
                </button>
            </div>
        </div>
    </div>
    
    <style>
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(10, 14, 23, 0.9);
            z-index: 1000;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .modal-content {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 1rem;
            padding: 2rem;
            max-width: 500px;
            width: 90%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
        }
        .config-line {
            padding: 0.25rem 0;
            border-bottom: 1px solid var(--border-color);
        }
        .config-line.success { color: var(--accent-2g); }
        .config-line.error { color: var(--accent-danger); }
        .config-line.info { color: var(--accent-5g); }
        .btn-apply-all:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(245, 158, 11, 0.3);
        }
    </style>
    
    <script>
        // Show notification
        function showNotification(message, type = 'success') {
            const notif = document.getElementById('notification');
            const text = document.getElementById('notificationText');
            notif.className = 'notification ' + type;
            text.textContent = message;
            notif.style.display = 'flex';
            
            setTimeout(() => {
                notif.style.display = 'none';
            }, 4000);
        }
        
        // Show/hide loading overlay
        function setLoading(show) {
            document.getElementById('loadingOverlay').classList.toggle('active', show);
        }
        
        // Start capture for single band
        async function startCapture(band) {
            setLoading(true);
            try {
                const response = await fetch('/api/start/' + band, { method: 'POST' });
                const data = await response.json();
                showNotification(data.message, data.success ? 'success' : 'error');
                if (data.success) {
                    setTimeout(() => location.reload(), 500);
                }
            } catch (e) {
                showNotification('Error: ' + e.message, 'error');
            }
            setLoading(false);
        }
        
        // Stop capture for single band
        async function stopCapture(band) {
            setLoading(true);
            try {
                const response = await fetch('/api/stop/' + band, { method: 'POST' });
                const data = await response.json();
                showNotification(data.message, data.success ? 'success' : 'error');
                if (data.success) {
                    setTimeout(() => location.reload(), 500);
                }
            } catch (e) {
                showNotification('Error: ' + e.message, 'error');
            }
            setLoading(false);
        }
        
        // Start all captures
        async function startAll() {
            setLoading(true);
            try {
                const response = await fetch('/api/start_all', { method: 'POST' });
                const data = await response.json();
                showNotification('Started captures for: ' + Object.keys(data.results).join(', '), 'success');
                setTimeout(() => location.reload(), 500);
            } catch (e) {
                showNotification('Error: ' + e.message, 'error');
            }
            setLoading(false);
        }
        
        // Stop all captures
        async function stopAll() {
            setLoading(true);
            try {
                const response = await fetch('/api/stop_all', { method: 'POST' });
                const data = await response.json();
                let savedFiles = [];
                for (const [band, result] of Object.entries(data.results)) {
                    if (result.success && result.path) {
                        savedFiles.push(band);
                    }
                }
                if (savedFiles.length > 0) {
                    showNotification('Saved captures: ' + savedFiles.join(', '), 'success');
                } else {
                    showNotification('No active captures to stop', 'error');
                }
                setTimeout(() => location.reload(), 500);
            } catch (e) {
                showNotification('Error: ' + e.message, 'error');
            }
            setLoading(false);
        }
        
        // Apply channel configuration for single band (local only)
        async function applyConfig(band) {
            const channel = document.getElementById('channel-' + band.toLowerCase()).value;
            const bandwidth = document.getElementById('bandwidth-' + band.toLowerCase()).value;
            
            setLoading(true);
            try {
                const response = await fetch('/api/config/' + band, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ channel: channel, bandwidth: bandwidth })
                });
                const data = await response.json();
                showNotification(data.message + ' (Click "Apply Config & Restart WiFi" to commit)', data.success ? 'success' : 'error');
            } catch (e) {
                showNotification('Error: ' + e.message, 'error');
            }
            setLoading(false);
        }
        
        // Apply all configurations and restart WiFi
        async function applyAllConfig() {
            // First, update all band configs from the dropdowns
            for (const band of ['2G', '5G', '6G']) {
                const channel = document.getElementById('channel-' + band.toLowerCase()).value;
                const bandwidth = document.getElementById('bandwidth-' + band.toLowerCase()).value;
                
                await fetch('/api/config/' + band, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ channel: channel, bandwidth: bandwidth })
                });
            }
            
            // Show modal
            const modal = document.getElementById('configModal');
            const status = document.getElementById('configStatus');
            const spinner = document.getElementById('configSpinner');
            const complete = document.getElementById('configComplete');
            
            modal.style.display = 'flex';
            spinner.style.display = 'block';
            complete.style.display = 'none';
            status.innerHTML = '<div class="config-line info">Starting configuration...</div>';
            
            try {
                // Add config lines for each band
                for (const band of ['2G', '5G', '6G']) {
                    const ch = document.getElementById('channel-' + band.toLowerCase()).value;
                    const bw = document.getElementById('bandwidth-' + band.toLowerCase()).value;
                    status.innerHTML += `<div class="config-line">${band}: CH ${ch}, ${bw}</div>`;
                }
                
                status.innerHTML += '<div class="config-line info">Sending to OpenWrt...</div>';
                
                const response = await fetch('/api/apply_config', { method: 'POST' });
                const data = await response.json();
                
                // Display results
                if (data.messages) {
                    for (const msg of data.messages) {
                        const cssClass = msg.includes('failed') || msg.includes('Failed') ? 'error' : 
                                        msg.includes('ready') || msg.includes('success') || msg.includes('Saved') ? 'success' : 'info';
                        status.innerHTML += `<div class="config-line ${cssClass}">${msg}</div>`;
                    }
                }
                
                if (data.interface_status) {
                    status.innerHTML += '<div class="config-line success">Interface Status:</div>';
                    status.innerHTML += `<pre style="font-size: 0.75rem; color: var(--text-secondary); margin: 0.5rem 0;">${data.interface_status}</pre>`;
                }
                
                spinner.style.display = 'none';
                complete.style.display = 'block';
                
                if (data.success) {
                    status.innerHTML += '<div class="config-line success">✓ All configurations applied successfully!</div>';
                } else {
                    status.innerHTML += '<div class="config-line error">✗ Configuration failed. Check messages above.</div>';
                }
                
            } catch (e) {
                status.innerHTML += `<div class="config-line error">Error: ${e.message}</div>`;
                spinner.style.display = 'none';
                complete.style.display = 'block';
            }
            
            // Scroll to bottom
            status.scrollTop = status.scrollHeight;
        }
        
        // Close config modal
        function closeConfigModal() {
            document.getElementById('configModal').style.display = 'none';
            location.reload();
        }
        
        // Refresh status
        function refreshStatus() {
            location.reload();
        }
        
        // Update time display
        async function updateTimeDisplay() {
            try {
                const response = await fetch('/api/time_info');
                const data = await response.json();
                
                document.getElementById('pcTime').textContent = data.pc_time ? data.pc_time.split(' ')[1] : '--:--:--';
                document.getElementById('openwrtTime').textContent = data.openwrt_time ? data.openwrt_time.split(' ')[1] : '--:--:--';
                
                const badge = document.getElementById('timeOffsetBadge');
                if (data.offset_seconds !== null) {
                    const absOffset = Math.abs(data.offset_seconds);
                    if (absOffset < 2) {
                        badge.textContent = '✓ Synced';
                        badge.style.background = 'rgba(34, 197, 94, 0.2)';
                        badge.style.color = 'var(--accent-2g)';
                    } else if (absOffset < 60) {
                        badge.textContent = `${data.offset_seconds > 0 ? '+' : ''}${data.offset_seconds.toFixed(0)}s`;
                        badge.style.background = 'rgba(245, 158, 11, 0.2)';
                        badge.style.color = 'var(--accent-warning)';
                    } else {
                        const minutes = Math.round(absOffset / 60);
                        badge.textContent = `${data.offset_seconds > 0 ? '+' : '-'}${minutes}m`;
                        badge.style.background = 'rgba(239, 68, 68, 0.2)';
                        badge.style.color = 'var(--accent-danger)';
                    }
                } else {
                    badge.textContent = '?';
                    badge.style.background = 'rgba(148, 163, 184, 0.2)';
                    badge.style.color = 'var(--text-secondary)';
                }
            } catch (e) {
                console.error('Failed to update time display:', e);
            }
        }
        
        // Manual sync time
        async function manualSyncTime() {
            setLoading(true);
            try {
                const response = await fetch('/api/sync_time', { method: 'POST' });
                const data = await response.json();
                
                if (data.success) {
                    showNotification('Time synchronized successfully!', 'success');
                    updateTimeDisplay();
                } else {
                    showNotification('Time sync failed: ' + data.message, 'error');
                }
            } catch (e) {
                showNotification('Time sync error: ' + e.message, 'error');
            }
            setLoading(false);
        }
        
        // Update time display periodically
        updateTimeDisplay();
        setInterval(updateTimeDisplay, 5000);
        
        // Load current WiFi config from OpenWrt on page load
        async function loadCurrentWifiConfig() {
            try {
                const response = await fetch('/api/get_wifi_config');
                const data = await response.json();
                
                if (data.success && data.config) {
                    console.log('[CONFIG] Loaded current WiFi config:', data.config);
                    
                    for (const [band, cfg] of Object.entries(data.config)) {
                        const bandLower = band.toLowerCase();
                        const channelSelect = document.getElementById('channel-' + bandLower);
                        const bandwidthSelect = document.getElementById('bandwidth-' + bandLower);
                        
                        if (channelSelect && cfg.channel) {
                            // Set channel dropdown
                            const channelValue = String(cfg.channel);
                            for (let option of channelSelect.options) {
                                if (option.value === channelValue) {
                                    channelSelect.value = channelValue;
                                    console.log(`[CONFIG] ${band} channel set to: ${channelValue}`);
                                    break;
                                }
                            }
                        }
                        
                        if (bandwidthSelect && cfg.bandwidth) {
                            // Set bandwidth dropdown
                            const bwValue = cfg.bandwidth;
                            for (let option of bandwidthSelect.options) {
                                if (option.value === bwValue) {
                                    bandwidthSelect.value = bwValue;
                                    console.log(`[CONFIG] ${band} bandwidth set to: ${bwValue}`);
                                    break;
                                }
                            }
                        }
                    }
                    
                    showNotification('Loaded current WiFi configuration from OpenWrt', 'success');
                }
            } catch (e) {
                console.error('[CONFIG] Failed to load WiFi config:', e);
            }
        }
        
        // Load config on page load (after connection is verified)
        setTimeout(loadCurrentWifiConfig, 1000);
        
        // ============== File Split Settings ==============
        
        // Load file split settings on page load
        async function loadFileSplitSettings() {
            try {
                const response = await fetch('/api/file_split');
                const data = await response.json();
                
                const checkbox = document.getElementById('fileSplitEnabled');
                const sizeSelect = document.getElementById('fileSplitSize');
                const sizeContainer = document.getElementById('fileSplitSizeContainer');
                const statusDiv = document.getElementById('fileSplitStatus');
                const splitNote = document.getElementById('splitFileNote');
                
                checkbox.checked = data.enabled;
                sizeSelect.value = data.size_mb;
                
                // Update UI state
                if (data.enabled) {
                    sizeContainer.style.opacity = '1';
                    statusDiv.innerHTML = `✂️ Split enabled: <strong>${data.size_mb} MB</strong> per file`;
                    statusDiv.style.color = 'var(--accent-2g)';
                    if (splitNote) splitNote.style.display = 'block';
                } else {
                    sizeContainer.style.opacity = '0.5';
                    statusDiv.innerHTML = '📁 Continuous capture (no split)';
                    statusDiv.style.color = 'var(--text-secondary)';
                    if (splitNote) splitNote.style.display = 'none';
                }
            } catch (e) {
                console.error('Failed to load file split settings:', e);
            }
        }
        
        // Update file split settings
        async function updateFileSplit() {
            const checkbox = document.getElementById('fileSplitEnabled');
            const sizeSelect = document.getElementById('fileSplitSize');
            const sizeContainer = document.getElementById('fileSplitSizeContainer');
            const statusDiv = document.getElementById('fileSplitStatus');
            const splitNote = document.getElementById('splitFileNote');
            
            const enabled = checkbox.checked;
            const size_mb = parseInt(sizeSelect.value);
            
            // Update UI immediately
            if (enabled) {
                sizeContainer.style.opacity = '1';
                statusDiv.innerHTML = `✂️ Split enabled: <strong>${size_mb} MB</strong> per file`;
                statusDiv.style.color = 'var(--accent-2g)';
                if (splitNote) splitNote.style.display = 'block';
            } else {
                sizeContainer.style.opacity = '0.5';
                statusDiv.innerHTML = '📁 Continuous capture (no split)';
                statusDiv.style.color = 'var(--text-secondary)';
                if (splitNote) splitNote.style.display = 'none';
            }
            
            try {
                const response = await fetch('/api/file_split', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled: enabled, size_mb: size_mb })
                });
                const data = await response.json();
                
                if (data.success) {
                    showNotification(data.message, 'success');
                }
            } catch (e) {
                showNotification('Failed to update file split settings: ' + e.message, 'error');
            }
        }
        
        // Load file split settings on page load
        loadFileSplitSettings();
        
        // Re-detect interface mapping
        async function redetectInterfaces() {
            setLoading(true);
            try {
                const response = await fetch('/api/detect_interfaces', { method: 'POST' });
                const data = await response.json();
                
                if (data.success) {
                    // Update UI with new mapping
                    document.getElementById('mapping2G').textContent = `2G=${data.interfaces['2G']}`;
                    document.getElementById('mapping5G').textContent = `5G=${data.interfaces['5G']}`;
                    document.getElementById('mapping6G').textContent = `6G=${data.interfaces['6G']}`;
                    
                    // Update card interface labels
                    document.getElementById('iface-2g').textContent = data.interfaces['2G'];
                    document.getElementById('iface-5g').textContent = data.interfaces['5G'];
                    document.getElementById('iface-6g').textContent = data.interfaces['6G'];
                    
                    // Update detection badge
                    const badge = document.getElementById('detectionBadge');
                    badge.textContent = '✓ Auto-detected';
                    badge.style.background = 'rgba(34, 197, 94, 0.2)';
                    badge.style.color = 'var(--accent-2g)';
                    
                    showNotification(data.message, 'success');
                } else {
                    showNotification('Interface detection failed. Using default mapping.', 'error');
                }
            } catch (e) {
                showNotification('Detection error: ' + e.message, 'error');
            }
            setLoading(false);
        }
        
        // Diagnose connection
        async function diagnoseConnection() {
            setLoading(true);
            try {
                const response = await fetch('/api/diagnose');
                const data = await response.json();
                
                // Build diagnosis modal content
                let statusHtml = `
                    <div style="background: var(--bg-dark); border-radius: 0.5rem; padding: 1rem; margin-bottom: 1rem; font-family: 'JetBrains Mono', monospace; font-size: 0.9rem;">
                        <div style="margin-bottom: 0.5rem;"><strong>Host:</strong> ${data.host}:${data.port}</div>
                        <div style="margin-bottom: 0.5rem;"><strong>User:</strong> ${data.user}</div>
                        <div style="margin-bottom: 0.5rem;"><strong>Password Set:</strong> ${data.password_set ? '<span style="color: var(--accent-2g);">Yes</span>' : '<span style="color: var(--accent-danger);">No</span>'}</div>
                        <div style="margin-bottom: 0.5rem;"><strong>SSH Keys Found:</strong> ${data.ssh_keys_found && data.ssh_keys_found.length > 0 ? '<span style="color: var(--accent-2g);">' + data.ssh_keys_found.join(', ') + '</span>' : '<span style="color: var(--text-secondary);">None</span>'}</div>
                        <div style="margin-bottom: 0.5rem;"><strong>Ping Test:</strong> ${data.ping_test ? '<span style="color: var(--accent-2g);">✓ OK</span>' : '<span style="color: var(--accent-danger);">✗ Failed</span>'}</div>
                        <div><strong>SSH Test:</strong> ${data.ssh_test ? '<span style="color: var(--accent-2g);">✓ OK</span>' : '<span style="color: var(--accent-danger);">✗ Failed</span>'}</div>
                        ${data.error ? `<div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border-color); color: var(--accent-danger);"><strong>Error:</strong> ${data.error}</div>` : ''}
                    </div>
                `;
                
                // Add solution section if needed
                let solutionHtml = '';
                if (!data.ssh_test && data.solution_text) {
                    solutionHtml = `
                        <div style="background: rgba(234, 179, 8, 0.1); border: 1px solid #eab308; border-radius: 0.5rem; padding: 1rem;">
                            <div style="font-weight: 600; color: #eab308; margin-bottom: 0.5rem;">💡 Solution</div>
                            <div style="color: var(--text-secondary); font-size: 0.9rem;">${data.solution_text}</div>
                        </div>
                    `;
                }
                
                // Show modal
                showDiagnoseModal(statusHtml, solutionHtml, data.ssh_test);
            } catch (e) {
                alert('Diagnosis failed: ' + e.message);
            }
            setLoading(false);
        }
        
        // Show diagnose modal dialog
        function showDiagnoseModal(statusHtml, solutionHtml, isConnected) {
            // Remove existing modal if any
            const existingModal = document.getElementById('diagnoseModal');
            if (existingModal) existingModal.remove();
            
            const modal = document.createElement('div');
            modal.id = 'diagnoseModal';
            modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); display: flex; justify-content: center; align-items: center; z-index: 9999;';
            modal.innerHTML = `
                <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 1rem; padding: 1.5rem; max-width: 500px; width: 90%; max-height: 90vh; overflow-y: auto;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                        <h3 style="margin: 0; font-size: 1.25rem;">🔍 Connection Diagnosis</h3>
                        <button onclick="closeDiagnoseModal()" style="background: none; border: none; color: var(--text-secondary); font-size: 1.5rem; cursor: pointer; padding: 0; line-height: 1;">&times;</button>
                    </div>
                    ${statusHtml}
                    ${solutionHtml}
                    <div style="display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 1rem;">
                        <button onclick="closeDiagnoseModal()" style="padding: 0.75rem 1.5rem; background: var(--bg-dark); border: 1px solid var(--border-color); border-radius: 0.5rem; color: var(--text-primary); cursor: pointer;">OK</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }
        
        function closeDiagnoseModal() {
            const modal = document.getElementById('diagnoseModal');
            if (modal) modal.remove();
        }
        
        
        // Auto-refresh every 5 seconds if any capture is running
        {% if status['2G']['running'] or status['5G']['running'] or status['6G']['running'] %}
        setInterval(() => {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    for (const [band, info] of Object.entries(data)) {
                        const bandLower = band.toLowerCase();
                        const statusEl = document.getElementById('status-' + bandLower);
                        const durationEl = document.getElementById('duration-' + bandLower);
                        const packetsEl = document.getElementById('packets-' + bandLower);
                        
                        if (statusEl) {
                            statusEl.textContent = info.running ? 'CAPTURING' : 'IDLE';
                            statusEl.className = 'status-badge ' + (info.running ? 'status-running' : 'status-idle');
                        }
                        if (durationEl) durationEl.textContent = info.duration || '--:--';
                        if (packetsEl) packetsEl.textContent = info.packets || 0;
                    }
                });
        }, 5000);
        {% endif %}
    </script>
</body>
</html>
"""


# ============== Routes ==============
@app.route('/')
def index():
    connected = test_connection()
    
    # Calculate duration for running captures
    status = {}
    for band in ["2G", "5G", "6G"]:
        status[band] = {
            "running": capture_status[band]["running"],
            "packets": capture_status[band]["packets"],
            "duration": None
        }
        if capture_status[band]["running"] and capture_status[band]["start_time"]:
            delta = datetime.now() - capture_status[band]["start_time"]
            minutes, seconds = divmod(int(delta.total_seconds()), 60)
            status[band]["duration"] = f"{minutes:02d}:{seconds:02d}"
    
    # Prepare detection status for template
    detection_status = {
        "detected": interface_detection_status["detected"],
        "method": interface_detection_status["detection_method"],
        "last_detection": interface_detection_status["last_detection"].strftime("%Y-%m-%d %H:%M:%S") if interface_detection_status["last_detection"] else None
    }
    
    return render_template_string(
        HTML_TEMPLATE,
        connected=connected,
        status=status,
        channels=CHANNELS,
        bandwidths=BANDWIDTHS,
        channel_config=channel_config,
        download_path=DOWNLOADS_FOLDER,
        interfaces=INTERFACES,
        uci_wifi_map=UCI_WIFI_MAP,
        detection_status=detection_status
    )


@app.route('/api/status')
def get_status():
    status = {}
    for band in ["2G", "5G", "6G"]:
        status[band] = {
            "running": capture_status[band]["running"],
            "packets": capture_status[band]["packets"],
            "duration": None
        }
        if capture_status[band]["running"] and capture_status[band]["start_time"]:
            delta = datetime.now() - capture_status[band]["start_time"]
            minutes, seconds = divmod(int(delta.total_seconds()), 60)
            status[band]["duration"] = f"{minutes:02d}:{seconds:02d}"
    return jsonify(status)


@app.route('/api/start/<band>', methods=['POST'])
def api_start(band):
    band = band.upper()
    if band not in INTERFACES:
        return jsonify({"success": False, "message": f"Invalid band: {band}"})
    
    success, message = start_capture_thread(band)
    return jsonify({"success": success, "message": message})


@app.route('/api/stop/<band>', methods=['POST'])
def api_stop(band):
    band = band.upper()
    if band not in INTERFACES:
        return jsonify({"success": False, "message": f"Invalid band: {band}"})
    
    success, message, path = stop_capture(band)
    return jsonify({"success": success, "message": message, "path": path})


@app.route('/api/start_all', methods=['POST'])
def api_start_all():
    results = {}
    for band in ["2G", "5G", "6G"]:
        success, message = start_capture_thread(band)
        results[band] = {"success": success, "message": message}
    return jsonify({"results": results})


@app.route('/api/stop_all', methods=['POST'])
def api_stop_all():
    results = stop_all_captures()
    return jsonify({"results": results})


@app.route('/api/config/<band>', methods=['POST'])
def api_config(band):
    """Update channel config for a single band (does not apply to router yet)"""
    band = band.upper()
    if band not in INTERFACES:
        return jsonify({"success": False, "message": f"Invalid band: {band}"})
    
    data = request.get_json()
    channel = int(data.get('channel', channel_config[band]['channel']))
    bandwidth = data.get('bandwidth', channel_config[band]['bandwidth'])
    
    success, message = set_channel(band, channel, bandwidth)
    return jsonify({"success": success, "message": message})


@app.route('/api/apply_config', methods=['POST'])
def api_apply_config():
    """Apply all channel configurations to OpenWrt and restart wifi"""
    # Check if any capture is running
    for band in ["2G", "5G", "6G"]:
        if capture_status[band]["running"]:
            return jsonify({
                "success": False, 
                "message": f"Cannot apply config while {band} capture is running. Stop all captures first."
            })
    
    results = apply_all_and_restart_wifi()
    return jsonify(results)


@app.route('/api/get_wifi_config')
def api_get_wifi_config():
    """Get current WiFi configuration from OpenWrt"""
    config = get_current_wifi_config()
    return jsonify({"success": True, "config": config})


@app.route('/api/test_connection')
def api_test_connection():
    connected = test_connection()
    return jsonify({
        "connected": connected, 
        "host": OPENWRT_HOST,
        "port": SSH_PORT,
        "user": OPENWRT_USER,
        "auth_method": "key" if SSH_KEY_PATH else ("password" if OPENWRT_PASSWORD else "default"),
        "error": last_connection_error if not connected else None
    })


@app.route('/api/diagnose')
def api_diagnose():
    """Diagnostic endpoint for troubleshooting connection issues"""
    import subprocess
    import sys
    from pathlib import Path
    
    # Check for SSH keys
    ssh_dir = Path.home() / ".ssh"
    ssh_keys_found = []
    for key_name in ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"]:
        key_path = ssh_dir / key_name
        if key_path.exists():
            ssh_keys_found.append(key_name)
    
    results = {
        "host": OPENWRT_HOST,
        "port": SSH_PORT,
        "user": OPENWRT_USER,
        "password_set": OPENWRT_PASSWORD is not None and OPENWRT_PASSWORD != "",
        "no_password_mode": OPENWRT_PASSWORD is None or OPENWRT_PASSWORD == "",
        "key_path": SSH_KEY_PATH,
        "ssh_keys_found": ssh_keys_found,
        "has_ssh_key": len(ssh_keys_found) > 0,
        "ping_test": False,
        "ssh_test": False,
        "error": None,
        "solution": None
    }
    
    # Hide console window on Windows
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    
    # Test ping
    try:
        ping_result = subprocess.run(
            ["ping", "-n", "1", "-w", "2000", OPENWRT_HOST],
            capture_output=True,
            timeout=5,
            creationflags=creationflags
        )
        results["ping_test"] = ping_result.returncode == 0
    except Exception as e:
        results["ping_error"] = str(e)
    
    # Test SSH connection
    results["ssh_test"] = test_connection()
    results["error"] = last_connection_error
    
    # Provide specific solution based on diagnosis
    if not results["ping_test"]:
        results["solution"] = "network"
        results["solution_text"] = "Cannot reach OpenWrt router. Check: 1) Router is powered on, 2) PC is connected to router network, 3) Router IP is 192.168.1.1"
    elif not results["ssh_test"]:
        results["solution"] = "ssh_failed"
        results["solution_text"] = "SSH connection failed. Check: 1) SSH/Dropbear is enabled on OpenWrt, 2) Try: ssh root@192.168.1.1 in terminal"
    
    return jsonify(results)


@app.route('/api/time_info')
def api_time_info():
    """Get time information from PC and OpenWrt"""
    info = get_time_info()
    info["last_sync"] = time_sync_status["last_sync"].strftime("%Y-%m-%d %H:%M:%S") if time_sync_status["last_sync"] else None
    return jsonify(info)


@app.route('/api/sync_time', methods=['POST'])
def api_sync_time():
    """Manually sync OpenWrt time with PC time"""
    success, message = sync_openwrt_time()
    info = get_time_info()
    return jsonify({
        "success": success,
        "message": message,
        "time_info": info
    })


@app.route('/api/file_split', methods=['GET'])
def api_get_file_split():
    """Get current file split configuration"""
    return jsonify({
        "enabled": file_split_config["enabled"],
        "size_mb": file_split_config["size_mb"]
    })


@app.route('/api/file_split', methods=['POST'])
def api_set_file_split():
    """Update file split configuration"""
    data = request.get_json()
    
    if "enabled" in data:
        file_split_config["enabled"] = bool(data["enabled"])
    
    if "size_mb" in data:
        size = int(data["size_mb"])
        # Validate size (minimum 10MB, maximum 2000MB)
        if size < 10:
            size = 10
        elif size > 2000:
            size = 2000
        file_split_config["size_mb"] = size
    
    return jsonify({
        "success": True,
        "enabled": file_split_config["enabled"],
        "size_mb": file_split_config["size_mb"],
        "message": f"File split {'enabled' if file_split_config['enabled'] else 'disabled'}" + 
                   (f" ({file_split_config['size_mb']}MB per file)" if file_split_config['enabled'] else "")
    })


@app.route('/api/interface_mapping')
def api_get_interface_mapping():
    """Get current interface mapping and detection status"""
    return jsonify({
        "interfaces": INTERFACES,
        "uci_wifi_map": UCI_WIFI_MAP,
        "detection_status": {
            "detected": interface_detection_status["detected"],
            "last_detection": interface_detection_status["last_detection"].strftime("%Y-%m-%d %H:%M:%S") if interface_detection_status["last_detection"] else None,
            "detection_method": interface_detection_status["detection_method"],
            "detected_mapping": interface_detection_status["detected_mapping"]
        }
    })


@app.route('/api/detect_interfaces', methods=['POST'])
def api_detect_interfaces():
    """Force re-detection of interface mapping"""
    global interface_detection_status
    
    # Reset detection status to force re-detection
    interface_detection_status["detected"] = False
    
    # Run detection
    success = detect_interface_mapping()
    
    return jsonify({
        "success": success,
        "interfaces": INTERFACES,
        "uci_wifi_map": UCI_WIFI_MAP,
        "detection_status": {
            "detected": interface_detection_status["detected"],
            "last_detection": interface_detection_status["last_detection"].strftime("%Y-%m-%d %H:%M:%S") if interface_detection_status["last_detection"] else None,
            "detection_method": interface_detection_status["detection_method"]
        },
        "message": f"Detection {'successful' if success else 'failed'}. Mapping: 2G={INTERFACES.get('2G')}, 5G={INTERFACES.get('5G')}, 6G={INTERFACES.get('6G')}"
    })


if __name__ == '__main__':
    # 從環境變數讀取 PORT，預設 5000
    SERVER_PORT = int(os.environ.get('FLASK_PORT', 5000))
    
    print("=" * 60)
    print("  WiFi Sniffer Web Control Panel")
    print("=" * 60)
    print(f"  OpenWrt Host: {OPENWRT_HOST}")
    print(f"  Download Folder: {DOWNLOADS_FOLDER}")
    print(f"  Default Interface Mapping (will auto-detect on connection):")
    for band, iface in INTERFACES.items():
        print(f"    - {band}: {iface}")
    print("-" * 60)
    print("  NOTE: Interface mapping will be auto-detected when")
    print("  connected to OpenWrt. This ensures channel config")
    print("  works correctly on different hardware units.")
    print("=" * 60)
    print(f"  Starting web server on http://127.0.0.1:{SERVER_PORT}")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=True, threaded=True)

