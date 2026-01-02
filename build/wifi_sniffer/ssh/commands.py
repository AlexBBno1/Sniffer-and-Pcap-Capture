"""
SSH Commands
============
High-level SSH command functions using the connection pool.
"""

from typing import Tuple, Optional
import subprocess
from .connection import ssh_pool


def run_ssh_command(command: str, timeout: int = 30) -> Tuple[bool, str, str]:
    """
    Run SSH command using the connection pool.
    
    Args:
        command: Command to execute on OpenWrt
        timeout: Command timeout in seconds
        
    Returns:
        Tuple of (success, stdout, stderr)
    """
    return ssh_pool.execute(command, timeout)


def run_ssh_command_background(command: str) -> Optional[subprocess.Popen]:
    """
    Start SSH command in background.
    
    Args:
        command: Command to execute in background
        
    Returns:
        Popen process object or None on failure
    """
    return ssh_pool.execute_background(command)


def download_file_scp(remote_path: str, local_path: str) -> bool:
    """
    Download file from OpenWrt using SSH.
    
    Args:
        remote_path: Path on OpenWrt
        local_path: Local destination path
        
    Returns:
        True if download successful
    """
    return ssh_pool.download_file(remote_path, local_path)


def test_ssh_connection() -> bool:
    """
    Test SSH connection to OpenWrt.
    
    Returns:
        True if connection successful
    """
    return ssh_pool.test_connection()
