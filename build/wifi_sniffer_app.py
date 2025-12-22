"""
WiFi Sniffer Desktop Application
=================================
Professional desktop application with system tray support.
Wraps the web control panel with native Windows integration.

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

# Try to import pystray for system tray support
try:
    import pystray
    from pystray import MenuItem as item
    from PIL import Image, ImageDraw, ImageFont
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("[WARNING] pystray or PIL not installed. System tray disabled.")
    print("         Install with: pip install pystray pillow")

# Import Flask app
try:
    from wifi_sniffer_web_control import app, test_connection, capture_status, DOWNLOADS_FOLDER
except ImportError:
    # When running as bundled exe, the module might be in the same directory
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from wifi_sniffer_web_control import app, test_connection, capture_status, DOWNLOADS_FOLDER


class WiFiSnifferApp:
    """Main application class with system tray support"""
    
    def __init__(self):
        self.server_thread = None
        self.server_running = False
        self.icon = None
        # 從環境變數讀取 PORT，預設 5000
        self.port = int(os.environ.get('FLASK_PORT', 5000))
        self.host = "127.0.0.1"
        
    def create_icon_image(self, color="green"):
        """Create a simple icon image for the system tray"""
        # Create a simple WiFi-like icon
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
            # Adjust alpha for outer rings
            alpha = 255 - (i * 50)
            arc_color = (*main_color[:3], alpha)
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
        running = []
        for band in ["2G", "5G", "6G"]:
            if capture_status[band]["running"]:
                running.append(band)
        
        if running:
            return f"Capturing: {', '.join(running)}"
        return "Idle"
    
    def open_browser(self, icon=None, item=None):
        """Open the web interface in default browser"""
        url = f"http://{self.host}:{self.port}"
        webbrowser.open(url)
    
    def open_downloads(self, icon=None, item=None):
        """Open the downloads folder"""
        os.startfile(DOWNLOADS_FOLDER)
    
    def show_status(self, icon=None, item=None):
        """Show current status in a message box"""
        status = self.get_status_text()
        connected = "Connected" if test_connection() else "Disconnected"
        
        message = f"WiFi Sniffer Control Panel\n\n"
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
        # Force exit
        os._exit(0)
    
    def update_icon(self):
        """Update icon based on current status"""
        if not self.icon:
            return
            
        # Check if any capture is running
        any_running = any(capture_status[band]["running"] for band in ["2G", "5G", "6G"])
        
        if any_running:
            self.icon.icon = self.create_icon_image("yellow")
        else:
            self.icon.icon = self.create_icon_image("green")
    
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
        
        # Run Flask app
        try:
            app.run(host=self.host, port=self.port, debug=False, threaded=True, use_reloader=False)
        except Exception as e:
            print(f"[ERROR] Server error: {e}")
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
        print("  WiFi Sniffer Desktop Application")
        print("=" * 60)
        print(f"  Server: http://{self.host}:{self.port}")
        print(f"  Downloads: {DOWNLOADS_FOLDER}")
        print("=" * 60)
        
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
                "WiFi Sniffer",
                self.create_icon_image("green"),
                "WiFi Sniffer Control Panel",
                self.create_menu()
            )
            
            # This blocks until icon.stop() is called
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
    # Set console title on Windows
    if sys.platform == 'win32':
        ctypes.windll.kernel32.SetConsoleTitleW("WiFi Sniffer Control Panel")
    
    # Create and run application
    app_instance = WiFiSnifferApp()
    app_instance.run()


if __name__ == '__main__':
    main()


