@echo off
title WiFi Sniffer - Clean Build
color 0E

echo.
echo ============================================================
echo    WiFi Sniffer Control Panel - Clean Build Files
echo ============================================================
echo.
echo This will remove all build artifacts:
echo   - dist\ folder
echo   - build\ subfolder (PyInstaller temp)
echo   - output\ folder
echo   - __pycache__\ folders
echo   - *.pyc files
echo.
echo Press Ctrl+C to cancel, or...
pause

cd /d "%~dp0"

echo.
echo [INFO] Cleaning build artifacts...

if exist "dist" (
    rmdir /S /Q "dist"
    echo [OK] Removed dist\
)

if exist "build" (
    rmdir /S /Q "build"
    echo [OK] Removed build\ (PyInstaller temp)
)

if exist "output" (
    rmdir /S /Q "output"
    echo [OK] Removed output\
)

if exist "__pycache__" (
    rmdir /S /Q "__pycache__"
    echo [OK] Removed __pycache__\
)

if exist "wifi_sniffer_web_control.py" (
    del /Q "wifi_sniffer_web_control.py"
    echo [OK] Removed copied wifi_sniffer_web_control.py
)

del /Q *.pyc 2>nul

echo.
echo ============================================================
echo    Clean completed!
echo ============================================================
echo.
pause


