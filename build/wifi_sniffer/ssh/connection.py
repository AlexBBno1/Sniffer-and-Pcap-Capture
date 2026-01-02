"""
SSH Connection Pool
===================
Reusable SSH connection pool for improved performance.
Caches SSH executable path and provides connection reuse.
"""

import os
import sys
import subprocess
import threading
import queue
import shutil
from typing import Optional, Tuple
from ..config import (
    OPENWRT_HOST, OPENWRT_USER, OPENWRT_PASSWORD,
    SSH_KEY_PATH, SSH_PORT, SSH_POOL_SIZE,
    SSH_CONNECT_TIMEOUT, SSH_COMMAND_TIMEOUT
)


class SSHConnectionPool:
    """
    SSH Connection Pool for efficient command execution.
    
    Features:
    - Caches SSH executable path (found once)
    - Thread-safe command execution
    - Configurable timeout and options
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern for global pool access"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._ssh_exe: Optional[str] = None
        self._pubkey_option: Optional[str] = None
        self._startupinfo = None
        self._command_lock = threading.Lock()
        
        # Initialize on first use
        self._find_ssh_executable()
        self._detect_pubkey_option()
        self._setup_startupinfo()
        
        self._initialized = True
        print(f"[SSH Pool] Initialized with SSH: {self._ssh_exe}")
    
    def _find_ssh_executable(self) -> str:
        """Find and cache SSH executable path (only once)"""
        if self._ssh_exe:
            return self._ssh_exe
            
        # Try to find ssh in PATH first
        ssh_path = shutil.which("ssh")
        if ssh_path:
            self._ssh_exe = ssh_path
            return self._ssh_exe
        
        # Common Windows SSH locations
        possible_paths = [
            r"C:\Windows\System32\OpenSSH\ssh.exe",
            r"C:\Program Files\OpenSSH\ssh.exe",
            r"C:\Program Files (x86)\OpenSSH\ssh.exe",
            rf"C:\Users\{os.environ.get('USERNAME', '')}\AppData\Local\Microsoft\WindowsApps\ssh.exe",
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                self._ssh_exe = path
                return self._ssh_exe
        
        # Fallback to just "ssh"
        self._ssh_exe = "ssh"
        return self._ssh_exe
    
    def _detect_pubkey_option(self):
        """Detect which pubkey option is supported (cached)"""
        if self._pubkey_option is not None:
            return
            
        for opt in ("PubkeyAcceptedAlgorithms", "PubkeyAcceptedKeyTypes"):
            try:
                probe = subprocess.run(
                    [self._ssh_exe, "-G", "-o", f"{opt}=+ssh-rsa", "dummy"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    startupinfo=self._startupinfo,
                )
                if probe.returncode == 0:
                    self._pubkey_option = opt
                    return
            except Exception:
                continue
        
        self._pubkey_option = None
    
    def _setup_startupinfo(self):
        """Setup Windows-specific startupinfo to hide console"""
        if sys.platform == "win32":
            self._startupinfo = subprocess.STARTUPINFO()
            self._startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self._startupinfo.wShowWindow = 0  # SW_HIDE
    
    def _build_ssh_command(self, timeout: Optional[int] = None, 
                          batch_mode: bool = False) -> list:
        """Build SSH command with cached executable"""
        ssh_cmd = [
            self._ssh_exe,
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
    
    def execute(self, command: str, timeout: int = SSH_COMMAND_TIMEOUT) -> Tuple[bool, str, str]:
        """
        Execute SSH command with optimized settings.
        
        Args:
            command: Command to execute on remote host
            timeout: Command timeout in seconds
            
        Returns:
            Tuple of (success, stdout, stderr)
        """
        ssh_cmd = self._build_ssh_command(timeout=SSH_CONNECT_TIMEOUT, batch_mode=False)
        ssh_cmd.append(command)
        
        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 5,
                startupinfo=self._startupinfo,
            )
            
            if result.returncode == 0:
                return True, result.stdout, result.stderr
            return False, result.stdout, result.stderr
            
        except subprocess.TimeoutExpired:
            return False, "", "Command timeout"
        except Exception as e:
            return False, "", str(e)
    
    def execute_background(self, command: str) -> Optional[subprocess.Popen]:
        """
        Start SSH command in background.
        
        Args:
            command: Command to execute in background
            
        Returns:
            Popen process object or None on failure
        """
        ssh_cmd = self._build_ssh_command(timeout=SSH_CONNECT_TIMEOUT, batch_mode=False)
        ssh_cmd.append(command)
        
        try:
            process = subprocess.Popen(
                ssh_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                startupinfo=self._startupinfo,
            )
            return process
        except Exception as e:
            print(f"[SSH] Failed to start background command: {e}")
            return None
    
    def download_file(self, remote_path: str, local_path: str) -> bool:
        """
        Download file using SSH cat pipe.
        
        Args:
            remote_path: Path on remote host
            local_path: Local destination path
            
        Returns:
            True if download successful
        """
        ssh_cmd = self._build_ssh_command(timeout=SSH_CONNECT_TIMEOUT, batch_mode=False)
        ssh_cmd.append(f"cat {remote_path}")
        
        try:
            print(f"[SSH] Downloading {remote_path} to {local_path}")
            with open(local_path, 'wb') as f:
                result = subprocess.run(
                    ssh_cmd,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.DEVNULL,
                    timeout=120,
                    startupinfo=self._startupinfo
                )
            
            if result.returncode == 0 and os.path.exists(local_path):
                size = os.path.getsize(local_path)
                print(f"[SSH] Download success: {size} bytes")
                return size > 0
            else:
                print(f"[SSH] Download failed: {result.stderr.decode() if result.stderr else 'Unknown error'}")
                return False
        except Exception as e:
            print(f"[SSH] Download error: {e}")
            return False
    
    def test_connection(self) -> bool:
        """Quick connection test"""
        success, stdout, _ = self.execute("echo connected", timeout=10)
        return success and "connected" in stdout


# Global singleton instance
ssh_pool = SSHConnectionPool()
