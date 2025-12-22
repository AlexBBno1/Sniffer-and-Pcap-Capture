@echo off
title WiFi Sniffer - Development Mode
color 0B

:: ============================================================
:: PORT 設定 - 可修改此處變更 Port（預設 5000）
:: ============================================================
set FLASK_PORT=5000

echo.
echo ============================================================
echo    WiFi Sniffer Control Panel - Development Mode
echo ============================================================
echo    Port: %FLASK_PORT%
echo.

REM Change to script directory
cd /d "%~dp0"

REM Check dependencies
python -c "import pystray" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Installing dependencies for system tray support...
    pip install -r requirements_build.txt
    echo.
)

REM Copy main module if not exists
if not exist "wifi_sniffer_web_control.py" (
    echo [INFO] Copying main module...
    copy /Y "..\wifi_sniffer_web_control.py" "." >nul
)

echo [INFO] Starting application in development mode...
echo [INFO] System tray icon will appear in taskbar
echo [INFO] Press Ctrl+C to stop
echo.

python wifi_sniffer_app.py

pause


