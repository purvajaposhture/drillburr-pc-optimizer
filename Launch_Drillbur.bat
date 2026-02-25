@echo off
setlocal
title DRILLBUR — PC Optimizer
color 0F

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   🐹  DRILLBUR  —  Windows PC Optimizer     ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: ── Check Python ──────────────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found!
    echo.
    echo  Please install Python 3.8+ from:
    echo  https://www.python.org/downloads/
    echo.
    echo  During install, check "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  [OK] %PY_VER% found
echo.

:: ── Check psutil ──────────────────────────────────────────────────────────────
python -c "import psutil" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [INFO] Installing psutil (required for system stats)...
    pip install psutil --quiet
    if %errorlevel% neq 0 (
        echo  [WARN] Could not auto-install psutil.
        echo         Run manually: pip install psutil
    ) else (
        echo  [OK] psutil installed.
    )
    echo.
) else (
    echo  [OK] psutil ready
    echo.
)

:: ── Check admin rights ────────────────────────────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo  [WARN] Not running as Administrator.
    echo         Some features need elevated access.
    echo         Right-click this file → "Run as administrator"
    echo         for full functionality.
    echo.
    choice /C YN /M "Continue anyway?"
    if %errorlevel% equ 2 exit /b 0
    echo.
)

:: ── Check frontend file ───────────────────────────────────────────────────────
if not exist "%~dp0Drillbur.html" (
    echo  [ERROR] Drillbur.html not found!
    echo          Make sure Drillbur.html is in the same folder as this launcher.
    echo.
    pause
    exit /b 1
)

echo  Starting DRILLBUR backend server...
echo  Your browser will open automatically.
echo.
echo  Press Ctrl+C in this window to stop the server.
echo.

:: ── Launch backend ────────────────────────────────────────────────────────────
python "%~dp0drillbur_backend.py"

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Backend crashed. Check the error above.
    echo.
    pause
)
