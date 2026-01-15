"""
WiFi Sniffer Web Control Panel - v2
===================================
High-performance web-based control panel for WiFi packet capture.

Features:
- Modular architecture for better maintainability
- SSH connection pooling for improved performance
- Async page loading (non-blocking)
- WebSocket support for real-time updates
- Optimized for Windows 10/11

Version: 2.0
"""

import os
import sys

# Add wifi_sniffer package to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wifi_sniffer import create_app
import wifi_sniffer  # Import module to access socketio after create_app
from wifi_sniffer.config import SERVER_HOST, SERVER_PORT, DOWNLOADS_FOLDER, OPENWRT_HOST
from wifi_sniffer.capture import capture_manager


def main():
    """Main entry point"""
    print("=" * 60)
    print("  WiFi Sniffer Web Control Panel v2.0")
    print("=" * 60)
    print(f"  OpenWrt Host: {OPENWRT_HOST}")
    print(f"  Download Folder: {DOWNLOADS_FOLDER}")
    print(f"  Default Interface Mapping:")
    for band, iface in capture_manager.interfaces.items():
        print(f"    - {band}: {iface}")
    print("-" * 60)
    print("  Performance Improvements in v2:")
    print("  - SSH connection pooling")
    print("  - Async page loading")
    print("  - WebSocket real-time updates")
    print("  - Cached interface detection")
    print("=" * 60)
    print(f"  Starting web server on http://127.0.0.1:{SERVER_PORT}")
    print("=" * 60)
    
    # Create Flask app (this initializes socketio)
    app = create_app()
    
    # Access socketio from module after create_app has initialized it
    socketio = wifi_sniffer.socketio
    
    # Run with SocketIO support
    socketio.run(
        app,
        host=SERVER_HOST,
        port=SERVER_PORT,
        debug=False,  # Disable debug for production
        use_reloader=False,
        allow_unsafe_werkzeug=True
    )


if __name__ == '__main__':
    main()
