"""
WiFi Sniffer Desktop Application v2
===================================
Professional desktop application with system tray support.
Uses the new modular architecture for better performance.

Author: AI Assistant
Version: 2.0
"""

import sys
import os
import threading
import webbrowser
import time
import ctypes
from pathlib import Path

# Add parent directory to path for importing the main module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try to import pystray for system tray support
try:
    import pystray
    from pystray import MenuItem as item
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("[WARNING] pystray or PIL not installed. System tray disabled.")
    print("         Install with: pip install pystray pillow")

# Import v2 modules
try:
    from wifi_sniffer import create_app, socketio, is_socketio_enabled
    from wifi_sniffer.config import SERVER_PORT, DOWNLOADS_FOLDER
    from wifi_sniffer.capture import capture_manager
    from wifi_sniffer.ssh import ssh_pool
except ImportError as e:
    print(f"[ERROR] Import error: {e}")
    # When running as bundled exe, modules are in the same directory
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from wifi_sniffer import create_app, socketio, is_socketio_enabled
    from wifi_sniffer.config import SERVER_PORT, DOWNLOADS_FOLDER
    from wifi_sniffer.capture import capture_manager
    from wifi_sniffer.ssh import ssh_pool


class WiFiSnifferAppV2:
    """Main application class with system tray support - v2"""
    
    def __init__(self):
        self.server_thread = None
        self.server_running = False
        self.icon = None
        self.app = None
        self.port = int(os.environ.get('FLASK_PORT', SERVER_PORT))
        self.host = "127.0.0.1"
        
    def create_icon_image(self, color="green"):
        """Create a simple icon image for the system tray"""
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Color scheme
        if color == "green":
            main_color = (34, 197, 94, 255)  # Green - connected
        elif color == "red":
            main_color = (239, 68, 68, 255)  # Red - disconnected
        elif color == "yellow":
            main_color = (245, 158, 11, 255)  # Yellow - capturing
        else:
            main_color = (148, 163, 184, 255)  # Gray - idle
        
        # Draw concentric arcs (WiFi signal style)
        center_x, center_y = size // 2, size - 10
        
        # Draw three arcs
        for i, radius in enumerate([12, 22, 32]):
            bbox = [
                center_x - radius, center_y - radius,
                center_x + radius, center_y + radius
            ]
            draw.arc(bbox, 200, 340, fill=main_color, width=4)
        
        # Draw center dot
        dot_radius = 5
        draw.ellipse([
            center_x - dot_radius, center_y - dot_radius,
            center_x + dot_radius, center_y + dot_radius
        ], fill=main_color)
        
        return image
    
    def get_status_text(self):
        """Get current capture status as text"""
        try:
            status = capture_manager.get_all_status()
            running = []
            for band in ["2G", "5G", "6G"]:
                if status[band]["running"]:
                    running.append(band)
            
            if running:
                return f"Capturing: {', '.join(running)}"
        except:
            pass
        return "Idle"
    
    def open_browser(self, icon=None, item=None):
        """Open the web interface in default browser"""
        url = f"http://{self.host}:{self.port}"
        webbrowser.open(url)
    
    def open_downloads(self, icon=None, item=None):
        """Open the downloads folder"""
        try:
            os.startfile(DOWNLOADS_FOLDER)
        except:
            pass
    
    def show_status(self, icon=None, item=None):
        """Show current status in a message box"""
        status = self.get_status_text()
        try:
            connected = "Connected" if ssh_pool.test_connection() else "Disconnected"
        except:
            connected = "Unknown"
        
        message = f"WiFi Sniffer Control Panel v2\n\n"
        message += f"Server: http://{self.host}:{self.port}\n"
        message += f"Router: {connected}\n"
        message += f"Status: {status}\n"
        message += f"\nDownload folder:\n{DOWNLOADS_FOLDER}"
        
        ctypes.windll.user32.MessageBoxW(0, message, "WiFi Sniffer Status", 0x40)
    
    def quit_app(self, icon=None, item=None):
        """Quit the application"""
        self.server_running = False
        if self.icon:
            self.icon.stop()
        os._exit(0)
    
    def update_icon(self):
        """Update icon based on current status"""
        if not self.icon or not TRAY_AVAILABLE:
            return
        
        try:
            status = capture_manager.get_all_status()
            any_running = any(status[band]["running"] for band in ["2G", "5G", "6G"])
            
            if any_running:
                self.icon.icon = self.create_icon_image("yellow")
            else:
                self.icon.icon = self.create_icon_image("green")
        except:
            pass
    
    def status_monitor(self):
        """Background thread to monitor and update status"""
        while self.server_running:
            try:
                self.update_icon()
            except:
                pass
            time.sleep(3)
    
    def run_server(self):
        """Run Flask server in background thread"""
        import logging
        
        # Suppress Flask's default logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        
        try:
            # Check if SocketIO is enabled and use appropriate run method
            if is_socketio_enabled() and socketio is not None:
                print("[INFO] Starting server with SocketIO...")
                socketio.run(
                    self.app,
                    host=self.host,
                    port=self.port,
                    debug=False,
                    use_reloader=False,
                    allow_unsafe_werkzeug=True
                )
            else:
                print("[INFO] Starting server without SocketIO (polling mode)...")
                self.app.run(
                    host=self.host,
                    port=self.port,
                    debug=False,
                    use_reloader=False,
                    threaded=True
                )
        except Exception as e:
            print(f"[ERROR] Server error: {e}")
            import traceback
            traceback.print_exc()
            self.server_running = False
    
    def create_menu(self):
        """Create system tray menu"""
        return pystray.Menu(
            item('🌐 Open Web Panel', self.open_browser, default=True),
            item('📁 Open Downloads', self.open_downloads),
            pystray.Menu.SEPARATOR,
            item('ℹ️ Status', self.show_status),
            pystray.Menu.SEPARATOR,
            item('❌ Exit', self.quit_app)
        )
    
    def run(self):
        """Main entry point"""
        print("=" * 60)
        print("  WiFi Sniffer Desktop Application v2.0")
        print("=" * 60)
        print(f"  Server: http://{self.host}:{self.port}")
        print(f"  Downloads: {DOWNLOADS_FOLDER}")
        print("-" * 60)
        
        # Create Flask app
        print("[INFO] Creating Flask application...")
        self.app = create_app()
        print("[OK] Flask application created")
        
        self.server_running = True
        
        # Start Flask server in background thread
        self.server_thread = threading.Thread(target=self.run_server, daemon=True)
        self.server_thread.start()
        
        # Wait a moment for server to start
        time.sleep(2)
        
        # Open browser automatically
        self.open_browser()
        
        if TRAY_AVAILABLE:
            print("[INFO] System tray enabled. Right-click the icon for options.")
            print("[INFO] The application is now running in the system tray.")
            
            # Start status monitor
            monitor_thread = threading.Thread(target=self.status_monitor, daemon=True)
            monitor_thread.start()
            
            # Create and run system tray icon
            self.icon = pystray.Icon(
                "WiFi Sniffer v2",
                self.create_icon_image("green"),
                "WiFi Sniffer Control Panel v2",
                self.create_menu()
            )
            
            self.icon.run()
        else:
            print("[INFO] Running without system tray. Press Ctrl+C to stop.")
            print("[INFO] Keep this window open while using the application.")
            
            try:
                while self.server_running:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n[INFO] Shutting down...")
                self.server_running = False


def main():
    """Main function"""
    if sys.platform == 'win32':
        try:
            ctypes.windll.kernel32.SetConsoleTitleW("WiFi Sniffer Control Panel v2")
        except:
            pass
    
    app_instance = WiFiSnifferAppV2()
    app_instance.run()


if __name__ == '__main__':
    main()
