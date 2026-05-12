#!/usr/bin/env python3
"""Clairvoyant-Optics v4.0.2 — Settings window (tkinter).

Runs as a SEPARATE process from app.py.
No Dock icon — hidden via osascript on startup (LSUIElement only works in .app bundles).

Communication:
  SIGUSR1 → deiconify + bring to front
  SIGTERM → quit
"""

import os
import signal
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

VERSION = "4.0.2"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = Path.home() / ".clairvoyant-optics"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

DEFAULTS = {
    "start_minimized": True,
    "launch_at_login": False,
    "close_to_menu_bar": True,
    "confirm_quit": False,
    "auto_update": False,
    "error_reporting": False,
    "pause_on_battery": False,
    "home_ssids": "",
    "pause_when_away": False,
    "log_level": "INFO",
}


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
        if path.exists():
            data = yaml.safe_load(open(path))
            return data if isinstance(data, dict) else {}
    except ImportError:
        pass
    return {}


def _save_yaml(path: Path, data: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import yaml
        yaml.safe_dump(data, open(path, "w"), default_flow_style=False, allow_unicode=True)
    except ImportError:
        with open(path, "w") as f:
            for k, v in data.items():
                f.write(f"{k}: {v}\n")


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(_load_yaml(CONFIG_FILE))
    return cfg


def save_config(cfg: dict):
    _save_yaml(CONFIG_FILE, cfg)


def _hide_from_dock():
    """Hide this process from the macOS Dock using Carbon TransformProcessType.

    Called immediately after tk.Tk() in SettingsWindow.__init__.
    LSUIElement=True only works in .app bundles.
    """
    import ctypes
    import ctypes.util

    lib = ctypes.CDLL(ctypes.util.find_library("Carbon"))
    psn = (ctypes.c_ulong * 2)(0, 0)
    lib.GetCurrentProcess(ctypes.byref(psn))
    # kProcessTransformToUIElementApplication = 4
    result = lib.TransformProcessType(ctypes.byref(psn), 4)
    # Force Dock refresh via NSApp
    try:
        from Cocoa import NSApplication
        NSApp = NSApplication.sharedApplication()
        NSApp.activateIgnoringOtherApps_(True)
    except Exception:
        pass
    return result == 0  # noErr


# ═══════════════════════════════════════════════════════════
# Settings Window
# ═══════════════════════════════════════════════════════════

class SettingsWindow:
    def __init__(self):
        self._root = tk.Tk()
        _hide_from_dock()  # immediately after Tk() — remove Dock icon it created

        self._root.title("Clairvoyant-Optics Settings")
        self._root.configure(bg="#1c1c1e")
        self._root.geometry("580x520")
        self._root.minsize(480, 400)
        self._root.withdraw()  # start hidden, shown after mainloop starts

        self._cfg = load_config()
        self._setup_signals()
        self._setup_window_protocol()
        self._build_ui()

    def _setup_signals(self):
        signal.signal(signal.SIGUSR1, lambda s, f: self._root.after(0, self._show))

        def _on_sigterm(signum, frame):
            # Clean exit: remove our PID file
            (CONFIG_DIR / "settings.pid").unlink(missing_ok=True)
            try:
                self._root.destroy()
            except Exception:
                pass
            sys.exit(0)
        signal.signal(signal.SIGTERM, _on_sigterm)

    def _setup_window_protocol(self):
        """Red X behavior: close_to_menu_bar → hide, otherwise → quit."""
        def _on_close():
            if self._cfg.get("close_to_menu_bar", True):
                self._root.withdraw()
            elif self._cfg.get("confirm_quit", False):
                if messagebox.askyesno("Quit?", "Quit Clairvoyant-Optics?"):
                    self._quit()
            else:
                self._quit()
        self._root.protocol("WM_DELETE_WINDOW", _on_close)

    def _show(self):
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()

    def _quit(self):
        (CONFIG_DIR / "settings.pid").unlink(missing_ok=True)
        try:
            self._root.destroy()
        except Exception:
            pass
        sys.exit(0)

    # ── UI ──────────────────────────────────────────────────

    def _build_ui(self):
        for w in self._root.winfo_children():
            w.destroy()

        main = tk.Frame(self._root, bg="#1c1c1e")
        main.pack(fill="both", expand=True, padx=24, pady=20)

        # Header
        hdr = tk.Frame(main, bg="#1c1c1e")
        hdr.pack(fill="x", pady=(0, 16))
        tk.Label(hdr, text="\U0001F441 Clairvoyant-Optics",
                 font=("SF Pro Display", 20, "bold"),
                 fg="#ffffff", bg="#1c1c1e").pack(side="left")
        tk.Label(hdr, text=f"v{VERSION}",
                 font=("SF Pro Text", 11),
                 fg="#8e8e93", bg="#1c1c1e").pack(side="right", pady=(6, 0))

        self._notebook = ttk.Notebook(main)
        self._notebook.pack(fill="both", expand=True)

        style = ttk.Style()
        style.configure("TNotebook", background="#1c1c1e", borderwidth=0)
        style.configure("TNotebook.Tab", padding=[16, 8], font=("SF Pro Text", 12))
        style.map("TNotebook.Tab", background=[("selected", "#2c2c2e")])

        self._build_general_tab()
        self._build_behavior_tab()
        self._build_advanced_tab()

        # Status bar
        sf = tk.Frame(main, bg="#1c1c1e")
        sf.pack(fill="x", pady=(12, 0))
        self._status_label = tk.Label(
            sf, text=f"Config: {CONFIG_FILE}",
            font=("SF Pro Text", 10), fg="#636366", bg="#1c1c1e")
        self._status_label.pack(side="left")
        tk.Label(sf, text="Changes save automatically",
                 font=("SF Pro Text", 10), fg="#636366", bg="#1c1c1e").pack(side="right")

    def _build_general_tab(self):
        tab = tk.Frame(self._notebook, bg="#1c1c1e")
        self._notebook.add(tab, text="  General  ")

        row = tk.Frame(tab, bg="#1c1c1e")
        row.pack(fill="x", pady=(12, 8))
        tk.Label(row, text="Log Level",
                 font=("SF Pro Text", 12, "bold"),
                 fg="#ffffff", bg="#1c1c1e").pack(side="left")

        levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        var = tk.StringVar(value=self._cfg.get("log_level", "INFO"))
        opt = tk.OptionMenu(row, var, *levels,
                            command=lambda v: self._set("log_level", v))
        opt.configure(bg="#2c2c2e", fg="#ffffff",
                      activebackground="#3c3c3e", activeforeground="#ffffff",
                      font=("SF Pro Text", 12))
        opt.pack(side="right")

    def _build_behavior_tab(self):
        tab = tk.Frame(self._notebook, bg="#1c1c1e")
        self._notebook.add(tab, text="  Behavior  ")

        self._mk_toggle(tab, "Start Minimized",
                        "Launch directly to menu bar (no settings window)",
                        "start_minimized")
        self._mk_toggle(tab, "Close to Menu Bar",
                        "Closing the window hides it to menu bar instead of quitting",
                        "close_to_menu_bar")
        self._mk_toggle(tab, "Launch at Login",
                        "Start automatically when you log in to your Mac",
                        "launch_at_login")
        self._mk_toggle(tab, "Confirm Before Quit",
                        "Ask for confirmation before quitting the application",
                        "confirm_quit")

    def _build_advanced_tab(self):
        tab = tk.Frame(self._notebook, bg="#1c1c1e")
        self._notebook.add(tab, text="  Advanced  ")

        self._mk_toggle(tab, "Auto-Update",
                        "Check for updates every 6 hours",
                        "auto_update")
        self._mk_toggle(tab, "Error Reporting",
                        "Send error reports to GitHub Issues automatically",
                        "error_reporting")
        self._mk_toggle(tab, "Pause When on Battery",
                        "Pause recognition when Mac is on battery power",
                        "pause_on_battery")
        self._mk_toggle(tab, "Pause When Away from Home",
                        "Pause recognition when not connected to home WiFi",
                        "pause_when_away")

        # Home SSIDs
        row = tk.Frame(tab, bg="#1c1c1e")
        row.pack(fill="x", pady=(20, 4))
        tk.Label(row, text="Home WiFi SSIDs",
                 font=("SF Pro Text", 12, "bold"),
                 fg="#ffffff", bg="#1c1c1e").pack(anchor="w")
        tk.Label(row,
                 text="Comma-separated list (e.g. HomeWiFi, CottageWiFi)",
                 font=("SF Pro Text", 10),
                 fg="#8e8e93", bg="#1c1c1e").pack(anchor="w", pady=(2, 0))

        entry = tk.Entry(tab, bg="#2c2c2e", fg="#ffffff",
                         insertbackground="#ffffff",
                         font=("SF Pro Text", 13), relief="flat", bd=8)
        entry.insert(0, self._cfg.get("home_ssids", ""))
        entry.pack(fill="x", ipady=4)

        def _save_ssids(e=None):
            self._set("home_ssids", entry.get().strip())

        entry.bind("<FocusOut>", _save_ssids)
        entry.bind("<Return>", _save_ssids)

    def _mk_toggle(self, parent, title: str, desc: str, key: str):
        row = tk.Frame(parent, bg="#1c1c1e")
        row.pack(fill="x", pady=(16, 0))

        left = tk.Frame(row, bg="#1c1c1e")
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=title,
                 font=("SF Pro Text", 12, "bold"),
                 fg="#ffffff", bg="#1c1c1e").pack(anchor="w")
        tk.Label(left, text=desc,
                 font=("SF Pro Text", 10),
                 fg="#8e8e93", bg="#1c1c1e").pack(anchor="w", pady=(2, 0))

        var = tk.BooleanVar(value=bool(self._cfg.get(key)))
        cb = tk.Checkbutton(
            row, variable=var,
            command=lambda k=key, v=var: self._set(k, v.get()),
            bg="#1c1c1e", fg="#ffffff",
            selectcolor="#1c1c1e",
            activebackground="#1c1c1e", activeforeground="#ffffff",
            font=("SF Pro Text", 13))
        cb.pack(side="right", padx=(16, 0))

    def _set(self, key: str, value):
        self._cfg[key] = value
        save_config(self._cfg)
        self._status_label.configure(text=f"\u2713 Saved: {key} = {value}")

        # Notify app.py to update launch_at_login
        if key == "launch_at_login":
            app_pid_file = CONFIG_DIR / "app.pid"
            try:
                if app_pid_file.exists():
                    pid = int(app_pid_file.read_text().strip())
                    os.kill(pid, signal.SIGUSR2)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    window = SettingsWindow()
    window._show()
    window._root.mainloop()
