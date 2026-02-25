# DRILLBUR Installer Script
# Run: Right-click → "Run with PowerShell" (as Administrator recommended)
# ─────────────────────────────────────────────────────────────────────────────

param(
    [switch]$BuildExe,      # Also build .exe with PyInstaller
    [switch]$CreateShortcut # Create desktop shortcut
)

$ErrorActionPreference = "Continue"

$DRILLBUR_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$DRILLBUR_VER = "1.0.0"

function Write-Header {
    Clear-Host
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════╗" -ForegroundColor DarkRed
    Write-Host "  ║                                              ║" -ForegroundColor DarkRed
    Write-Host "  ║   🐹  DRILLBUR  —  PC Optimizer  v$DRILLBUR_VER     ║" -ForegroundColor DarkRed
    Write-Host "  ║         Windows Installer                    ║" -ForegroundColor DarkRed
    Write-Host "  ║                                              ║" -ForegroundColor DarkRed
    Write-Host "  ╚══════════════════════════════════════════════╝" -ForegroundColor DarkRed
    Write-Host ""
}

function Write-Step($msg) {
    Write-Host "  ▸ $msg" -ForegroundColor Cyan
}

function Write-OK($msg) {
    Write-Host "  ✓ $msg" -ForegroundColor Green
}

function Write-Warn($msg) {
    Write-Host "  ⚠ $msg" -ForegroundColor Yellow
}

function Write-Fail($msg) {
    Write-Host "  ✗ $msg" -ForegroundColor Red
}

Write-Header

# ── Step 1: Check Windows version ────────────────────────────────────────────
Write-Step "Checking Windows version..."
$winVer = [System.Environment]::OSVersion.Version
if ($winVer.Major -lt 10) {
    Write-Fail "Windows 10 or later is required (found: $winVer)"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-OK "Windows $($winVer.Major).$($winVer.Minor) detected"

# ── Step 2: Check Python ──────────────────────────────────────────────────────
Write-Step "Checking Python installation..."
$python = $null
$pythonCmds = @("python", "python3", "py")

foreach ($cmd in $pythonCmds) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.([89]|1[0-9])") {
            $python = $cmd
            Write-OK "$ver found ($cmd)"
            break
        }
    } catch {}
}

if (-not $python) {
    Write-Warn "Python 3.8+ not found."
    Write-Host ""
    Write-Host "  Installing Python via winget..." -ForegroundColor Yellow
    try {
        winget install --id Python.Python.3.11 --silent --accept-source-agreements --accept-package-agreements
        $python = "python"
        Write-OK "Python installed via winget"
    } catch {
        Write-Fail "Could not auto-install Python."
        Write-Host ""
        Write-Host "  Please install manually from: https://python.org/downloads/" -ForegroundColor White
        Write-Host "  Then re-run this installer." -ForegroundColor White
        Write-Host ""
        Start-Process "https://python.org/downloads/"
        Read-Host "Press Enter after installing Python"
        exit 1
    }
}

# ── Step 3: Install psutil ────────────────────────────────────────────────────
Write-Step "Checking psutil..."
$hasPsutil = & $python -c "import psutil; print('ok')" 2>&1
if ($hasPsutil -eq "ok") {
    Write-OK "psutil already installed"
} else {
    Write-Step "Installing psutil..."
    & $python -m pip install psutil --quiet --upgrade
    $check = & $python -c "import psutil; print('ok')" 2>&1
    if ($check -eq "ok") {
        Write-OK "psutil installed successfully"
    } else {
        Write-Warn "Could not install psutil — live stats may be limited"
    }
}

# ── Step 4: Verify required files ────────────────────────────────────────────
Write-Step "Verifying required files..."
$requiredFiles = @(
    "drillbur_app.py",
    "drillbur_backend.py",
    "Drillbur.html"
)
$allFound = $true
foreach ($f in $requiredFiles) {
    $fp = Join-Path $DRILLBUR_DIR $f
    if (Test-Path $fp) {
        Write-OK "$f"
    } else {
        Write-Fail "$f NOT FOUND"
        $allFound = $false
    }
}

