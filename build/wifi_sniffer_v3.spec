# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec File for WiFi Sniffer Control Panel v3
========================================================
This file configures how PyInstaller bundles the v3 application.

To build:
    pyinstaller wifi_sniffer_v3.spec

Or use build_v3.bat for automated building.
"""

import os
import sys

# Get the directory containing this spec file
spec_dir = os.path.dirname(os.path.abspath(SPEC))
parent_dir = os.path.dirname(spec_dir)

# Analysis - collect all dependencies
a = Analysis(
    ['wifi_sniffer_app_v3.py'],
    pathex=[spec_dir, parent_dir],
    binaries=[],
    datas=[
        # Include the wifi_sniffer package from build directory (already copied)
        ('wifi_sniffer', 'wifi_sniffer'),
        # Include templates from parent directory
        (os.path.join(parent_dir, 'templates'), 'templates'),
    ],
    hiddenimports=[
        # Flask and extensions
        'flask',
        'flask_socketio',
        'jinja2',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.debug',
        
        # SSH
        'paramiko',
        
        # System tray
        'pystray',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        
        # SocketIO backends - core
        'engineio',
        'engineio.server',
        'engineio.socket',
        'engineio.packet',
        'engineio.payload',
        'engineio.async_drivers',
        'socketio',
        'socketio.server',
        'socketio.namespace',
        'socketio.packet',
        
        # Eventlet - full package for async mode
        'eventlet',
        'eventlet.hubs',
        'eventlet.hubs.hub',
        'eventlet.hubs.selects',
        'eventlet.hubs.poll',
        'eventlet.hubs.epolls',
        'eventlet.green',
        'eventlet.green.socket',
        'eventlet.green.ssl',
        'eventlet.green.time',
        'eventlet.green.threading',
        'eventlet.green.select',
        'eventlet.green.subprocess',
        'eventlet.green.os',
        'eventlet.greenthread',
        'eventlet.event',
        'eventlet.queue',
        'eventlet.semaphore',
        'eventlet.timeout',
        'eventlet.wsgi',
        'eventlet.websocket',
        
        # DNS for eventlet
        'dns',
        'dns.resolver',
        
        # wifi_sniffer modules
        'wifi_sniffer',
        'wifi_sniffer.config',
        'wifi_sniffer.cache',
        'wifi_sniffer.ssh',
        'wifi_sniffer.ssh.connection',
        'wifi_sniffer.ssh.commands',
        'wifi_sniffer.capture',
        'wifi_sniffer.capture.manager',
        'wifi_sniffer.routes',
        'wifi_sniffer.routes.api',
        'wifi_sniffer.routes.views',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# Create PYZ archive
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# Create EXE
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WiFi_Sniffer_Control_Panel_v3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window (GUI mode)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(spec_dir, 'assets', 'icon.ico') if os.path.exists(os.path.join(spec_dir, 'assets', 'icon.ico')) else None,
    version=os.path.join(spec_dir, 'assets', 'version_info_v3.txt') if os.path.exists(os.path.join(spec_dir, 'assets', 'version_info_v3.txt')) else None,
)
