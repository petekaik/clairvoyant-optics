#!/usr/bin/env python3
"""Clairvoyant-Optics v5.0 — Settings (tkinter, IPC client).

Tab-based settings GUI using macOS HIG conventions:
- Toolbar tab navigation (icon + label)
- Instant-apply on change (via IPC config.set)
- Close-only window controls, Escape to close
- Reads/writes all config through clairvoyantd IPC (not direct file I/O)

Runs as SEPARATE process spawned by menu bar or directly.
"""

import os
import signal
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

VERSION = "5.0.0"

IS_BUNDLED = getattr(sys, "frozen", False)
CONFIG_DIR = Path.home() / ".clairvoyant-optics"
SETTINGS_PID_FILE = CONFIG_DIR / "settings.pid"

# ── IPC Client ─────────────────────────────────────────────────────────

from src.desktop.ipc_client import IPCClient

_ipc: IPCClient | None = None
_config_cache: dict = {}  # Full config as dict, refreshed on load/reload


def _get_ipc() -> IPCClient:
    """Lazy-init IPC connection to daemon."""
    global _ipc
    if _ipc is None:
        _ipc = IPCClient()
        _ipc.connect()
    return _ipc


def _ipc_call(method: str, params: dict | None = None, timeout: float = 5.0) -> dict:
    """IPC RPC wrapper. Returns result dict or raises on error."""
    ipc = _get_ipc()
    if not ipc.connected:
        raise ConnectionError("Daemon not running. Start clairvoyantd first.")
    resp = ipc.call(method, params, timeout=timeout)
    if "error" in resp:
        raise RuntimeError(resp["error"].get("message", str(resp["error"])))
    return resp.get("result", {})


def load_config() -> dict:
    """Load full config from daemon, cache locally."""
    global _config_cache
    _config_cache = _ipc_call("config.get")
    return _config_cache


def save_key(section: str, key: str, value: object) -> bool:
    """Save a single key via IPC. Returns True on success."""
    try:
        _ipc_call("config.set", {"section": section, "key": key, "value": value})
        # Update local cache
        if section in _config_cache and isinstance(_config_cache[section], dict):
            _config_cache[section][key] = value
        return True
    except Exception as e:
        print(f"Config save failed: {e}", file=sys.stderr)
        return False


def reload_config() -> bool:
    """Trigger daemon config reload and refresh cache."""
    try:
        _ipc_call("config.reload")
        load_config()
        return True
    except Exception:
        return False


# ── Settings Window ────────────────────────────────────────────────────

