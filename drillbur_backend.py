"""
DRILLBUR Backend Server
=======================
A self-contained HTTP API server for the Drillbur Windows PC Optimizer.

Requirements: pip install psutil   (only external dep)
Run:          python drillbur_backend.py
              → opens http://localhost:7474

API Endpoints:
  GET  /api/status          – Live system stats (CPU, RAM, Disk, Net, Battery, Processes)
  GET  /api/scan            – Scan for cleanable junk files
  POST /api/clean           – Delete selected junk items  {items: ["path1","path2"]}
  GET  /api/apps            – List installed applications
  POST /api/uninstall       – Uninstall app               {uninstall_string: "..."}
  POST /api/optimize        – Run an optimization task    {task: "dns"|"wu"|"recycle"|...}
  GET  /api/analyze         – Analyze directory sizes     ?path=C:\\Users
  POST /api/delete          – Delete a file/folder        {path: "..."}
  GET  /api/sysinfo         – Static system information
  GET  /events              – SSE stream for live status (2s updates)
"""

import http.server
import json
import os
import sys
import glob
import shutil
import subprocess
import threading
import time
import platform
import socket
import traceback
import urllib.parse
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

try:
    import psutil
    PSUTIL = True
except ImportError:
    PSUTIL = False
    print("[WARN] psutil not found. Install it: pip install psutil")

# ─── Config ────────────────────────────────────────────────────────────────────
PORT      = 7474
HOST      = "127.0.0.1"
IS_WIN    = sys.platform == "win32"
FRONTEND  = os.path.join(os.path.dirname(__file__), "Drillbur.html")

# ─── Helpers ───────────────────────────────────────────────────────────────────
def fmt_bytes(n: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"

def run_cmd(cmd: str, timeout: int = 30) -> str:
    kw = {}
    if IS_WIN:
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, timeout=timeout, **kw
        )
        return r.stdout.strip()
    except Exception as e:
        return f"[error] {e}"

def dir_size(path: str, max_depth: int = 4, _depth: int = 0) -> int:
    total = 0
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    if e.is_file(follow_symlinks=False):
                        total += e.stat(follow_symlinks=False).st_size
                    elif e.is_dir(follow_symlinks=False) and _depth < max_depth:
                        total += dir_size(e.path, max_depth, _depth + 1)
                except (PermissionError, OSError):
                    pass
    except (PermissionError, OSError):
        pass
    return total

def safe_json(obj) -> str:
    return json.dumps(obj, default=str)

# ─── API Handlers ──────────────────────────────────────────────────────────────

def api_sysinfo() -> dict:
    uname = platform.uname()
    info = {
        "hostname":  uname.node,
        "os":        f"{uname.system} {uname.release}",
        "version":   uname.version,
        "arch":      uname.machine,
        "processor": uname.processor or "Unknown",
        "python":    sys.version.split()[0],
        "is_windows": IS_WIN,
        "psutil":    PSUTIL,
    }
    if PSUTIL:
        info["cpu_count_physical"] = psutil.cpu_count(logical=False)
        info["cpu_count_logical"]  = psutil.cpu_count(logical=True)
        mem = psutil.virtual_memory()
        info["ram_total"] = fmt_bytes(mem.total)
        info["ram_total_bytes"] = mem.total
        try:
            boot = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot
            d = uptime.days
            h, rem = divmod(uptime.seconds, 3600)
            m = rem // 60
            info["uptime"] = f"{d}d {h}h {m}m"
            info["boot_time"] = boot.strftime("%Y-%m-%d %H:%M")
        except Exception:
            info["uptime"] = "Unknown"
    return info


