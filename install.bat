@echo off
title WiFi Sniffer - Installation Script
color 0B
setlocal EnableDelayedExpansion

echo.
echo ============================================================
echo     WiFi Sniffer Web Control Panel - Installation
echo     Supports v1 (Classic) and v2 (Performance)
echo ============================================================
echo.

REM ========== Check Administrator ==========
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] This script may require administrator privileges.
    echo [WARN] If installation fails, please right-click and "Run as administrator"
    echo.
)

REM ========== Check Python ==========
echo [1/6] Checking Python installation...
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is NOT installed!
    echo.
    echo Please install Python manually:
    echo   1. Download from: https://www.python.org/downloads/
    echo   2. During installation, CHECK "Add Python to PATH"
    echo   3. Run this script again after installation
    echo.
    echo Opening Python download page...
    start "" "https://www.python.org/downloads/"
    pause
    exit /b 1
) else (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYVER=%%i
    echo [OK] !PYVER! is installed
)

REM ========== Check pip ==========
echo.
echo [2/6] Checking pip installation...
python -m pip --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Installing pip...
    python -m ensurepip --upgrade
) else (
    echo [OK] pip is installed
)

REM ========== Upgrade pip ==========
echo.
echo [3/6] Upgrading pip to latest version...
python -m pip install --upgrade pip --quiet

REM ========== Install Core Dependencies ==========
echo.
echo [4/6] Installing core Python dependencies...
echo      - Flask (Web framework)
echo      - Paramiko (SSH library)
echo.

python -m pip install flask paramiko --quiet
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install core dependencies!
    echo Please try running: pip install flask paramiko
    pause
    exit /b 1
)
echo [OK] Core dependencies installed

REM ========== Install v2 Dependencies ==========
echo.
echo [5/6] Installing v2 dependencies (WebSocket support)...
echo      - Flask-SocketIO (Real-time updates)
echo      - Eventlet (Async support)
echo.

python -m pip install flask-socketio eventlet --quiet
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] Failed to install v2 dependencies.
    echo [WARN] v1 will work, but v2 requires these packages.
    echo [INFO] Try manually: pip install flask-socketio eventlet
) else (
    echo [OK] v2 dependencies installed
)

REM ========== Check Wireshark ==========
echo.
echo [6/6] Checking Wireshark installation...
where wireshark >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] Wireshark is NOT found in PATH
    echo [INFO] Wireshark is recommended for viewing .pcap files
    echo.
    set /p INSTALL_WS="Do you want to open Wireshark download page? (Y/N): "
    if /i "!INSTALL_WS!"=="Y" (
        echo Opening Wireshark download page...
        start "" "https://www.wireshark.org/download.html"
    )
) else (
    echo [OK] Wireshark is installed
)

REM ========== SSH Key Setup Info ==========
echo.
echo ============================================================
echo     SSH Configuration for OpenWrt (192.168.1.1)
echo ============================================================
echo.
echo The system uses Windows native SSH which works automatically
echo with OpenWrt's default configuration (no password).
echo.
echo If your OpenWrt requires a password:
echo   Option 1: Set up SSH key authentication (recommended)
echo   Option 2: Edit wifi_sniffer/config.py and set OPENWRT_PASSWORD
echo.

REM ========== Test Connection ==========
echo.
set /p TEST_SSH="Test SSH connection to 192.168.1.1? (Y/N): "
if /i "%TEST_SSH%"=="Y" (
    echo.
    echo [INFO] Testing SSH connection...
    ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o HostKeyAlgorithms=+ssh-rsa root@192.168.1.1 "echo 'SSH connection successful!'" 2>nul
    if %ERRORLEVEL% NEQ 0 (
        echo [WARN] SSH connection failed. Please check:
        echo        - OpenWrt is powered on
        echo        - IP address is 192.168.1.1
        echo        - SSH service is enabled on OpenWrt
        echo        - Correct authentication configured
    ) else (
        echo [OK] SSH connection successful!
    )
)

REM ========== Complete ==========
echo.
echo ============================================================
echo                 Installation Complete!
echo ============================================================
echo.
echo Available versions:
echo.
echo   v1 (Classic):
echo      - Run: start_server.bat
echo      - Or:  python wifi_sniffer_web_control.py
echo.
echo   v2 (Performance - Recommended):
echo      - Run: start_server_v2.bat
echo      - Or:  python wifi_sniffer_web_control_v2.py
echo      - Features: SSH pooling, WebSocket, Caching
echo.
echo   Standalone EXE (No Python needed):
echo      - v1: build\dist\WiFi_Sniffer_Control_Panel.exe
echo      - v2: build\dist\WiFi_Sniffer_Control_Panel_v2.exe
echo.
echo Files saved to: %USERPROFILE%\Downloads
echo.
pause
