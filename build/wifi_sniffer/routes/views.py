"""
View Routes
===========
Page rendering routes for the WiFi Sniffer application.
"""

from flask import render_template

from . import views_bp
from ..capture import capture_manager
from ..ssh import ssh_pool
from ..config import CHANNELS, BANDWIDTHS, DOWNLOADS_FOLDER


@views_bp.route('/')
def index():
    """
    Main page - renders asynchronously.
    Connection test is done via AJAX to avoid blocking page load.
    """
    # Get current capture status
    status = capture_manager.get_all_status()
    
    # Prepare detection status for template
    detection_status = {
        "detected": capture_manager.detection_status["detected"],
        "method": capture_manager.detection_status["detection_method"],
        "last_detection": capture_manager.detection_status["last_detection"].strftime("%Y-%m-%d %H:%M:%S") if capture_manager.detection_status["last_detection"] else None
    }
    
    # Return page immediately - connection status fetched via AJAX
    return render_template(
        'index.html',
        connected=None,  # Will be fetched via AJAX
        status=status,
        channels=CHANNELS,
        bandwidths=BANDWIDTHS,
        channel_config=capture_manager.channel_config,
        download_path=DOWNLOADS_FOLDER,
        interfaces=capture_manager.interfaces,
        uci_wifi_map=capture_manager.uci_wifi_map,
        detection_status=detection_status
    )
