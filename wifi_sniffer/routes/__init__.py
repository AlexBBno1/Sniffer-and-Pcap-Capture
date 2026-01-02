"""
Routes Module
=============
Flask routes for the WiFi Sniffer application.
"""

from flask import Blueprint

# Create blueprints
api_bp = Blueprint('api', __name__, url_prefix='/api')
views_bp = Blueprint('views', __name__)

# Import route handlers
from . import api
from . import views

__all__ = ['api_bp', 'views_bp']
