"""
Capture Manager
===============
Manages WiFi packet capture sessions with state tracking.
"""

import os
import threading
import time
from datetime import datetime
from typing import Dict, Tuple, Optional, Any

from ..config import DOWNLOADS_FOLDER, DEFAULT_INTERFACES, DEFAULT_UCI_WIFI_MAP
from ..ssh import run_ssh_command, download_file_scp


class CaptureManager:
    """
    Manages capture state and operations for all bands.
    
    Features:
    - Thread-safe state management
    - Auto time sync before capture
    - Interface auto-detection
    - File split support
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        # Capture status for each band
        self._status: Dict[str, Dict[str, Any]] = {
            "2G": {"running": False, "start_time": None, "packets": 0},
            "5G": {"running": False, "start_time": None, "packets": 0},
            "6G": {"running": False, "start_time": None, "packets": 0}
        }
        
        # Interface mapping (will be auto-detected)
        self.interfaces = dict(DEFAULT_INTERFACES)
        self.uci_wifi_map = dict(DEFAULT_UCI_WIFI_MAP)
        
        # Detection status
        self.detection_status = {
            "detected": False,
            "last_detection": None,
            "detection_method": None,
            "detected_mapping": None
        }
        
        # File split configuration
        self.file_split_config = {
            "enabled": False,
            "size_mb": 200,
        }
        
        # Channel configuration
        self.channel_config = {
            "2G": {"channel": 6, "bandwidth": "HT40"},
            "5G": {"channel": 36, "bandwidth": "EHT160"},
            "6G": {"channel": 37, "bandwidth": "EHT320"}
        }
        
        # Time sync status
        self.time_sync_status = {
            "last_sync": None,
            "offset_seconds": None,
            "success": False
        }
        
        # Last connection error
        self.last_connection_error = None
        
        self._status_lock = threading.Lock()
        self._socketio = None  # Will be set by app factory
        self._initialized = True
    
    def set_socketio(self, socketio):
        """Set SocketIO instance for broadcasting updates"""
        self._socketio = socketio
    
    def _broadcast_status_update(self):
        """Broadcast capture status update to all connected clients"""
        if self._socketio:
            try:
                self._socketio.emit('status_update', self.get_all_status())
            except Exception as e:
                print(f"[WebSocket] Broadcast error: {e}")
    
    def get_status(self, band: str) -> Dict[str, Any]:
        """Get capture status for a band"""
        with self._status_lock:
            status = self._status[band].copy()
            if status["running"] and status["start_time"]:
                delta = datetime.now() - status["start_time"]
                minutes, seconds = divmod(int(delta.total_seconds()), 60)
                status["duration"] = f"{minutes:02d}:{seconds:02d}"
            else:
                status["duration"] = None
            return status
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get capture status for all bands"""
        return {band: self.get_status(band) for band in ["2G", "5G", "6G"]}
    
    def sync_time(self) -> Tuple[bool, str]:
        """Sync OpenWrt system time with local PC time"""
        try:
            pc_time = datetime.now()
            time_str = pc_time.strftime("%Y-%m-%d %H:%M:%S")
            
            # Get OpenWrt's current time to calculate offset
            success, stdout, stderr = run_ssh_command("date '+%Y-%m-%d %H:%M:%S'", timeout=10)
            
            if success and stdout.strip():
                try:
                    openwrt_time_before = datetime.strptime(stdout.strip(), "%Y-%m-%d %H:%M:%S")
                    offset = (pc_time - openwrt_time_before).total_seconds()
                    self.time_sync_status["offset_seconds"] = offset
                    print(f"[TIME SYNC] Offset: {offset:.1f} seconds")
                except Exception as e:
                    print(f"[TIME SYNC] Could not parse OpenWrt time: {e}")
            
            # Set the time on OpenWrt
            set_cmd = f'date -s "{time_str}"'
            success, stdout, stderr = run_ssh_command(set_cmd, timeout=10)
            
            if success:
                self.time_sync_status["last_sync"] = pc_time
                self.time_sync_status["success"] = True
                return True, f"Time synced: {time_str}"
            else:
                self.time_sync_status["success"] = False
                return False, f"Failed to set time: {stderr}"
                
        except Exception as e:
            self.time_sync_status["success"] = False
            return False, f"Time sync error: {str(e)}"
    
    def get_time_info(self) -> Dict[str, Any]:
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
    
    def detect_interfaces(self) -> bool:
        """Auto-detect interface mapping from OpenWrt"""
        import re
        
        print("[DETECT] Starting interface auto-detection...")
        
        try:
            # Method 1: Use iwconfig to get frequency
            success, stdout, stderr = run_ssh_command(
                "iwconfig 2>/dev/null | grep -E '^ath[0-2]|Frequency'",
                timeout=10
            )
            
            if success and stdout.strip():
                detected = {}
                lines = stdout.strip().split('\n')
                current_iface = None
                
                for line in lines:
                    line = line.strip()
                    if line.startswith('ath'):
                        current_iface = line.split()[0]
                    elif 'Frequency' in line and current_iface:
                        freq_match = re.search(r'Frequency[:\s]*(\d+\.?\d*)', line)
                        if freq_match:
                            freq = float(freq_match.group(1))
                            if freq < 3:
                                detected[current_iface] = "2G"
                            elif freq < 6:
                                detected[current_iface] = "5G"
                            else:
                                detected[current_iface] = "6G"
                            print(f"[DETECT] {current_iface}: {freq} GHz -> {detected[current_iface]}")
                
                if len(detected) >= 3:
                    new_interfaces = {}
                    for iface, band in detected.items():
                        new_interfaces[band] = iface
                    
                    if "2G" in new_interfaces and "5G" in new_interfaces and "6G" in new_interfaces:
                        self.interfaces = new_interfaces
                        self.detection_status["detected"] = True
                        self.detection_status["last_detection"] = datetime.now()
                        self.detection_status["detection_method"] = "iwconfig_frequency"
                        self.detection_status["detected_mapping"] = dict(self.interfaces)
                        print(f"[DETECT] Success! Mapping: {self.interfaces}")
                        
                        # Detect UCI radio mapping and sync channel config
                        self._detect_uci_wifi_mapping()
                        self.sync_channel_config_from_openwrt()
                        return True
            
            print("[DETECT] Auto-detection failed, using default mapping")
            return False
            
        except Exception as e:
            print(f"[DETECT] Error: {e}")
            return False
    
    def _detect_uci_wifi_mapping(self):
        """Detect UCI radio mapping based on channel and read current config"""
        try:
            # Get channel, htmode and band info from UCI
            success, stdout, stderr = run_ssh_command(
                "uci show wireless | grep -E 'wifi[0-2]\\.(channel|htmode|band|hwmode)'",
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
                
                print(f"[UCI DETECT] Raw data: {uci_data}")
                
                for radio, config in uci_data.items():
                    band = None
                    try:
                        channel = int(config.get('channel', 0))
                        htmode = config.get('htmode', '')
                        
                        # Determine band from channel
                        if channel > 0:
                            if channel <= 14:
                                band = "2G"
                            elif channel <= 177:
                                band = "5G"
                            else:
                                band = "6G"
                            
                            self.uci_wifi_map[band] = radio
                            
                            # Sync local channel_config with actual OpenWrt settings
                            self.channel_config[band]["channel"] = channel
                            if htmode:
                                self.channel_config[band]["bandwidth"] = htmode
                            
                            print(f"[UCI DETECT] {radio} -> {band}: CH{channel} {htmode}")
                    except Exception as e:
                        print(f"[UCI DETECT] Error parsing {radio}: {e}")
                
                print(f"[UCI DETECT] Mapping: {self.uci_wifi_map}")
                print(f"[UCI DETECT] Channel Config: {self.channel_config}")
                
        except Exception as e:
            print(f"[UCI DETECT] Error: {e}")
    
    def sync_channel_config_from_openwrt(self) -> bool:
        """
        Sync local channel_config with actual OpenWrt settings.
        Call this after connection is established to get real values.
        """
        try:
            print("[CONFIG SYNC] Reading current WiFi config from OpenWrt...")
            
            for band, uci_radio in self.uci_wifi_map.items():
                if not uci_radio:
                    continue
                    
                success, stdout, stderr = run_ssh_command(
                    f"uci get wireless.{uci_radio}.channel 2>/dev/null; uci get wireless.{uci_radio}.htmode 2>/dev/null",
                    timeout=10
                )
                
                if success and stdout.strip():
                    lines = stdout.strip().split('\n')
                    if len(lines) >= 1:
                        try:
                            channel = int(lines[0]) if lines[0].isdigit() else 0
                            htmode = lines[1] if len(lines) > 1 else self.channel_config[band]["bandwidth"]
                            
                            if channel > 0:
                                self.channel_config[band]["channel"] = channel
                                self.channel_config[band]["bandwidth"] = htmode
                                print(f"[CONFIG SYNC] {band} ({uci_radio}): CH{channel} {htmode}")
                        except Exception as e:
                            print(f"[CONFIG SYNC] Parse error for {band}: {e}")
            
            print(f"[CONFIG SYNC] Final config: {self.channel_config}")
            return True
            
        except Exception as e:
            print(f"[CONFIG SYNC] Error: {e}")
            return False
    
    def start_capture(self, band: str, auto_sync_time: bool = True) -> Tuple[bool, str]:
        """Start packet capture for specified band"""
        interface = self.interfaces.get(band)
        if not interface:
            return False, f"Unknown band: {band}"
        
        with self._status_lock:
            if self._status[band]["running"]:
                return False, f"{band} capture already running"
        
        try:
            # Auto-sync time before starting capture
            if auto_sync_time:
                other_bands_running = any(
                    self._status[b]["running"] for b in ["2G", "5G", "6G"] if b != band
                )
                if not other_bands_running:
                    print(f"[CAPTURE] Syncing time before starting {band} capture...")
                    sync_success, sync_msg = self.sync_time()
                    if sync_success:
                        print(f"[CAPTURE] Time sync successful")
            
            remote_path = f"/tmp/{band}.pcap"
            
            # Build tcpdump command
            if self.file_split_config["enabled"]:
                size_mb = self.file_split_config["size_mb"]
                tcpdump_cmd = f"tcpdump -i {interface} -U -s0 -w {remote_path} -C {size_mb}"
            else:
                tcpdump_cmd = f"tcpdump -i {interface} -U -s0 -w {remote_path}"
            
            cmd = f"""
                PID=$(ps | grep "tcpdump -i {interface}" | grep -v grep | awk '{{print $1}}')
                [ -n "$PID" ] && kill $PID 2>/dev/null
                rm -f {remote_path} {remote_path}[0-9]* 
                ({tcpdump_cmd} &)
                sleep 1
                ps | grep "tcpdump -i {interface}" | grep -v grep && echo 'TCPDUMP_STARTED' || echo 'TCPDUMP_FAILED'
            """
            
            success, stdout, stderr = run_ssh_command(cmd, timeout=15)
            
            if not success or "TCPDUMP_FAILED" in stdout:
                return False, f"Failed to start tcpdump: {stderr or stdout}"
            
            if "TCPDUMP_STARTED" not in stdout:
                return False, "tcpdump verification failed"
            
            with self._status_lock:
                self._status[band]["running"] = True
                self._status[band]["start_time"] = datetime.now()
                self._status[band]["packets"] = 0
            
            # Start monitoring thread
            monitor_thread = threading.Thread(target=self._monitor_capture, args=(band,))
            monitor_thread.daemon = True
            monitor_thread.start()
            
            # Broadcast status update via WebSocket
            self._broadcast_status_update()
            
            return True, f"{band} capture started on {interface}"
        
        except Exception as e:
            return False, f"Error starting capture: {str(e)}"
    
    def _monitor_capture(self, band: str):
        """Monitor packet count for a capture"""
        while self._status[band]["running"]:
            try:
                remote_path = f"/tmp/{band}.pcap"
                success, stdout, stderr = run_ssh_command(
                    f"ls -la {remote_path} 2>/dev/null | awk '{{print $5}}'",
                    timeout=5
                )
                if success and stdout.strip():
                    try:
                        size = int(stdout.strip())
                        with self._status_lock:
                            self._status[band]["packets"] = size // 100
                    except:
                        pass
            except:
                pass
            time.sleep(3)
    
    def stop_capture(self, band: str) -> Tuple[bool, str, Optional[str]]:
        """Stop packet capture and download file(s)"""
        with self._status_lock:
            if not self._status[band]["running"]:
                return False, f"{band} capture not running", None
        
        try:
            interface = self.interfaces.get(band)
            kill_cmd = f"PID=$(ps | grep 'tcpdump -i {interface}' | grep -v grep | awk '{{print $1}}'); [ -n \"$PID\" ] && kill $PID 2>/dev/null || true"
            run_ssh_command(kill_cmd, timeout=10)
            time.sleep(2)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            remote_path = f"/tmp/{band}.pcap"
            
            success, stdout, stderr = run_ssh_command(f"ls -1 {remote_path}* 2>/dev/null", timeout=5)
            
            if not success or not stdout.strip():
                with self._status_lock:
                    self._status[band]["running"] = False
                    self._status[band]["start_time"] = None
                return False, "No capture file found on router", None
            
            remote_files = [f.strip() for f in stdout.strip().split('\n') if f.strip()]
            print(f"[CAPTURE] Found {len(remote_files)} capture file(s) for {band}")
            
            downloaded_files = []
            total_size = 0
            
            if len(remote_files) == 1:
                local_filename = f"{band}_sniffer_{timestamp}.pcap"
                local_path = os.path.join(DOWNLOADS_FOLDER, local_filename)
                
                if download_file_scp(remote_files[0], local_path):
                    if os.path.exists(local_path):
                        file_size = os.path.getsize(local_path)
                        total_size = file_size
                        downloaded_files.append(local_filename)
            else:
                for i, remote_file in enumerate(remote_files):
                    part_num = i + 1
                    local_filename = f"{band}_sniffer_{timestamp}_part{part_num:03d}.pcap"
                    local_path = os.path.join(DOWNLOADS_FOLDER, local_filename)
                    
                    if download_file_scp(remote_file, local_path):
                        if os.path.exists(local_path):
                            file_size = os.path.getsize(local_path)
                            total_size += file_size
                            downloaded_files.append(local_filename)
            
            # Remove remote files
            run_ssh_command(f"rm -f {remote_path}*", timeout=5)
            
            with self._status_lock:
                self._status[band]["running"] = False
                self._status[band]["start_time"] = None
            
            # Broadcast status update via WebSocket
            self._broadcast_status_update()
            
            if downloaded_files:
                if len(downloaded_files) == 1:
                    return True, f"Saved: {downloaded_files[0]} ({total_size:,} bytes)", os.path.join(DOWNLOADS_FOLDER, downloaded_files[0])
                else:
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
            with self._status_lock:
                self._status[band]["running"] = False
                self._status[band]["start_time"] = None
            return False, f"Error stopping capture: {str(e)}", None
    
    def stop_all_captures(self) -> Dict[str, Dict[str, Any]]:
        """Stop all running captures"""
        results = {}
        for band in ["2G", "5G", "6G"]:
            if self._status[band]["running"]:
                success, msg, path = self.stop_capture(band)
                results[band] = {"success": success, "message": msg, "path": path}
        return results
    
    def set_channel_config(self, band: str, channel: int, bandwidth: str = None) -> Tuple[bool, str]:
        """Set channel configuration for a band"""
        self.channel_config[band]["channel"] = channel
        if bandwidth:
            self.channel_config[band]["bandwidth"] = bandwidth
        return True, f"Config updated for {band}: CH{channel} {bandwidth or ''}"
    
    def apply_channel_config(self, band: str) -> Tuple[bool, str]:
        """Apply channel configuration to OpenWrt"""
        uci_radio = self.uci_wifi_map.get(band)
        if not uci_radio:
            return False, f"Unknown band: {band}"
        
        channel = self.channel_config[band]["channel"]
        bandwidth = self.channel_config[band]["bandwidth"]
        
        commands = [
            f"uci set wireless.{uci_radio}.channel={channel}",
            f"uci set wireless.{uci_radio}.htmode={bandwidth}",
        ]
        
        for cmd in commands:
            success, stdout, stderr = run_ssh_command(cmd, timeout=10)
            if not success:
                return False, f"Failed to execute: {cmd} - {stderr}"
            print(f"[UCI] {cmd}")
        
        return True, f"{band} config set: CH{channel} {bandwidth}"
    
    def apply_all_and_restart_wifi(self) -> Dict[str, Any]:
        """Apply all channel configurations and restart wifi"""
        results = {"success": True, "messages": [], "bands": {}}
        
        for band in ["2G", "5G", "6G"]:
            success, msg = self.apply_channel_config(band)
            results["bands"][band] = {"success": success, "message": msg}
            results["messages"].append(f"{band}: {msg}")
            if not success:
                results["success"] = False
        
        if not results["success"]:
            return results
        
        # Commit UCI changes
        success, stdout, stderr = run_ssh_command("uci commit wireless", timeout=10)
        if not success:
            results["success"] = False
            results["messages"].append(f"UCI commit failed: {stderr}")
            return results
        
        results["messages"].append("UCI changes committed")
        
        # Reload wifi configuration using 'wifi load'
        # This is the correct command to apply channel changes in OpenWrt
        results["messages"].append("Executing 'wifi load' to apply changes...")
        print("[WIFI] Executing 'wifi load'...")
        
        success, stdout, stderr = run_ssh_command("wifi load", timeout=60)
        if not success:
            # Try alternative: run in background if timeout
            results["messages"].append("Trying 'wifi load' in background...")
            restart_cmd = "nohup wifi load > /dev/null 2>&1 &"
            success, stdout, stderr = run_ssh_command(restart_cmd, timeout=10)
            if not success:
                results["success"] = False
                results["messages"].append(f"Wifi load failed: {stderr}")
                return results
        
        results["messages"].append("Wifi restart initiated, waiting for interfaces...")
        
        # Poll for interfaces to be ready (increased wait time)
        max_wait = 90  # Increased from 30 to 90 seconds
        start_time = time.time()
        interfaces_ready = False
        last_check = ""
        
        while time.time() - start_time < max_wait:
            time.sleep(5)  # Check every 5 seconds
            elapsed = int(time.time() - start_time)
            
            success, stdout, stderr = run_ssh_command("iwconfig 2>/dev/null | grep -E '^ath[0-2]'", timeout=10)
            
            if success:
                found_interfaces = []
                if "ath0" in stdout:
                    found_interfaces.append("ath0")
                if "ath1" in stdout:
                    found_interfaces.append("ath1")
                if "ath2" in stdout:
                    found_interfaces.append("ath2")
                
                current_check = ",".join(found_interfaces)
                if current_check != last_check:
                    print(f"[WIFI] {elapsed}s: Found interfaces: {current_check}")
                    last_check = current_check
                
                if len(found_interfaces) == 3:
                    interfaces_ready = True
                    break
            
            # Progress update
            if elapsed % 15 == 0:
                print(f"[WIFI] Waiting... {elapsed}s / {max_wait}s")
        
        if interfaces_ready:
            results["messages"].append("All interfaces ready!")
            # Wait a bit more for interfaces to stabilize
            time.sleep(3)
            
            success, stdout, stderr = run_ssh_command("iwconfig 2>/dev/null | grep -E 'Frequency|^ath'", timeout=10)
            if success:
                results["interface_status"] = stdout
            
            # Re-detect interface mapping after wifi restart
            self.detect_interfaces()
        else:
            results["success"] = False
            results["messages"].append(f"Timeout waiting for interfaces ({max_wait}s)")
        
        return results
    
    def get_current_wifi_config(self, force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        Get current channel configuration from OpenWrt.
        Also syncs local channel_config with actual values.
        
        Args:
            force_refresh: If True, always query OpenWrt. If False, return cached config.
        """
        if force_refresh:
            # Query OpenWrt for current config
            for band, uci_radio in self.uci_wifi_map.items():
                if not uci_radio:
                    continue
                    
                success, stdout, stderr = run_ssh_command(
                    f"uci get wireless.{uci_radio}.channel 2>/dev/null; uci get wireless.{uci_radio}.htmode 2>/dev/null",
                    timeout=10
                )
                if success and stdout.strip():
                    lines = stdout.strip().split('\n')
                    try:
                        channel = int(lines[0]) if lines[0].isdigit() else 0
                        htmode = lines[1] if len(lines) > 1 else self.channel_config[band]["bandwidth"]
                        
                        if channel > 0:
                            self.channel_config[band]["channel"] = channel
                            self.channel_config[band]["bandwidth"] = htmode
                            print(f"[WIFI CONFIG] {band}: CH{channel} {htmode}")
                    except Exception as e:
                        print(f"[WIFI CONFIG] Parse error for {band}: {e}")
        
        # Return the current channel_config
        return dict(self.channel_config)
    
    def get_channel_config(self) -> Dict[str, Dict[str, Any]]:
        """Get the current local channel configuration (without querying OpenWrt)"""
        return dict(self.channel_config)


# Global singleton instance
capture_manager = CaptureManager()


# Convenience functions
def start_capture(band: str, auto_sync_time: bool = True) -> Tuple[bool, str]:
    return capture_manager.start_capture(band, auto_sync_time)


def stop_capture(band: str) -> Tuple[bool, str, Optional[str]]:
    return capture_manager.stop_capture(band)


def stop_all_captures() -> Dict[str, Dict[str, Any]]:
    return capture_manager.stop_all_captures()


def get_capture_status(band: str = None) -> Dict[str, Any]:
    if band:
        return capture_manager.get_status(band)
    return capture_manager.get_all_status()
