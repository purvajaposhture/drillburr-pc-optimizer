@echo off
title DRILLBUR Installer
echo.
echo  ================================================================
echo   DRILLBUR -- Windows PC Optimizer -- Installer
echo  ================================================================
echo.
echo  This will install DRILLBUR on your PC.
echo  A desktop shortcut and Start Menu entry will be created.
echo.
echo  For FULL access (clean system files, SFC scan etc):
echo  Right-click this file and choose "Run as administrator"
echo.
pause

:: Try PowerShell execution (most Windows 10/11 machines allow this)
powershell -ExecutionPolicy Bypass -File "%~dp0install.ps1"

if %errorlevel% neq 0 (
    echo.
    echo  [INFO] Trying alternative installation method...
    echo.
    :: Fallback: just check Python and pip install psutil
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo  Python not found. Please install from https://python.org
        echo  Then run this installer again.
        pause
        start https://python.org/downloads/
        exit /b 1
    )
    python -m pip install psutil --quiet
    echo.
    echo  Basic setup complete!
    echo  Run "python drillbur_app.py" to start DRILLBUR.
    echo.
    pause
)
