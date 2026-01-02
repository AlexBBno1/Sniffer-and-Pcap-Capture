"""
WiFi Sniffer Web Control Panel
==============================
A Flask-based web application for controlling WiFi packet capture on OpenWrt.

Version: 2.0
"""

import os
import sys
from flask import Flask

# Global socketio instance (may be None if SocketIO is disabled)
socketio = None
_socketio_enabled = False


def create_app():
    """
    Application factory for creating the Flask app.
    
    Returns:
        Flask application instance
    """
    global socketio, _socketio_enabled
    
    # Detect if running as PyInstaller bundle
    if getattr(sys, 'frozen', False):
        # Running as bundled exe
        base_dir = sys._MEIPASS
        print(f"[INFO] Running as bundled exe, base_dir: {base_dir}")
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        print(f"[INFO] Running from source, base_dir: {base_dir}")
    
    # Setup template and static folders
    template_folder = os.path.join(base_dir, 'templates')
    static_folder = os.path.join(base_dir, 'wifi_sniffer', 'static')
    
    # Fallback paths for bundled exe
    if not os.path.exists(template_folder):
        template_folder = os.path.join(base_dir, 'templates')
    if not os.path.exists(static_folder):
        static_folder = os.path.join(base_dir, 'static')
    
    print(f"[INFO] Template folder: {template_folder}")
    print(f"[INFO] Static folder: {static_folder}")
    
    app = Flask(__name__,
                template_folder=template_folder,
                static_folder=static_folder)
    
    # Configure app
    app.config['SECRET_KEY'] = 'wifi-sniffer-secret-key'
    
    # Try to initialize SocketIO with multiple fallback modes
    socketio, _socketio_enabled = _init_socketio(app)
    
    # Register blueprints
    from .routes import api_bp, views_bp
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)
    
    # Set socketio on capture manager for broadcasting
    from .capture import capture_manager
    if _socketio_enabled and socketio:
        capture_manager.set_socketio(socketio)
        # Register WebSocket events
        _register_socketio_events()
    else:
        print("[INFO] SocketIO disabled, using polling mode")
    
    return app


def _init_socketio(app):
    """
    Try to initialize SocketIO with multiple async modes.
    Returns (socketio_instance, enabled_flag)
    """
    from flask_socketio import SocketIO
    
    # List of async modes to try, in order of preference
    # 'threading' is most compatible with PyInstaller
    async_modes = ['threading', 'eventlet', 'gevent', None]
    
    for mode in async_modes:
        try:
            print(f"[INFO] Trying SocketIO with async_mode='{mode}'...")
            sio = SocketIO()
            sio.init_app(app, async_mode=mode, cors_allowed_origins="*")
            print(f"[OK] SocketIO initialized with async_mode='{mode}'")
            return sio, True
        except Exception as e:
            print(f"[WARN] async_mode='{mode}' failed: {e}")
            continue
    
    # All modes failed, create a dummy socketio that won't crash
    print("[WARN] All SocketIO modes failed, creating fallback...")
    try:
        sio = SocketIO()
        # Don't init with app, just return a dummy
        return sio, False
    except:
        return None, False


def _register_socketio_events():
    """Register WebSocket event handlers"""
    global socketio
    if not socketio or not _socketio_enabled:
        return
    
    from .capture import capture_manager
    from .ssh import ssh_pool
    
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection"""
        print('[WebSocket] Client connected')
        # Send initial status
        socketio.emit('status_update', capture_manager.get_all_status())
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection"""
        print('[WebSocket] Client disconnected')
    
    @socketio.on('request_status')
    def handle_request_status():
        """Handle status request from client"""
        socketio.emit('status_update', capture_manager.get_all_status())
    
    @socketio.on('request_connection')
    def handle_request_connection():
        """Handle connection test request"""
        connected = ssh_pool.test_connection()
        if connected and not capture_manager.detection_status["detected"]:
            capture_manager.detect_interfaces()
        socketio.emit('connection_update', {
            'connected': connected,
            'interfaces': capture_manager.interfaces,
            'detection_status': capture_manager.detection_status
        })


def broadcast_status_update():
    """Broadcast capture status update to all connected clients"""
    global socketio, _socketio_enabled
    if socketio and _socketio_enabled:
        from .capture import capture_manager
        try:
            socketio.emit('status_update', capture_manager.get_all_status())
        except:
            pass


def broadcast_connection_update(connected: bool):
    """Broadcast connection status update to all connected clients"""
    global socketio, _socketio_enabled
    if socketio and _socketio_enabled:
        from .capture import capture_manager
        try:
            socketio.emit('connection_update', {
                'connected': connected,
                'interfaces': capture_manager.interfaces,
                'detection_status': capture_manager.detection_status
            })
        except:
            pass


def is_socketio_enabled():
    """Check if SocketIO is enabled"""
    return _socketio_enabled


__all__ = ['create_app', 'socketio', 'broadcast_status_update', 'broadcast_connection_update', 'is_socketio_enabled']