class SettingsWindow:
    """Toolbar-based tabbed settings window. Instant-apply on all changes."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Clairvoyant-Optics Settings")
        self.root.resizable(True, True)
        self.root.minsize(680, 520)

        # Write PID file for menu bar / test scripts
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_PID_FILE.write_text(str(os.getpid()))

        # Center on screen
        w, h = 700, 600
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        x = (ws // 2) - (w // 2)
        y = (hs // 2) - (h // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Escape>", lambda e: self._on_close())
        self.root.bind("<Command-w>", lambda e: self._on_close())

        # Variables for fields (populated after config load)
        self._vars: dict[str, tk.Variable] = {}
        self._after_ids: list[str] = []  # after() IDs for cleanup

        # Build UI
        self._build_toolbar()
        self._build_tabs()
        self._load_and_populate()

        # SIGUSR1 = bring to front (from menu bar)
        signal.signal(signal.SIGUSR1, lambda s, f: self._bring_to_front())

    # ── Toolbar ─────────────────────────────────────────────────────

    def _build_toolbar(self):
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, side=tk.TOP, padx=0, pady=0)

        self._tabs_frame = ttk.Frame(self.root)
        self._tabs_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

        self._tab_buttons: list[ttk.Button] = []
        self._tab_frames: dict[str, ttk.Frame] = {}
        self._current_tab: str | None = None

        tabs = [
            ("general", "General"),
            ("cameras", "Cameras"),
            ("detection", "Detection"),
            ("notifications", "Notifications"),
            ("battery", "Battery"),
            ("telemetry", "Telemetry"),
        ]

        for name, label in tabs:
            btn = ttk.Button(toolbar, text=label, command=lambda n=name: self._switch_tab(n))
            btn.pack(side=tk.LEFT, padx=2, pady=6)
            self._tab_buttons.append((name, btn))
            frame = ttk.Frame(self._tabs_frame)
            self._tab_frames[name] = frame

        self._switch_tab("general")

    def _switch_tab(self, name: str):
        if self._current_tab == name:
            return
        for tab_name, frame in self._tab_frames.items():
            frame.pack_forget()
        self._tab_frames[name].pack(fill=tk.BOTH, expand=True)
        self._current_tab = name

    # ── Tabs ─────────────────────────────────────────────────────────

    def _build_tabs(self):
        self._build_general_tab()
        self._build_cameras_tab()
        self._build_detection_tab()
        self._build_notifications_tab()
        self._build_battery_tab()
        self._build_telemetry_tab()

    # ── General tab ─────────────────────────────────────────────────

    def _build_general_tab(self):
        f = self._tab_frames["general"]
        ttk.Label(f, text="General Settings", font=("Helvetica", 13, "bold")).pack(anchor=tk.W, pady=(10, 15))
        self._add_checkbox(f, "general", "launch_at_login", "Launch at login")
        self._add_checkbox(f, "general", "start_minimized", "Start minimized to menu bar")
        self._add_checkbox(f, "general", "close_to_menu_bar", "Close to menu bar (not quit)")
        self._add_checkbox(f, "general", "confirm_quit", "Confirm before quit")
        self._add_combobox(f, "general", "log_level", "Log level", ["DEBUG", "INFO", "WARNING", "ERROR"])

    # ── Cameras tab ──────────────────────────────────────────────────

    def _build_cameras_tab(self):
        f = self._tab_frames["cameras"]
        ttk.Label(f, text="Camera Configuration", font=("Helvetica", 13, "bold")).pack(anchor=tk.W, pady=(10, 15))

        self._cameras_list_frame = ttk.Frame(f)
        self._cameras_list_frame.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(f)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="+ Add Camera", command=self._add_camera_row).pack(side=tk.LEFT, padx=5)

    def _add_camera_row(self, data: dict | None = None):
        """Add one camera row (or populate from data)."""
        data = data or {"name": "", "stream_url": "", "snap_url": "", "enabled": True}
        row = ttk.Frame(self._cameras_list_frame)
        row.pack(fill=tk.X, pady=4)

        ttk.Label(row, text="Name:").pack(side=tk.LEFT, padx=(0, 4))
        name_var = tk.StringVar(value=data.get("name", ""))
        ttk.Entry(row, textvariable=name_var, width=16).pack(side=tk.LEFT, padx=4)
        name_var.trace_add("write", lambda *a, v=name_var: save_key("cameras", "dirty", True))

        ttk.Label(row, text="Stream:").pack(side=tk.LEFT, padx=4)
        stream_var = tk.StringVar(value=data.get("stream_url", ""))
        ttk.Entry(row, textvariable=stream_var, width=28).pack(side=tk.LEFT, padx=4)

        ttk.Label(row, text="Snap:").pack(side=tk.LEFT, padx=4)
        snap_var = tk.StringVar(value=data.get("snap_url", ""))
        ttk.Entry(row, textvariable=snap_var, width=28).pack(side=tk.LEFT, padx=4)

        enabled_var = tk.BooleanVar(value=data.get("enabled", True))
        ttk.Checkbutton(row, text="On", variable=enabled_var).pack(side=tk.LEFT, padx=8)

        ttk.Button(row, text="✕", width=3, command=lambda r=row: r.destroy()).pack(side=tk.RIGHT)

    # ── Detection tab ────────────────────────────────────────────────

    def _build_detection_tab(self):
        f = self._tab_frames["detection"]
        ttk.Label(f, text="Detection Settings", font=("Helvetica", 13, "bold")).pack(anchor=tk.W, pady=(10, 15))
        self._add_scale(f, "detection", "person_confidence", "Person detection confidence", 0.2, 1.0, 0.05)
        self._add_scale(f, "detection", "face_confidence", "Face detection confidence", 0.2, 1.0, 0.05)
        self._add_scale(f, "detection", "recognition_threshold", "Recognition threshold", 0.3, 0.95, 0.05)
        self._add_spinbox(f, "detection", "frame_interval", "Frame interval (every Nth frame)", 1, 60)
        self._add_spinbox(f, "detection", "debounce_seconds", "Debounce (seconds)", 5, 300)

    # ── Notifications tab ────────────────────────────────────────────

    def _build_notifications_tab(self):
        f = self._tab_frames["notifications"]
        ttk.Label(f, text="Notification Settings", font=("Helvetica", 13, "bold")).pack(anchor=tk.W, pady=(10, 15))
        self._add_checkbox(f, "notifications", "enabled", "Enable notifications")
        self._add_checkbox(f, "notifications", "notify_on_family", "Notify on family member")
        self._add_checkbox(f, "notifications", "notify_on_unknown", "Notify on unknown person")
        self._add_entry(f, "notifications", "sound_family", "Family notification sound")
        self._add_entry(f, "notifications", "sound_alert", "Alert notification sound")
        self._add_entry(f, "notifications", "dnd_start", "DND start (HH:MM)", width=8)
        self._add_entry(f, "notifications", "dnd_end", "DND end (HH:MM)", width=8)

    # ── Battery tab ──────────────────────────────────────────────────

    def _build_battery_tab(self):
        f = self._tab_frames["battery"]
        ttk.Label(f, text="Battery & WiFi", font=("Helvetica", 13, "bold")).pack(anchor=tk.W, pady=(10, 15))
        self._add_checkbox(f, "battery", "pause_on_battery", "Pause detection on battery")
        self._add_checkbox(f, "battery", "pause_when_away", "Pause when away from home WiFi")
        self._add_entry(f, "battery", "home_ssids", "Home WiFi SSIDs (comma-separated)")
        self._add_spinbox(f, "battery", "poll_interval", "Poll interval (seconds)", 10, 300)

    # ── Telemetry tab ────────────────────────────────────────────────

    def _build_telemetry_tab(self):
        f = self._tab_frames["telemetry"]
        ttk.Label(f, text="Telemetry & Updates", font=("Helvetica", 13, "bold")).pack(anchor=tk.W, pady=(10, 15))
        self._add_checkbox(f, "telemetry", "auto_update", "Auto-update (check every 6h)")
        self._add_checkbox(f, "telemetry", "error_reporting", "Anonymous error reporting")
        lbl = ttk.Label(
            f,
            text="Error reports are auto-labeled and analyzed daily.\nNo personal data is sent.",
            foreground="gray",
        )
        lbl.pack(anchor=tk.W, pady=(0, 10))

    # ── Field helpers ────────────────────────────────────────────────

    def _add_checkbox(self, parent, section: str, key: str, label: str):
        var = tk.BooleanVar()
        cb = ttk.Checkbutton(parent, text=label, variable=var)
        cb.pack(anchor=tk.W, pady=4)
        var.trace_add("write", lambda *a, s=section, k=key, v=var: save_key(s, k, v.get()))
        self._vars[f"{section}.{key}"] = var

    def _add_entry(self, parent, section: str, key: str, label: str, width: int = 30):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text=label, width=26, anchor=tk.W).pack(side=tk.LEFT)
        var = tk.StringVar()
        e = ttk.Entry(row, textvariable=var, width=width)
        e.pack(side=tk.LEFT)
        var.trace_add("write", lambda *a, s=section, k=key, v=var: save_key(s, k, v.get()))
        self._vars[f"{section}.{key}"] = var

    def _add_combobox(self, parent, section: str, key: str, label: str, values: list[str]):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text=label, width=26, anchor=tk.W).pack(side=tk.LEFT)
        var = tk.StringVar()
        cb = ttk.Combobox(row, textvariable=var, values=values, state="readonly", width=18)
        cb.pack(side=tk.LEFT)
        var.trace_add("write", lambda *a, s=section, k=key, v=var: save_key(s, k, v.get()))
        self._vars[f"{section}.{key}"] = var

    def _add_scale(self, parent, section: str, key: str, label: str, from_: float, to: float, step: float):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text=label, width=30, anchor=tk.W).pack(side=tk.LEFT)
        var = tk.DoubleVar()
        scale = ttk.Scale(row, from_=from_, to=to, variable=var, length=200)
        scale.pack(side=tk.LEFT, padx=8)
        val_lbl = ttk.Label(row, text="0.00", width=5)
        val_lbl.pack(side=tk.LEFT)
        var.trace_add("write", lambda *a, s=section, k=key, v=var, vl=val_lbl: self._on_scale_change(s, k, v, vl))
        self._vars[f"{section}.{key}"] = var

    def _add_spinbox(self, parent, section: str, key: str, label: str, from_: int, to: int):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text=label, width=30, anchor=tk.W).pack(side=tk.LEFT)
        var = tk.IntVar()
        sb = ttk.Spinbox(row, from_=from_, to=to, textvariable=var, width=8)
        sb.pack(side=tk.LEFT)
        var.trace_add("write", lambda *a, s=section, k=key, v=var: save_key(s, k, str(v.get())))
        self._vars[f"{section}.{key}"] = var

    # ── Data ─────────────────────────────────────────────────────────

    def _load_and_populate(self):
        """Load config from daemon and fill all fields."""
        try:
            cfg = load_config()
        except Exception as e:
            self._show_error(f"Failed to connect to daemon:\n{e}\n\nStart clairvoyantd first.")
            return

        # Set form values from loaded config
        for full_key, var in self._vars.items():
            section, key = full_key.split(".", 1)
            section_data = cfg.get(section, {})
            if isinstance(section_data, dict) and key in section_data:
                value = section_data[key]
                try:
                    if isinstance(var, tk.BooleanVar):
                        var.set(bool(value))
                    elif isinstance(var, tk.DoubleVar):
                        var.set(float(value))
                    elif isinstance(var, tk.IntVar):
                        var.set(int(value))
                    else:
                        var.set(str(value) if value is not None else "")
                except Exception:
                    pass  # Type mismatch — leave default

        # Populate cameras
        camera_data = cfg.get("cameras", [])
        if isinstance(camera_data, list):
            for cam in camera_data:
                if isinstance(cam, dict):
                    self._add_camera_row(cam)

    def _on_scale_change(self, section: str, key: str, var: tk.DoubleVar, label: ttk.Label):
        """Update scale label and save."""
        val = round(var.get(), 2)
        label.config(text=f"{val:.2f}")
        save_key(section, key, val)

    # ── Window management ────────────────────────────────────────────

    def _bring_to_front(self):
        """Bring window to front (SIGUSR1 handler). Runs on main thread via after()."""
        def _raise():
            try:
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
            except Exception:
                pass
        self.root.after(0, _raise)

    def _on_close(self):
        SETTINGS_PID_FILE.unlink(missing_ok=True)
        if _ipc:
            _ipc.close()
        self.root.destroy()

    def _show_error(self, message: str):
        """Show error dialog if daemon unavailable."""
        top = tk.Toplevel(self.root)
        top.title("Connection Error")
        top.geometry("400x160")
        top.resizable(False, False)
        ttk.Label(top, text=message, wraplength=360, justify=tk.LEFT).pack(padx=20, pady=20)
        ttk.Button(top, text="Retry", command=lambda: [top.destroy(), self._load_and_populate()]).pack(pady=5)
        ttk.Button(top, text="Close", command=self._on_close).pack(pady=5)

    def run(self):
        self.root.mainloop()


# ── Main ───────────────────────────────────────────────────────────────

def main():
    try:
        app = SettingsWindow()
        app.run()
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
