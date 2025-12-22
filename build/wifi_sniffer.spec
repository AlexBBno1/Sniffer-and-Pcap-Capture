# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec File for WiFi Sniffer Control Panel
=====================================================
This file configures how PyInstaller bundles the application.

To build:
    pyinstaller wifi_sniffer.spec

Or use build.bat for automated building.
"""

import os
import sys

# Get the directory containing this spec file
spec_dir = os.path.dirname(os.path.abspath(SPEC))
parent_dir = os.path.dirname(spec_dir)

# Analysis - collect all dependencies
a = Analysis(
    ['wifi_sniffer_app.py'],
    pathex=[spec_dir, parent_dir],
    binaries=[],
    datas=[
        # Include the main web control module
        (os.path.join(parent_dir, 'wifi_sniffer_web_control.py'), '.'),
    ],
    hiddenimports=[
        'flask',
        'jinja2',
        'werkzeug',
        'paramiko',
        'pystray',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
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
    name='WiFi_Sniffer_Control_Panel',
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
    version=os.path.join(spec_dir, 'assets', 'version_info.txt') if os.path.exists(os.path.join(spec_dir, 'assets', 'version_info.txt')) else None,
)

