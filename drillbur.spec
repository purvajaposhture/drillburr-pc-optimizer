# drillbur.spec
# ─────────────────────────────────────────────────────────────────────────────
# PyInstaller build spec for DRILLBUR Windows PC Optimizer
#
# Usage:
#   pip install pyinstaller
#   pyinstaller drillbur.spec
#
# Output: dist\DRILLBUR\DRILLBUR.exe  (folder mode, easy to distribute)
#         dist\DRILLBUR.exe           (single-file mode — slower to start)
#
# The build includes:
#   - drillbur_app.py     (main entry / tray)
#   - drillbur_backend.py (HTTP server + all API logic)
#   - Drillbur.html       (frontend UI)
#   - assets\drillbur.ico (optional icon)
# ─────────────────────────────────────────────────────────────────────────────

import os
block_cipher = None

a = Analysis(
    ['drillbur_app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Include the frontend HTML
        ('Drillbur.html', '.'),
        # Include assets folder (icon etc.)
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'psutil',
        'psutil._pswindows',
        'tkinter',
        'tkinter.messagebox',
        'http.server',
        'json',
        'threading',
        'webbrowser',
        'subprocess',
        'socket',
        'urllib.parse',
        'urllib.request',
        'pathlib',
        'shutil',
        'glob',
        'platform',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'scipy', 'PIL',
        'PyQt5', 'wx', 'gi', 'cv2',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── OPTION A: Folder build (faster startup, easier) ──────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DRILLBUR',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # No black console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets\\drillbur.ico',   # Windows taskbar/exe icon
    version='version_info.txt',    # Optional: embed version info
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DRILLBUR',
)

# ── OPTION B: Single-file build (comment out COLLECT above, uncomment below) ──
# exe_onefile = EXE(
#     pyz,
#     a.scripts,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     [],
#     name='DRILLBUR',
#     debug=False,
#     bootloader_ignore_signals=False,
#     strip=False,
#     upx=True,
#     console=False,
#     icon='assets\\drillbur.ico',
# )
