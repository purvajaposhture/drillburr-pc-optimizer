@echo off
title DRILLBUR — Build Standalone .EXE
color 0A
echo.
echo  ============================================================
echo   DRILLBUR — Build Standalone .EXE
echo   Creates a single installable DRILLBUR.exe
echo  ============================================================
echo.

cd /d "%~dp0"

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found. Install from python.org first.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  [OK] %%v

:: Install/upgrade PyInstaller
echo.
echo  [1/4] Installing PyInstaller...
python -m pip install pyinstaller psutil --quiet --upgrade
echo  [OK] PyInstaller ready

:: Make assets dir
echo.
echo  [2/4] Creating assets...
if not exist "assets" mkdir assets

:: Generate icon
echo.
python -c "
import struct

def make_simple_ico(path):
    size = 32
    img = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            i = (y * size + x) * 4
            if x < 2 or x >= size-2 or y < 2 or y >= size-2:
                img[i:i+4] = [184, 148, 138, 255]
            elif 10 <= x <= 22 and 6 <= y <= 18:
                img[i:i+4] = [58, 53, 48, 255]
            elif 8 <= x <= 24 and 16 <= y <= 26:
                img[i:i+4] = [90, 106, 122, 255]
            else:
                img[i:i+4] = [240, 235, 227, 255]
    bmp = struct.pack('<IIIHHIIIIII', 40, 32, 64, 1, 32, 0, 0, 0, 0, 0, 0)
    for y in range(31, -1, -1):
        for x in range(32):
            idx = (y * 32 + x) * 4
            bmp += bytes([img[idx+2], img[idx+1], img[idx], img[idx+3]])
    bmp += b'\x00' * 128
    ico = bytearray()
    ico += struct.pack('<HHH', 0, 1, 1)
    ico += struct.pack('<BBBBHHII', 32, 32, 0, 0, 1, 32, len(bmp), 22)
    with open(path, 'wb') as f: f.write(bytes(ico) + bmp)

make_simple_ico('assets/drillbur.ico')
print('[OK] Icon created')
"

:: Clean previous builds
echo.
echo  [3/4] Cleaning previous build...
if exist build  rmdir /s /q build
if exist dist   rmdir /s /q dist
echo  [OK] Clean

:: Build
echo.
echo  [4/4] Building DRILLBUR.exe — this may take 1-3 minutes...
echo.
python -m PyInstaller drillbur.spec --noconfirm --clean

:: Check result
echo.
if exist "dist\DRILLBUR\DRILLBUR.exe" (
    echo  ============================================================
    echo   SUCCESS! Your app is ready:
    echo.
    echo   dist\DRILLBUR\DRILLBUR.exe
    echo.
    echo   To distribute: zip the entire dist\DRILLBUR\ folder
    echo   The folder contains everything needed to run.
    echo  ============================================================
    echo.
    set /p OPEN="Open dist\DRILLBUR folder now? (Y/N): "
    if /i "%OPEN%"=="Y" explorer dist\DRILLBUR
) else (
    echo  [ERROR] Build failed. Check the output above for errors.
    echo.
    echo  Common fixes:
    echo   - Make sure all .py and .html files are in this folder
    echo   - Try: python -m pip install pyinstaller --upgrade
    echo   - Check antivirus isn't blocking PyInstaller
)
echo.
pause