if (-not $allFound) {
    Write-Host ""
    Write-Fail "Missing files. Make sure all DRILLBUR files are in the same folder."
    Read-Host "Press Enter to exit"
    exit 1
}

# ── Step 5: Create assets folder & icon ──────────────────────────────────────
$assetsDir = Join-Path $DRILLBUR_DIR "assets"
if (-not (Test-Path $assetsDir)) {
    New-Item -ItemType Directory -Path $assetsDir -Force | Out-Null
}

# Generate a simple .ico using Python if it doesn't exist
$icoPath = Join-Path $assetsDir "drillbur.ico"
if (-not (Test-Path $icoPath)) {
    Write-Step "Creating app icon..."
    $iconScript = @"
import struct, zlib, io

def make_ico():
    # 32x32 RGBA pixel data - simple mole icon
    size = 32
    img = bytearray(size * size * 4)
    
    # Simple colored square icon (cream bg, rose border, dark center)
    for y in range(size):
        for x in range(size):
            i = (y * size + x) * 4
            # Border
            if x < 2 or x >= size-2 or y < 2 or y >= size-2:
                img[i:i+4] = [184, 148, 138, 255]  # rose border
            # Inner area
            elif x < 4 or x >= size-4 or y < 4 or y >= size-4:
                img[i:i+4] = [240, 235, 227, 255]  # cream
            # Dark center (mole body)
            elif 8 <= x <= 24 and 8 <= y <= 24:
                img[i:i+4] = [58, 53, 48, 255]     # dark
            else:
                img[i:i+4] = [240, 235, 227, 255]  # cream

    # Create BMP data
    def bmp_header(w, h, bpp):
        row_bytes = ((w * bpp + 31) // 32) * 4
        img_size = row_bytes * h
        return struct.pack('<BBIHHIIIHHIIIIII',
            66, 77, 54 + img_size, 0, 0, 54,
            40, w, h, 1, bpp, 0, img_size, 0, 0, 0, 0)
    
    # Write ICO
    ico_data = bytearray()
    # ICO header
    ico_data += struct.pack('<HHH', 0, 1, 1)
    # Directory entry
    ico_data += struct.pack('<BBBBHHII', 32, 32, 0, 0, 1, 32, 0, 22)
    
    # BMP for ICO (BGRA, flipped vertically)
    bmp = struct.pack('<IIIHHIIIIII', 40, 32, 64, 1, 32, 0, 0, 0, 0, 0, 0)
    for y in range(31, -1, -1):
        for x in range(32):
            i = (y * 32 + x) * 4
            bmp += bytes([img[i+2], img[i+1], img[i], img[i+3]])
    # AND mask (transparent)
    bmp += b'\x00' * (32 * 4)
    
    # Fix offset
    bmp_size = len(bmp)
    ico_data[18:22] = struct.pack('<I', bmp_size)
    
    with open(r'$icoPath', 'wb') as f:
        f.write(bytes(ico_data) + bmp)

make_ico()
print('icon created')
"@
    $result = & $python -c $iconScript 2>&1
    if ($result -eq "icon created") {
        Write-OK "App icon created"
    } else {
        Write-Warn "Icon creation skipped (non-critical)"
    }
}

# ── Step 6: Create launcher scripts ──────────────────────────────────────────
Write-Step "Creating launcher..."

$batContent = @"
@echo off
cd /d "%~dp0"
python drillbur_app.py
"@
$batPath = Join-Path $DRILLBUR_DIR "DRILLBUR.bat"
$batContent | Out-File -FilePath $batPath -Encoding ASCII
Write-OK "DRILLBUR.bat created"

# Admin launcher
$adminBatContent = @"
@echo off
cd /d "%~dp0"
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
python drillbur_app.py
"@
$adminBatPath = Join-Path $DRILLBUR_DIR "DRILLBUR_Admin.bat"
$adminBatContent | Out-File -FilePath $adminBatPath -Encoding ASCII
Write-OK "DRILLBUR_Admin.bat created (for elevated access)"

# ── Step 7: Desktop shortcut ──────────────────────────────────────────────────
Write-Step "Creating shortcuts..."
$WshShell = New-Object -ComObject WScript.Shell

# Desktop shortcut
$desktop = $WshShell.SpecialFolders("Desktop")
$shortcut = $WshShell.CreateShortcut("$desktop\DRILLBUR.lnk")
$shortcut.TargetPath = $python
$shortcut.Arguments = "`"$(Join-Path $DRILLBUR_DIR 'drillbur_app.py')`""
$shortcut.WorkingDirectory = $DRILLBUR_DIR
$shortcut.Description = "DRILLBUR - Windows PC Optimizer"
$shortcut.WindowStyle = 1
if (Test-Path $icoPath) {
    # Convert .ico path for shortcut (needs .ico)
    $shortcut.IconLocation = $icoPath
}
$shortcut.Save()
Write-OK "Desktop shortcut created → DRILLBUR.lnk"

# Start Menu shortcut
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$startShortcut = $WshShell.CreateShortcut("$startMenu\DRILLBUR.lnk")
$startShortcut.TargetPath = $python
$startShortcut.Arguments = "`"$(Join-Path $DRILLBUR_DIR 'drillbur_app.py')`""
$startShortcut.WorkingDirectory = $DRILLBUR_DIR
$startShortcut.Description = "DRILLBUR - Windows PC Optimizer"
if (Test-Path $icoPath) { $startShortcut.IconLocation = $icoPath }
$startShortcut.Save()
Write-OK "Start Menu shortcut created"

# ── Step 8: Optional .exe build ───────────────────────────────────────────────
if ($BuildExe) {
    Write-Step "Building standalone .exe with PyInstaller..."
    $piInstalled = & $python -c "import PyInstaller; print('ok')" 2>&1
    if ($piInstalled -ne "ok") {
        Write-Step "Installing PyInstaller..."
        & $python -m pip install pyinstaller --quiet
    }
    $specPath = Join-Path $DRILLBUR_DIR "drillbur.spec"
    if (Test-Path $specPath) {
        Push-Location $DRILLBUR_DIR
        & $python -m PyInstaller drillbur.spec --noconfirm
        Pop-Location
        $exePath = Join-Path $DRILLBUR_DIR "dist\DRILLBUR\DRILLBUR.exe"
        if (Test-Path $exePath) {
            Write-OK ".exe built: $exePath"
        } else {
            Write-Warn ".exe build may have failed — check dist\ folder"
        }
    } else {
        Write-Warn "drillbur.spec not found — skipping .exe build"
    }
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ╔══════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║   ✅  DRILLBUR Installed Successfully!       ║" -ForegroundColor Green
Write-Host "  ╚══════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  How to launch:" -ForegroundColor White
Write-Host "  • Double-click  DRILLBUR  on your Desktop" -ForegroundColor Cyan
Write-Host "  • Or find it in the Start Menu" -ForegroundColor Cyan
Write-Host "  • Or run: python drillbur_app.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "  For full system access:" -ForegroundColor White
Write-Host "  • Use DRILLBUR_Admin.bat (runs as Administrator)" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Installed at: $DRILLBUR_DIR" -ForegroundColor Gray
Write-Host ""

$launch = Read-Host "  Launch DRILLBUR now? (Y/N)"
if ($launch -match "^[Yy]") {
    Write-Host "  🐹 Starting DRILLBUR..." -ForegroundColor Cyan
    Start-Process $python -ArgumentList "`"$(Join-Path $DRILLBUR_DIR 'drillbur_app.py')`"" -WorkingDirectory $DRILLBUR_DIR
}
