@echo off
setlocal enabledelayedexpansion
title WiFi Sniffer - Build System
color 0A

echo.
echo ============================================================
echo    WiFi Sniffer Control Panel - Build System
echo ============================================================
echo.

REM Change to script directory
cd /d "%~dp0"

REM Check Python
echo [1/6] Checking Python installation...
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo         Please install Python 3.8+ from https://www.python.org/downloads/
    goto :error
)
python --version
echo [OK] Python found
echo.

REM Install build dependencies
echo [2/6] Installing build dependencies...
pip install -r requirements_build.txt --quiet
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install dependencies!
    goto :error
)
echo [OK] Dependencies installed
echo.

REM Generate icon
echo [3/6] Generating application icon...
python create_icon.py
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Icon generation failed. Using default icon.
)
echo.

REM Copy main module to build directory
echo [4/6] Preparing source files...
copy /Y "..\wifi_sniffer_web_control.py" "." >nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Cannot find wifi_sniffer_web_control.py in parent directory!
    goto :error
)
echo [OK] Source files prepared
echo.

REM Build with PyInstaller
echo [5/6] Building executable with PyInstaller...
echo       This may take a few minutes...
echo.
python -m PyInstaller --clean --noconfirm wifi_sniffer.spec
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] PyInstaller build failed!
    goto :error
)
echo.
echo [OK] Build completed successfully!
echo.

REM Create output directory for installer
if not exist "output" mkdir output

REM Check if Inno Setup is installed
echo [6/6] Checking for Inno Setup...
set ISCC_PATH=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if defined ISCC_PATH (
    echo [INFO] Inno Setup found. Building installer...
    "%ISCC_PATH%" "installer\setup.iss"
    if %ERRORLEVEL% EQU 0 (
        echo [OK] Installer created successfully!
    ) else (
        echo [WARNING] Installer build failed. You can build it manually later.
    )
) else (
    echo [INFO] Inno Setup not found. Skipping installer creation.
    echo        To create an installer, install Inno Setup 6 from:
    echo        https://jrsoftware.org/isdl.php
    echo.
    echo        Then run: "installer\setup.iss" with Inno Setup Compiler
)

echo.
echo ============================================================
echo    BUILD COMPLETED!
echo ============================================================
echo.
echo    Executable: dist\WiFi_Sniffer_Control_Panel.exe
if exist "output\WiFi_Sniffer_Setup*.exe" (
    echo    Installer:  output\WiFi_Sniffer_Setup_v2.0.exe
)
echo.
echo    You can now:
echo    1. Run the EXE directly from dist\ folder
echo    2. Distribute the installer to other computers
echo.
echo ============================================================
goto :end

:error
echo.
echo ============================================================
echo    BUILD FAILED!
echo ============================================================
echo    Please check the error messages above.
echo ============================================================
pause
exit /b 1

:end
pause
exit /b 0