def api_status() -> dict:
    if not PSUTIL:
        return {"error": "psutil not installed"}

    # CPU
    cpu_pct   = psutil.cpu_percent(interval=0.1)
    cpu_freq  = psutil.cpu_freq()
    cpu_cores = psutil.cpu_count(logical=True)
    try:
        per_cpu = psutil.cpu_percent(percpu=True, interval=0)
    except Exception:
        per_cpu = []

    # Memory
    mem  = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # Disk I/O
    try:
        dio = psutil.disk_io_counters()
        disk_read  = dio.read_bytes  if dio else 0
        disk_write = dio.write_bytes if dio else 0
    except Exception:
        disk_read = disk_write = 0

    # Disk usage (C: on Windows, / on others)
    disk_root = "C:\\" if IS_WIN else "/"
    try:
        disk = psutil.disk_usage(disk_root)
        disk_info = {
            "total":   fmt_bytes(disk.total),
            "used":    fmt_bytes(disk.used),
            "free":    fmt_bytes(disk.free),
            "percent": round(disk.percent, 1),
        }
    except Exception:
        disk_info = {"error": "unavailable"}

    # All drive partitions
    drives = []
    try:
        for part in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(part.mountpoint)
                drives.append({
                    "device":     part.device,
                    "mountpoint": part.mountpoint,
                    "fstype":     part.fstype,
                    "total":      fmt_bytes(u.total),
                    "free":       fmt_bytes(u.free),
                    "used":       fmt_bytes(u.used),
                    "percent":    round(u.percent, 1),
                })
            except (PermissionError, OSError):
                pass
    except Exception:
        pass

    # Network
    try:
        net  = psutil.net_io_counters()
        net_info = {
            "bytes_sent":   fmt_bytes(net.bytes_sent),
            "bytes_recv":   fmt_bytes(net.bytes_recv),
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        }
        try:
            conns = len(psutil.net_connections(kind="inet"))
            net_info["connections"] = conns
        except Exception:
            net_info["connections"] = 0
    except Exception:
        net_info = {}

    # Battery
    bat_info = {}
    try:
        bat = psutil.sensors_battery()
        if bat:
            bat_info = {
                "percent":     round(bat.percent, 1),
                "plugged":     bat.power_plugged,
                "status":      "Charging" if bat.power_plugged else "Discharging",
                "time_left":   (
                    str(timedelta(seconds=int(bat.secsleft)))
                    if bat.secsleft and bat.secsleft > 0 else
                    ("Plugged In" if bat.power_plugged else "Unknown")
                ),
            }
        else:
            bat_info = {"status": "No battery / Desktop PC"}
    except Exception:
        bat_info = {"status": "Unavailable"}

    # Top processes
    procs = []
    try:
        all_procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                all_procs.append({
                    "pid":    p.info["pid"],
                    "name":   p.info["name"] or "Unknown",
                    "cpu":    round(p.info["cpu_percent"] or 0, 1),
                    "mem":    round(p.info["memory_percent"] or 0, 1),
                    "status": p.info["status"],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        procs = sorted(all_procs, key=lambda x: x["cpu"], reverse=True)[:10]
    except Exception:
        pass

    # Health score
    health = max(0, min(100, round(
        100 - cpu_pct * 0.35 - mem.percent * 0.35 - disk_info.get("percent", 0) * 0.15
    )))
    health_label = (
        "Excellent" if health >= 85 else
        "Very Good" if health >= 70 else
        "Good"      if health >= 55 else
        "Fair"      if health >= 40 else
        "Poor"
    )

    return {
        "timestamp": datetime.now().isoformat(),
        "health":    {"score": health, "label": health_label},
        "cpu": {
            "percent":    round(cpu_pct, 1),
            "per_core":   [round(x, 1) for x in per_cpu],
            "cores":      cpu_cores,
            "freq_mhz":   round(cpu_freq.current) if cpu_freq else None,
            "freq_max":   round(cpu_freq.max)     if cpu_freq else None,
        },
        "memory": {
            "total":     fmt_bytes(mem.total),
            "used":      fmt_bytes(mem.used),
            "free":      fmt_bytes(mem.available),
            "percent":   round(mem.percent, 1),
            "swap_used": fmt_bytes(swap.used),
            "swap_total":fmt_bytes(swap.total),
            "swap_pct":  round(swap.percent, 1),
        },
        "disk":      disk_info,
        "drives":    drives,
        "disk_io": {
            "read_bytes":  disk_read,
            "write_bytes": disk_write,
        },
        "network":   net_info,
        "battery":   bat_info,
        "processes": procs,
    }


def api_scan() -> dict:
    """Scan for cleanable junk files and return sizes."""
    user    = os.path.expanduser("~")
    local   = os.environ.get("LOCALAPPDATA", os.path.join(user, "AppData", "Local"))
    roaming = os.environ.get("APPDATA",      os.path.join(user, "AppData", "Roaming"))
    win     = os.environ.get("WINDIR", "C:\\Windows") if IS_WIN else "/tmp"

    candidates = [
        {"icon":"🌐","name":"Chrome Cache",        "path": os.path.join(local, "Google","Chrome","User Data","Default","Cache"),           "cat":"Browser"},
        {"icon":"🌐","name":"Chrome Code Cache",   "path": os.path.join(local, "Google","Chrome","User Data","Default","Code Cache"),       "cat":"Browser"},
        {"icon":"🔷","name":"Edge Cache",           "path": os.path.join(local, "Microsoft","Edge","User Data","Default","Cache"),          "cat":"Browser"},
        {"icon":"🦊","name":"Firefox Cache",        "path": os.path.join(roaming,"Mozilla","Firefox","Profiles"),                           "cat":"Browser"},
        {"icon":"🪟","name":"Windows Temp",         "path": os.path.join(win, "Temp")    if IS_WIN else "/tmp",                            "cat":"System"},
        {"icon":"📁","name":"User Temp",            "path": os.environ.get("TEMP", os.path.join(local, "Temp")),                           "cat":"System"},
        {"icon":"📦","name":"Windows Prefetch",     "path": os.path.join(win, "Prefetch") if IS_WIN else "",                               "cat":"System"},
        {"icon":"📦","name":"npm Cache",            "path": os.path.join(local, "npm-cache"),                                              "cat":"Dev"},
        {"icon":"🐍","name":"pip Cache",            "path": os.path.join(local, "pip","cache"),                                            "cat":"Dev"},
        {"icon":"☕","name":"Gradle Cache",         "path": os.path.join(user, ".gradle","caches"),                                        "cat":"Dev"},
        {"icon":"📊","name":"Crash Dumps",          "path": os.path.join(local, "CrashDumps"),                                             "cat":"Logs"},
        {"icon":"🎵","name":"Spotify Cache",        "path": os.path.join(local, "Spotify","Data"),                                         "cat":"Apps"},
        {"icon":"💬","name":"Teams Cache",          "path": os.path.join(roaming,"Microsoft","Teams","Cache"),                             "cat":"Apps"},
        {"icon":"🔔","name":"Discord Cache",        "path": os.path.join(roaming,"discord","Cache"),                                       "cat":"Apps"},
        {"icon":"📜","name":"Windows Event Logs",   "path": os.path.join(win, "System32","winevt","Logs") if IS_WIN else "",               "cat":"Logs"},
        {"icon":"🔄","name":"Windows Update Cache", "path": os.path.join(win, "SoftwareDistribution","Download") if IS_WIN else "",        "cat":"System"},
        {"icon":"🗃️","name":"Internet Cache",      "path": os.path.join(local, "Microsoft","Windows","INetCache"),                        "cat":"Browser"},
        {"icon":"📷","name":"Thumbnail Cache",      "path": os.path.join(local, "Microsoft","Windows","Explorer"),                         "cat":"System"},
    ]

    items = []
    for c in candidates:
        p = c["path"]
        if not p or not os.path.isdir(p):
            continue
        size_bytes = dir_size(p)
        if size_bytes < 1024:   # skip truly empty
            continue
        items.append({
            "icon":       c["icon"],
            "name":       c["name"],
            "path":       p,
            "cat":        c["cat"],
            "size_bytes": size_bytes,
            "size_human": fmt_bytes(size_bytes),
        })

    items.sort(key=lambda x: x["size_bytes"], reverse=True)
    total = sum(i["size_bytes"] for i in items)
    return {
        "items":       items,
        "total_bytes": total,
        "total_human": fmt_bytes(total),
        "count":       len(items),
    }


def api_clean(paths: list) -> dict:
    """Delete files in the given directory paths."""
    freed = 0
    results = []
    for p in paths:
        if not os.path.isdir(p):
            results.append({"path": p, "status": "skipped", "reason": "not found"})
            continue
        size_before = dir_size(p)
        deleted = 0
        errors  = 0
        try:
            for entry in os.scandir(p):
                try:
                    if entry.is_file(follow_symlinks=False):
                        sz = entry.stat(follow_symlinks=False).st_size
                        os.unlink(entry.path)
                        deleted += sz
                    elif entry.is_dir(follow_symlinks=False):
                        sz = dir_size(entry.path)
                        shutil.rmtree(entry.path, ignore_errors=True)
                        deleted += sz
                except (PermissionError, OSError):
                    errors += 1
        except (PermissionError, OSError) as e:
            results.append({"path": p, "status": "error", "reason": str(e)})
            continue
        freed += deleted
        results.append({
            "path":    p,
            "status":  "ok",
            "freed":   fmt_bytes(deleted),
            "errors":  errors,
        })
    return {"freed_total": fmt_bytes(freed), "freed_bytes": freed, "results": results}


def api_apps() -> dict:
    """List all installed applications from the Windows Registry."""
    apps = []
    if not IS_WIN:
        # Non-Windows demo data
        return {"apps": [
            {"name":"Demo App 1","publisher":"Demo Publisher","size":"120 MB","date":"2024-01-01","uninstall_string":""},
            {"name":"Demo App 2","publisher":"Another Co.","size":"45 MB","date":"2023-06-15","uninstall_string":""},
        ], "note": "Registry lookup only available on Windows"}

    ps_cmd = (
        "Get-ItemProperty "
        "'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
        "'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
        "'HKLM:\\Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*' "
        "-ErrorAction SilentlyContinue | "
        "Where-Object { $_.DisplayName } | "
        "Select-Object DisplayName,Publisher,EstimatedSize,InstallDate,UninstallString | "
        "ConvertTo-Json -Compress -Depth 2"
    )
    out = run_cmd(f'powershell -Command "{ps_cmd}"', timeout=20)

    try:
        raw = json.loads(out)
        if isinstance(raw, dict):
            raw = [raw]
        seen = set()
        for item in raw:
            name = (item.get("DisplayName") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            sz   = item.get("EstimatedSize") or 0
            date = item.get("InstallDate") or ""
            if len(date) == 8:
                date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
            unin = (item.get("UninstallString") or "").strip()
            pub  = (item.get("Publisher") or "Unknown").strip()
            now_year = datetime.now().year
            try:
                inst_year = int(date[:4]) if len(date) >= 4 else 0
                old = (now_year - inst_year) >= 2
            except Exception:
                old = False
            apps.append({
                "name":             name,
                "publisher":        pub,
                "size":             fmt_bytes(int(sz) * 1024) if sz else "—",
                "date":             date,
                "uninstall_string": unin,
                "old":              old,
            })
        apps.sort(key=lambda x: x["name"].lower())
    except Exception as e:
        return {"apps": [], "error": str(e)}

    return {"apps": apps, "count": len(apps)}


def api_uninstall(uninstall_string: str) -> dict:
    """Launch the app's own uninstaller."""
    if not uninstall_string:
        return {"status": "error", "reason": "No uninstall string provided"}
    if not IS_WIN:
        return {"status": "error", "reason": "Uninstall only supported on Windows"}
    try:
        subprocess.Popen(uninstall_string, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return {"status": "launched", "cmd": uninstall_string}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def api_optimize(task: str) -> dict:
    """Run a single optimization task and return the result."""
    t = task.lower()

    if t == "dns":
        out = run_cmd("ipconfig /flushdns") if IS_WIN else run_cmd("sudo dscacheutil -flushcache")
        return {"task": t, "status": "ok", "output": out or "DNS cache flushed"}

    elif t == "recycle":
        if IS_WIN:
            out = run_cmd('powershell -Command "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"')
        else:
            trash = os.path.expanduser("~/.local/share/Trash")
            shutil.rmtree(trash, ignore_errors=True)
            os.makedirs(trash, exist_ok=True)
            out = "Trash emptied"
        return {"task": t, "status": "ok", "output": out or "Recycle Bin emptied"}

    elif t == "wu":
        if not IS_WIN:
            return {"task": t, "status": "skip", "output": "Windows-only task"}
        wu = r"C:\Windows\SoftwareDistribution\Download"
        if os.path.isdir(wu):
            freed = dir_size(wu)
            run_cmd("net stop wuauserv")
            shutil.rmtree(wu, ignore_errors=True)
            os.makedirs(wu, exist_ok=True)
            run_cmd("net start wuauserv")
            return {"task": t, "status": "ok", "output": f"Freed {fmt_bytes(freed)} from Windows Update cache"}
        return {"task": t, "status": "ok", "output": "Windows Update cache already clean"}

    elif t == "sfc":
        if not IS_WIN:
            return {"task": t, "status": "skip", "output": "Windows-only task"}
        out = run_cmd("sfc /scannow", timeout=120)
        ok  = "no integrity violations" in (out or "").lower()
        return {"task": t, "status": "ok", "output": out[:300] if out else "SFC scan complete",
                "clean": ok}

    elif t == "icons":
        if not IS_WIN:
            return {"task": t, "status": "skip", "output": "Windows-only task"}
        local = os.environ.get("LOCALAPPDATA", "")
        db    = os.path.join(local, "IconCache.db")
        try:
            if os.path.exists(db):
                os.unlink(db)
        except PermissionError:
            pass
        run_cmd("ie4uinit.exe -show")
        return {"task": t, "status": "ok", "output": "Icon cache rebuilt"}

    elif t == "evtlogs":
        if not IS_WIN:
            return {"task": t, "status": "skip", "output": "Windows-only task"}
        out = run_cmd(
            'powershell -Command "Get-EventLog -List | '
            'ForEach-Object { Clear-EventLog $_.Log -ErrorAction SilentlyContinue }"',
            timeout=30
        )
        return {"task": t, "status": "ok", "output": "Event logs cleared"}

    elif t == "power":
        if not IS_WIN:
            return {"task": t, "status": "skip", "output": "Windows-only task"}
        out = run_cmd("powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c")
        return {"task": t, "status": "ok", "output": "High Performance power plan activated"}

    elif t == "network":
        if not IS_WIN:
            return {"task": t, "status": "skip", "output": "Windows-only task"}
        for cmd in ["netsh winsock reset", "netsh int ip reset",
                    "ipconfig /release", "ipconfig /renew", "ipconfig /flushdns"]:
            run_cmd(cmd, timeout=15)
        return {"task": t, "status": "ok", "output": "Network stack reset. Restart recommended."}

    elif t == "visuals":
        if not IS_WIN:
            return {"task": t, "status": "skip", "output": "Windows-only task"}
        ps = (
            "SystemParametersInfo 0x1048 0 2 3; "   # SPI_SETANIMATION
            "$reg='HKCU:\\Control Panel\\Desktop'; "
            "Set-ItemProperty $reg VisualFXSetting 2"
        )
        run_cmd(f'powershell -Command "{ps}"')
        return {"task": t, "status": "ok", "output": "Visual effects set to best performance"}

    elif t == "startup":
        if IS_WIN:
            subprocess.Popen("taskmgr", shell=True,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        return {"task": t, "status": "ok", "output": "Task Manager opened → go to Startup tab"}

    elif t == "chkdsk":
        if not IS_WIN:
            return {"task": t, "status": "skip", "output": "Windows-only task"}
        run_cmd("chkdsk C: /f /r /x")
        return {"task": t, "status": "ok", "output": "Disk check scheduled for next restart"}

    else:
        return {"task": t, "status": "error", "output": f"Unknown task: {task}"}


def api_analyze(path: str) -> dict:
    """List contents of a directory sorted by size."""
    if not path or not os.path.isdir(path):
        return {"error": f"Path not found: {path}", "items": []}

    items = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        sz   = dir_size(entry.path, max_depth=2)
                        stat = entry.stat(follow_symlinks=False)
                        items.append({
                            "icon":     "📁",
                            "name":     entry.name,
                            "path":     entry.path,
                            "is_dir":   True,
                            "size_bytes": sz,
                            "size_human": fmt_bytes(sz),
                            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                        })
                    elif entry.is_file(follow_symlinks=False):
                        stat = entry.stat(follow_symlinks=False)
                        sz   = stat.st_size
                        items.append({
                            "icon":     "📄",
                            "name":     entry.name,
                            "path":     entry.path,
                            "is_dir":   False,
                            "size_bytes": sz,
                            "size_human": fmt_bytes(sz),
                            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                        })
                except (PermissionError, OSError):
                    pass
    except PermissionError:
        return {"error": f"Permission denied: {path}", "items": []}

    items.sort(key=lambda x: x["size_bytes"], reverse=True)
    total = sum(i["size_bytes"] for i in items)

    # Add percentage
    for item in items:
        item["pct"] = round(item["size_bytes"] / total * 100, 1) if total else 0

    return {
        "path":        path,
        "items":       items[:200],
        "total_bytes": total,
        "total_human": fmt_bytes(total),
        "count":       len(items),
    }


def api_delete(path: str) -> dict:
    """Delete a file or folder."""
    if not path or not os.path.exists(path):
        return {"status": "error", "reason": "Path not found"}
    # Safety guard: never delete root-level paths
    parts = Path(path).parts
    if len(parts) <= 2:
        return {"status": "error", "reason": "Refusing to delete root-level path"}
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.unlink(path)
        return {"status": "ok", "path": path}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


# ─── SSE Status Stream ─────────────────────────────────────────────────────────
_last_io = {"read": 0, "write": 0, "net_sent": 0, "net_recv": 0, "ts": time.time()}

def get_live_deltas(status: dict) -> dict:
    """Add per-second I/O delta rates to the status dict."""
    global _last_io
    now = time.time()
    dt  = now - _last_io["ts"] or 1

    try:
        dio      = psutil.disk_io_counters()
        net      = psutil.net_io_counters()
        read_sp  = (dio.read_bytes  - _last_io["read"])     / dt
        write_sp = (dio.write_bytes - _last_io["write"])    / dt
        dl_sp    = (net.bytes_recv  - _last_io["net_recv"]) / dt
        up_sp    = (net.bytes_sent  - _last_io["net_sent"]) / dt

        _last_io.update({
            "read":     dio.read_bytes,
            "write":    dio.write_bytes,
            "net_sent": net.bytes_sent,
            "net_recv": net.bytes_recv,
            "ts":       now,
        })

        status["disk_io"]["read_speed"]  = fmt_bytes(max(0, read_sp))  + "/s"
        status["disk_io"]["write_speed"] = fmt_bytes(max(0, write_sp)) + "/s"
        status["network"]["download"]    = fmt_bytes(max(0, dl_sp))    + "/s"
        status["network"]["upload"]      = fmt_bytes(max(0, up_sp))    + "/s"
    except Exception:
        pass

    return status


# ─── HTTP Server ───────────────────────────────────────────────────────────────

class DrillburHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # Quiet logger — only print errors
        if "404" in (args[1] if len(args) > 1 else ""):
            print(f"[404] {args[0]}")

    def send_json(self, data: dict, status: int = 200):
        body = safe_json(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_cors()
        self.end_headers()
        self.wfile.write(body)

    def send_cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def send_html(self, path: str):
        try:
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_error(404, "Frontend not found")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        # ── Serve frontend ──
        if path in ("/", "/index.html", "/Drillbur.html"):
            fe = FRONTEND
            if not os.path.exists(fe):
                fe_dir = os.path.dirname(__file__)
                for name in ["Drillbur.html", "drillbur.html", "index.html"]:
                    candidate = os.path.join(fe_dir, name)
                    if os.path.exists(candidate):
                        fe = candidate
                        break
            self.send_html(fe)
            return

        # ── SSE live stream ──
        if path == "/events":
            self.sse_stream()
            return

        # ── REST API ──
        try:
            if path == "/api/status":
                s = api_status()
                if PSUTIL:
                    s = get_live_deltas(s)
                self.send_json(s)

            elif path == "/api/scan":
                self.send_json(api_scan())

            elif path == "/api/apps":
                self.send_json(api_apps())

            elif path == "/api/sysinfo":
                self.send_json(api_sysinfo())

            elif path == "/api/analyze":
                p = params.get("path", [""])[0]
                if not p:
                    p = os.path.expanduser("~")
                self.send_json(api_analyze(p))

            else:
                self.send_json({"error": "Not found"}, 404)

        except Exception as e:
            self.send_json({"error": str(e), "trace": traceback.format_exc()}, 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path

        # Read body
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        try:
            if path == "/api/clean":
                paths = data.get("paths", [])
                self.send_json(api_clean(paths))

            elif path == "/api/uninstall":
                cmd = data.get("uninstall_string", "")
                self.send_json(api_uninstall(cmd))

            elif path == "/api/optimize":
                task = data.get("task", "")
                self.send_json(api_optimize(task))

            elif path == "/api/delete":
                p = data.get("path", "")
                self.send_json(api_delete(p))

            else:
                self.send_json({"error": "Not found"}, 404)

        except Exception as e:
            self.send_json({"error": str(e), "trace": traceback.format_exc()}, 500)

    def sse_stream(self):
        """Server-Sent Events: push live stats every 2 seconds."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_cors()
        self.end_headers()

        try:
            while True:
                s = api_status()
                if PSUTIL:
                    s = get_live_deltas(s)
                payload  = safe_json(s)
                msg      = f"data: {payload}\n\n"
                self.wfile.write(msg.encode())
                self.wfile.flush()
                time.sleep(2)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            print(f"[SSE error] {e}")


# ─── Server Boot ───────────────────────────────────────────────────────────────

class ThreadedHTTPServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads      = True


def print_banner():
    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║   🐹  DRILLBUR Backend Server  v1.0      ║")
    print("  ╠══════════════════════════════════════════╣")
    print(f"  ║   🌐  http://{HOST}:{PORT}               ║")
    print(f"  ║   📊  psutil available: {str(PSUTIL):<17}  ║")
    print(f"  ║   🪟  Windows mode:     {str(IS_WIN):<17}  ║")
    print("  ╠══════════════════════════════════════════╣")
    print("  ║   API Endpoints:                         ║")
    print(f"  ║   GET  /api/status   – Live system stats ║")
    print(f"  ║   GET  /api/scan     – Scan junk files   ║")
    print(f"  ║   POST /api/clean    – Clean files       ║")
    print(f"  ║   GET  /api/apps     – Installed apps    ║")
    print(f"  ║   POST /api/uninstall– Uninstall app     ║")
    print(f"  ║   POST /api/optimize – Run opt task      ║")
    print(f"  ║   GET  /api/analyze  – Disk analyzer     ║")
    print(f"  ║   GET  /events       – SSE live stream   ║")
    print("  ╚══════════════════════════════════════════╝")
    print()
    print("  Press Ctrl+C to stop.")
    print()


def main():
    print_banner()

    # Warn if not admin on Windows
    if IS_WIN:
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
            if not is_admin:
                print("  ⚠  Not running as Administrator.")
                print("     Some tasks (SFC, Windows Temp) need elevated privileges.")
                print("     Right-click → 'Run as Administrator' for full access.")
                print()
        except Exception:
            pass

    server = ThreadedHTTPServer((HOST, PORT), DrillburHandler)

    # Auto-open browser after 1 second
    def open_browser():
        time.sleep(1.2)
        url = f"http://{HOST}:{PORT}"
        print(f"  🚀 Opening browser → {url}")
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()

    print(f"  ✅ Server listening on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  👋 Drillbur server stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
