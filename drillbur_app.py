"""
DRILLBUR — Windows PC Optimizer
================================
Main application entry point.

This script:
1. Creates a system tray icon (via tkinter)
2. Starts the backend HTTP server in a background thread
3. Opens the UI in the default browser
4. Provides tray menu: Open, Run Clean, Status, Exit

Run directly:   python drillbur_app.py
Build to .exe:  pyinstaller drillbur.spec
"""

import sys
import os
import time
import threading
import webbrowser
import socket
import subprocess
import tkinter as tk
from tkinter import messagebox

# ── Resolve paths (works both as script and frozen .exe) ─────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)

# ── Make backend importable ───────────────────────────────────────────────────
sys.path.insert(0, BASE_DIR)
import drillbur_backend as backend

PORT = 7474
URL  = f"http://127.0.0.1:{PORT}"

# ── Check if port already in use ─────────────────────────────────────────────
def port_free(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            return s.connect_ex(("127.0.0.1", port)) != 0
    except Exception:
        return True

# ── Tray icon (tkinter-based, no extra deps) ──────────────────────────────────
class DrillburTray:
    """Minimal Windows system tray via tkinter withdraw + wm_iconify hack."""

    def __init__(self, server_thread: threading.Thread):
        self.server_thread = server_thread
        self.root = tk.Tk()
        self.root.withdraw()               # hide main window
        self.root.title("DRILLBUR")
        self.root.resizable(False, False)

        # On Windows, set taskbar icon
        try:
            ico = os.path.join(BASE_DIR, "assets", "drillbur.ico")
            if os.path.exists(ico):
                self.root.iconbitmap(ico)
        except Exception:
            pass

        self._build_menu()
        self._make_tray()
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)

    def _build_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0,
                            bg="#1a1410", fg="#e6edf3",
                            activebackground="#b8948a", activeforeground="white",
                            font=("Segoe UI", 10))
        self.menu.add_command(label="🐹  Open DRILLBUR",  command=self.open_ui)
        self.menu.add_separator()
        self.menu.add_command(label="🧹  Quick Clean",    command=self.quick_clean)
        self.menu.add_command(label="📊  System Status",  command=self.open_status)
        self.menu.add_separator()
        self.menu.add_command(label="ℹ️  About",          command=self.show_about)
        self.menu.add_separator()
        self.menu.add_command(label="✖  Exit",            command=self.on_exit)

    def _make_tray(self):
        """Create a tiny always-on-top indicator window as tray substitute."""
        self.tray_win = tk.Toplevel(self.root)
        self.tray_win.title("DRILLBUR")
        self.tray_win.geometry("220x56+{}+{}".format(
            self.root.winfo_screenwidth() - 240,
            self.root.winfo_screenheight() - 100
        ))
        self.tray_win.overrideredirect(True)
        self.tray_win.attributes("-topmost", True)
        self.tray_win.attributes("-alpha", 0.95)
        self.tray_win.configure(bg="#110e0b")

        # Border frame
        frame = tk.Frame(self.tray_win, bg="#b8948a", padx=1, pady=1)
        frame.pack(fill="both", expand=True)
        inner = tk.Frame(frame, bg="#110e0b", padx=10, pady=8)
        inner.pack(fill="both", expand=True)

        # Status dot
        self.dot_var = tk.StringVar(value="●")
        self.dot_lbl = tk.Label(inner, textvariable=self.dot_var,
                                bg="#110e0b", fg="#7a9a6e",
                                font=("Segoe UI", 10))
        self.dot_lbl.pack(side="left", padx=(0, 6))

        tk.Label(inner, text="DRILLBUR", bg="#110e0b", fg="#d4b5ae",
                 font=("Segoe UI Semibold", 11, "bold")).pack(side="left")

        btn = tk.Label(inner, text="⊕", bg="#110e0b", fg="#b8948a",
                       font=("Segoe UI", 14), cursor="hand2")
        btn.pack(side="right")
        btn.bind("<Button-1>", lambda e: self.open_ui())

        # Right-click menu
        for widget in (self.tray_win, frame, inner, btn):
            widget.bind("<Button-3>", self.show_menu)
        self.tray_win.bind("<Button-1>", lambda e: self.open_ui())

        # Drag support
        self.tray_win.bind("<ButtonPress-1>",   self._drag_start)
        self.tray_win.bind("<B1-Motion>",        self._drag_move)

        # Animate dot
        self._animate_dot()

    def _animate_dot(self):
        colors = ["#7a9a6e", "#5a7a4e", "#9aba8e"]
        idx = getattr(self, "_dot_idx", 0)
        self.dot_lbl.configure(fg=colors[idx % len(colors)])
        self._dot_idx = idx + 1
        self.root.after(800, self._animate_dot)

    def _drag_start(self, e):
        self._drag_x = e.x_root - self.tray_win.winfo_x()
        self._drag_y = e.y_root - self.tray_win.winfo_y()

    def _drag_move(self, e):
        self.tray_win.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")

    def show_menu(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def open_ui(self):
        webbrowser.open(URL)

    def open_status(self):
        webbrowser.open(URL + "#status")

    def quick_clean(self):
        import urllib.request, json
        try:
            # Scan first
            with urllib.request.urlopen(URL + "/api/scan", timeout=5) as r:
                data = json.loads(r.read())
            total = data.get("total_human", "?")
            count = data.get("count", 0)
            if count == 0:
                messagebox.showinfo("DRILLBUR", "✅ Your PC is already clean!")
                return
            ok = messagebox.askyesno(
                "DRILLBUR — Quick Clean",
                f"Found {count} junk items ({total} reclaimable).\n\nClean them all now?"
            )
            if not ok:
                return
            paths = [i["path"] for i in data.get("items", [])]
            req = urllib.request.Request(
                URL + "/api/clean",
                data=json.dumps({"paths": paths}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                result = json.loads(r.read())
            messagebox.showinfo(
                "DRILLBUR — Done!",
                f"✅ Cleaned successfully!\nTotal freed: {result.get('freed_total','?')}"
            )
        except Exception as ex:
            messagebox.showerror("DRILLBUR", f"Error: {ex}")

    def show_about(self):
        messagebox.showinfo(
            "About DRILLBUR",
            "🐹  DRILLBUR v1.0\n"
            "Windows PC Optimizer\n\n"
            "Features:\n"
            "  • Deep junk file cleaning\n"
            "  • Smart app uninstaller\n"
            "  • 10 system optimization tasks\n"
            "  • Disk space analyzer\n"
            "  • Live system status\n\n"
            f"Running at: {URL}\n"
            "Inspired by Mole (tw93/Mole)"
        )

    def on_exit(self):
        if messagebox.askokcancel("DRILLBUR", "Exit DRILLBUR?"):
            self.root.destroy()
            os._exit(0)

    def run(self):
        self.root.mainloop()


# ── Startup splash (shown while backend boots) ────────────────────────────────
class SplashScreen:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.97)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 360, 220
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.root.configure(bg="#110e0b")

        # Border
        border = tk.Frame(self.root, bg="#b8948a", padx=2, pady=2)
        border.pack(fill="both", expand=True)
        inner = tk.Frame(border, bg="#110e0b")
        inner.pack(fill="both", expand=True, padx=0, pady=0)

        # Mascot ASCII
        tk.Label(inner, text="🐹", bg="#110e0b", font=("Segoe UI Emoji", 42)
                 ).pack(pady=(28, 4))

        tk.Label(inner, text="DRILLBUR", bg="#110e0b", fg="#d4b5ae",
                 font=("Segoe UI", 20, "bold")).pack()

        tk.Label(inner, text="Windows PC Optimizer", bg="#110e0b",
                 fg="#7d6560", font=("Segoe UI", 10)).pack(pady=(2, 14))

        self.status_var = tk.StringVar(value="Starting backend…")
        tk.Label(inner, textvariable=self.status_var, bg="#110e0b",
                 fg="#b8948a", font=("Segoe UI", 9)).pack()

        # Progress bar
        self.bar_frame = tk.Frame(inner, bg="#2a1f1a", height=4, width=280)
        self.bar_frame.pack(pady=(10, 0))
        self.bar_frame.pack_propagate(False)
        self.bar_fill = tk.Frame(self.bar_frame, bg="#b8948a", height=4, width=0)
        self.bar_fill.pack(side="left")

        self._progress = 0
        self._animate()

    def _animate(self):
        self._progress = min(90, self._progress + 3)
        self.bar_fill.configure(width=int(280 * self._progress / 100))
        self.root.after(60, self._animate)

    def set_status(self, msg: str):
        self.status_var.set(msg)
        self.root.update()

    def finish(self):
        self._progress = 100
        self.bar_fill.configure(width=280)
        self.root.update()
        time.sleep(0.3)
        self.root.destroy()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # Show splash
    splash = SplashScreen()
    splash.root.update()

    # Check if already running
    if not port_free(PORT):
        splash.set_status("Already running — opening browser…")
        time.sleep(0.5)
        splash.finish()
        webbrowser.open(URL)
        return

    # Set frontend path
    fe = os.path.join(BASE_DIR, "Drillbur.html")
    if not os.path.exists(fe):
        messagebox.showerror("DRILLBUR", f"Frontend not found:\n{fe}")
        sys.exit(1)
    backend.FRONTEND = fe

    splash.set_status("Starting HTTP server…")

    # Start backend server
    server = backend.ThreadedHTTPServer(("127.0.0.1", PORT), backend.DrillburHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Wait for server to be ready
    for _ in range(20):
        if not port_free(PORT):
            break
        time.sleep(0.1)

    splash.set_status("Opening DRILLBUR…")
    time.sleep(0.4)
    splash.finish()

    # Open browser
    webbrowser.open(URL)

    # Show tray
    tray = DrillburTray(server_thread)
    tray.run()


if __name__ == "__main__":
    main()
