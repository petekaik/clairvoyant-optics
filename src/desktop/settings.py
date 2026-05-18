#!/usr/bin/env python3
"""Clairvoyant-Optics v5.0.1 — Settings (macOS HIG + IPC).

Architecture
  Toolbar-based tab navigation (icon + label), modeless instant-apply,
  close-only window controls, Escape / ⌘. / ⌘W to close.

  Dual config backend:
    Primary:   IPC to clairvoyantd daemon (config.get / config.set)
    Fallback:  Direct YAML read/write if daemon unreachable

  Runs as SEPARATE process — spawned via open -a Settings.app (bundle)
  or python settings.py (dev).

IPC: SIGUSR1 → show, SIGTERM → quit
"""

import os
import signal
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

VERSION = "5.3.0"

# ── paths ──────────────────────────────────────────────────────────────

IS_BUNDLED = getattr(sys, "frozen", False) or (
    "Contents/Resources" in str(Path(__file__).resolve())
)
if IS_BUNDLED:
    BUNDLE_DIR = Path(__file__).resolve().parent          # Contents/Resources/
    BUNDLE_CONTENTS = BUNDLE_DIR.parent                    # Contents/
else:
    BUNDLE_DIR = None
    BUNDLE_CONTENTS = None
CONFIG_DIR = Path.home() / ".clairvoyant-optics"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

DEFAULTS: dict = {
    "log_level": "INFO",
    "start_minimized": True,
    "close_to_menu_bar": True,
    "launch_at_login": False,
    "confirm_quit": False,
    "auto_update": False,
    "error_reporting": False,
    "pause_on_battery": False,
    "pause_when_away": False,
    "home_ssids": "",
    "cameras": [],
    "notifications_enabled": True,
    "notify_on_family": True,
    "notify_on_unknown": True,
    "notification_sound_family": "default",
    "notification_sound_alert": "alarm",
    "notification_dnd_start": "",
    "notification_dnd_end": "",
}

# ── Dual config backend ───────────────────────────────────────────────

_ipc = None

def _get_ipc():
    """Lazy-init IPC client. Returns None if daemon unreachable."""
    global _ipc
    if _ipc is None:
        try:
            from src.desktop.ipc_client import IPCClient
            _ipc = IPCClient()
            if not _ipc.connect():
                _ipc = None
        except Exception:
            _ipc = None
    return _ipc

def _ipc_call(method: str, params: dict | None = None, timeout: float = 5.0) -> dict | None:
    ipc = _get_ipc()
    if ipc is None or not ipc.connected:
        return None
    resp = ipc.call(method, params, timeout=timeout)
    if "error" in resp:
        return None
    return resp.get("result")

# ── yaml helpers (fallback when daemon offline) ───────────────────────

def _load_yaml(path: Path) -> dict:
    try:
        import yaml
        if path.exists():
            data = yaml.safe_load(open(path))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}

def _save_yaml(path: Path, data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import yaml
        yaml.safe_dump(data, open(path, "w"), default_flow_style=False, allow_unicode=True)
    except Exception:
        with open(path, "w") as f:
            for k, v in data.items():
                f.write(f"{k}: {v}\n")

def load_config() -> dict:
    """Load config: try IPC first, fallback to YAML."""
    result = _ipc_call("config.get")
    if result and isinstance(result, dict):
        cfg = dict(DEFAULTS)
        for section, prefix in (("general", ""), ("behavior", ""), ("cameras", ""),
                                ("notifications", ""), ("advanced", ""),
                                ("web", "api_"), ("battery", ""),
                                ("telemetry", "")):
            if section in result and isinstance(result[section], dict):
                # Flatten: web.host → api_host, notifications.enabled → notifications_enabled
                for k, v in result[section].items():
                    cfg[f"{prefix}{k}"] = v
        # Cameras come as list of dicts, not a dict
        if "cameras" in result and isinstance(result["cameras"], list):
            # Daemon returns list of CameraConfig objects (serialized as dicts)
            cfg["cameras"] = list(result["cameras"])
        return cfg

    # Fallback: direct YAML
    cfg = dict(DEFAULTS)
    cfg.update(_load_yaml(CONFIG_FILE))
    return cfg

def save_key(key: str, value: object) -> None:
    """Save single key: try IPC first, fallback to YAML."""
    # Try IPC
    section = _key_to_section(key)
    ipc_key = _key_to_ipc_key(key)
    result = _ipc_call("config.set", {"section": section, "key": ipc_key, "value": value})
    if result:
        return

    # Fallback: direct YAML
    cfg = _load_yaml(CONFIG_FILE)
    cfg[key] = value
    _save_yaml(CONFIG_FILE, cfg)

def _key_to_section(key: str) -> str:
    mapping = {
        "log_level": "general", "start_minimized": "general",
        "close_to_menu_bar": "general", "launch_at_login": "general",
        "confirm_quit": "general", "auto_update": "telemetry",
        "error_reporting": "telemetry",
        "pause_on_battery": "battery", "pause_when_away": "battery",
        "home_ssids": "battery",
        "api_host": "web", "api_port": "web",
        "notifications_enabled": "notifications",
        "notify_on_family": "notifications", "notify_on_unknown": "notifications",
        "notification_sound_family": "notifications",
        "notification_sound_alert": "notifications",
        "notification_dnd_start": "notifications",
        "notification_dnd_end": "notifications",
    }
    return mapping.get(key, "general")

def _key_to_ipc_key(key: str) -> str:
    """Strip section prefixes for flat YAML keys → IPC nested keys."""
    prefixes = {"notification_sound_": "", "notification_dnd_": "", "notifications_": "", "notify_on_": ""}
    for prefix, replacement in prefixes.items():
        if key.startswith(prefix) and prefix != "":
            return key[len(prefix):]
    return key

def save_cameras(cameras: list) -> None:
    """Save cameras list: try IPC, fallback YAML."""
    result = _ipc_call("config.set", {"section": "cameras", "key": "cameras", "value": cameras})
    if result:
        return
    cfg = _load_yaml(CONFIG_FILE)
    cfg["cameras"] = cameras
    _save_yaml(CONFIG_FILE, cfg)

def reload_config() -> None:
    _ipc_call("config.reload")

# ── macOS semantic colour palette ──────────────────────────────────────

def _mac_colors(dark: bool) -> dict:
    if dark:
        return {
            "window_bg": "#1e1e20", "toolbar_bg": "#262628",
            "toolbar_selected": "#3a3a3c", "toolbar_hover": "#323234",
            "separator": "#3a3a3c", "label_primary": "#f5f5f7",
            "label_secondary": "#98989d", "label_tertiary": "#6e6e73",
            "control_bg": "#2c2c2e", "control_active": "#0a84ff",
            "entry_bg": "#1c1c1e", "entry_border": "#48484a",
            "toggle_track_off": "#48484a", "toggle_track_on": "#0a84ff",
            "toggle_knob": "#ffffff", "destructive": "#ff453a",
            "success": "#30d158",
        }
    return {
        "window_bg": "#f5f5f7", "toolbar_bg": "#e8e8ec",
        "toolbar_selected": "#d1d1d6", "toolbar_hover": "#dddddf",
        "separator": "#c6c6c8", "label_primary": "#1d1d1f",
        "label_secondary": "#6e6e73", "label_tertiary": "#aeaeb2",
        "control_bg": "#ffffff", "control_active": "#007aff",
        "entry_bg": "#ffffff", "entry_border": "#c6c6c8",
        "toggle_track_off": "#aeaeb2", "toggle_track_on": "#34c759",
        "toggle_knob": "#ffffff", "destructive": "#ff3b30",
        "success": "#34c759",
    }

# ── tab definitions ────────────────────────────────────────────────────

TABS = [
    ("general",       "General",        "\u2699"),      # ⚙ gear
    ("streams",       "Streams",        "\u25B6"),      # ▶ play
    ("notifications", "Notifications",  "\u269D"),      # ⚝ outlined white star
    ("advanced",      "Advanced",       "\u2305"),      # ⌅ enter
]

# ────────────────────────────────────────────────────────────────────────
#  SettingsWindow
# ────────────────────────────────────────────────────────────────────────

class SettingsWindow:
    """macOS HIG – compliant preferences window with dual IPC/YAML backend."""

    def __init__(self) -> None:
        self._cfg = load_config()
        self._setup_root()
        self._detect_dark_mode()
        self._col = _mac_colors(self._dark)
        self._apply_window_theme()
        self._setup_dark_mode_notification()
        self._setup_signals()
        self._setup_keyboard()
        self._build_toolbar()
        self._build_content_area()
        self._select_tab("general")
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        (CONFIG_DIR / "settings.pid").write_text(str(os.getpid()))
        # Force immediate layout + paint for initial render
        self._root.update_idletasks()
        self._root.update()

    # ── window basics ───────────────────────────────────────────────

    def _setup_root(self) -> None:
        self._root = tk.Tk()
        self._root.title("Clairvoyant-Optics Settings")
        self._root.geometry("660x580")
        self._root.minsize(540, 420)
        self._root.resizable(True, True)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _detect_dark_mode(self) -> None:
        self._dark = False
        debug: list[str] = []

        # Strategy 0: Read GlobalPreferences plist directly (no subprocess, no imports)
        try:
            import plistlib
            plist_path = os.path.expanduser("~/Library/Preferences/.GlobalPreferences.plist")
            if os.path.exists(plist_path):
                with open(plist_path, "rb") as f:
                    prefs = plistlib.load(f)
                self._dark = prefs.get("AppleInterfaceStyle") == "Dark"
                debug.append(f"Strategy0(plistlib): dark={self._dark}")
                if self._dark:
                    self._force_tk_dark_mode()
                    self._write_debug("dark_mode", debug)
                    return
        except Exception as e:
            debug.append(f"Strategy0(plistlib): FAIL {e}")

        # Strategy 1: Tk isdark (requires realized window)
        try:
            self._root.update_idletasks()
            result = self._root.tk.call("::tk::unsupported::MacWindowStyle", "isdark", self._root)
            self._dark = bool(int(result))
            debug.append(f"Strategy1(Tk): dark={self._dark} result={result}")
            if self._dark:
                self._force_tk_dark_mode()
                self._write_debug("dark_mode", debug)
                return
        except Exception as e:
            debug.append(f"Strategy1(Tk): FAIL {e}")

        # Strategy 2: defaults command (full path for bundle env)
        try:
            import subprocess
            r = subprocess.run(
                ["/usr/bin/defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True, timeout=2,
            )
            self._dark = r.stdout.strip() == "Dark"
            debug.append(f"Strategy2(defaults): dark={self._dark} stdout={r.stdout.strip()!r} rc={r.returncode}")
            if self._dark:
                self._force_tk_dark_mode()
                self._write_debug("dark_mode", debug)
                return
        except Exception as e:
            debug.append(f"Strategy2(defaults): FAIL {e}")

        # Strategy 3: NSUserDefaults
        try:
            from Foundation import NSUserDefaults
            defaults = NSUserDefaults.standardUserDefaults()
            style = defaults.stringForKey_("AppleInterfaceStyle")
            debug.append(f"Strategy3(NSUserDefaults): style={style!r}")
            if style:
                self._dark = style == "Dark"
                self._force_tk_dark_mode()
                self._write_debug("dark_mode", debug)
                return
        except Exception as e:
            debug.append(f"Strategy3(NSUserDefaults): FAIL {e}")

        # Strategy 4: PyObjC effectiveAppearance (last resort)
        try:
            from AppKit import NSApp
            if NSApp is not None:
                name = NSApp.effectiveAppearance().bestMatchFromAppearancesWithNames_([
                    "NSAppearanceNameAqua",
                    "NSAppearanceNameDarkAqua",
                ])
                self._dark = name == "NSAppearanceNameDarkAqua"
                debug.append(f"Strategy4(NSApp): dark={self._dark} name={name!r}")
                if self._dark:
                    self._force_tk_dark_mode()
        except Exception as e:
            debug.append(f"Strategy4(NSApp): FAIL {e}")

        self._write_debug("dark_mode", debug)

    def _force_tk_dark_mode(self) -> None:
        """Force Tk to use NSAppearanceNameDarkAqua — bg colors alone aren't enough."""
        try:
            self._root.tk.call(
                "::tk::unsupported::MacWindowStyle", "appearance",
                self._root, "dark", "dark",
            )
        except Exception:
            pass

    def _write_debug(self, key: str, lines: list[str]) -> None:
        try:
            log_path = CONFIG_DIR / "settings-debug.log"
            import datetime
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            with open(log_path, "a") as f:
                f.write(f"[{stamp}] {key}:\n")
                for line in lines:
                    f.write(f"  {line}\n")
                f.write("\n")
        except Exception:
            pass

    def _apply_window_theme(self) -> None:
        self._root.configure(bg=self._col["window_bg"])

    def _setup_dark_mode_notification(self) -> None:
        """Listen for system dark/light mode changes while Settings is open."""
        try:
            from Foundation import (
                NSDistributedNotificationCenter,
                NSObject,
                objc,
            )
            class DarkModeObserver(NSObject):
                def onThemeChanged_(self, notification):
                    self._callback()

            observer = DarkModeObserver.alloc().init()
            observer._callback = self._on_system_theme_changed
            center = NSDistributedNotificationCenter.defaultCenter()
            center.addObserver_selector_name_object_(
                observer,
                "onThemeChanged:",
                "AppleInterfaceThemeChangedNotification",
                None,
            )
            self._dm_observer = observer  # keep alive
        except Exception:
            self._dm_observer = None

    def _on_system_theme_changed(self) -> None:
        """Rebuild UI when system dark mode toggles — schedule on Tk main thread.

        NSDistributedNotificationCenter fires on a background thread.
        Tk is NOT thread-safe — all widget mutations MUST go through after().
        """
        self._root.after(0, self._do_theme_changed)

    def _do_theme_changed(self) -> None:
        """Run on Tk main thread: re-detect theme, rebuild UI."""
        self._detect_dark_mode()
        self._col = _mac_colors(self._dark)
        self._apply_window_theme()
        self._rebuild_ui()

    def _rebuild_ui(self) -> None:
        """Rebuild toolbar + current tab with new colors."""
        # Rebuild toolbar
        self._toolbar.destroy()
        self._build_toolbar()
        # Rebuild content with same active tab
        self._content_frame.destroy()
        self._build_content_area()
        active = getattr(self, "_active_tab", "general")
        self._select_tab(active)
        # Force immediate layout + paint — otherwise widgets stay invisible
        # until mouse moves from toolbar to content area on macOS Sequoia.
        self._root.update_idletasks()
        self._root.update()

    def _mac_button(self, parent: tk.Frame, text: str, command,
                    style: str = "primary", font_size: int = 13,
                    bold: bool = True, padx: int = 24, pady: int = 8) -> tk.Frame:
        """Label-based button — tk.Button doesn't honour bg in macOS dark mode."""
        c = self._col
        if style == "primary":
            bg_color = c["control_active"]
            fg_color = "#ffffff"
        elif style == "destructive":
            bg_color = c["destructive"]
            fg_color = "#ffffff"
        else:
            bg_color = c["control_bg"]
            fg_color = c["label_primary"]

        font_style = ("SF Pro Text", font_size, "bold") if bold else ("SF Pro Text", font_size)
        btn_frame = tk.Frame(parent, bg=parent["bg"], cursor="hand2")
        inner = tk.Frame(btn_frame, bg=bg_color,
                         highlightbackground=c.get("entry_border", bg_color),
                         highlightthickness=0)
        inner.pack()
        lbl = tk.Label(inner, text=text, font=font_style,
                       fg=fg_color, bg=bg_color,
                       padx=padx, pady=pady, cursor="hand2")
        lbl.pack()

        def _on_enter(e):
            if style == "primary":
                inner.configure(bg=c["control_active"])
                lbl.configure(bg=c["control_active"])
            elif style == "destructive":
                inner.configure(bg=c["destructive"])
                lbl.configure(bg=c["destructive"])

        def _on_click(e):
            command()

        for w in (btn_frame, inner, lbl):
            w.bind("<Button-1>", _on_click)
            w.bind("<Enter>", _on_enter)
        return btn_frame

    def _show(self) -> None:
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()

    # ── signals ────────────────────────────────────────────────────

    def _setup_signals(self) -> None:
        signal.signal(signal.SIGUSR1, lambda s, f: self._root.after(0, self._show))
        def _term(signum, frame):
            (CONFIG_DIR / "settings.pid").unlink(missing_ok=True)
            try:
                self._root.destroy()
            except Exception:
                pass
            sys.exit(0)
        signal.signal(signal.SIGTERM, _term)

    # ── keyboard ────────────────────────────────────────────────────

    def _setup_keyboard(self) -> None:
        self._root.bind("<Escape>", lambda e: self._on_close())
        self._root.bind("<Command-,>", lambda e: self._on_close())
        self._root.bind("<Command-.>", lambda e: self._on_close())
        self._root.bind("<Command-w>", lambda e: self._on_close())

    def _on_close(self) -> None:
        # Always quit on window close — prevents ghost lingering in dock
        self._quit()

    def _quit(self) -> None:
        (CONFIG_DIR / "settings.pid").unlink(missing_ok=True)
        try:
            self._root.destroy()
        except Exception:
            pass
        sys.exit(0)

    def _show_confirm_quit(self) -> None:
        c = self._col
        top = tk.Toplevel(self._root, bg=c["window_bg"])
        top.title("")
        top.resizable(False, False)
        top.transient(self._root)
        top.grab_set()
        top.geometry("320x140")
        top.update_idletasks()
        px, py = self._root.winfo_x(), self._root.winfo_y()
        pw, ph = self._root.winfo_width(), self._root.winfo_height()
        tw, th = top.winfo_width(), top.winfo_height()
        top.geometry(f"+{px + (pw - tw)//2}+{py + (ph - th)//2}")

        frm = tk.Frame(top, bg=c["window_bg"], padx=20, pady=20)
        frm.pack(expand=True, fill="both")
        tk.Label(frm, text="Quit Clairvoyant-Optics?",
                 font=("SF Pro Text", 13, "bold"), fg=c["label_primary"],
                 bg=c["window_bg"]).pack(anchor="w")
        tk.Label(frm, text="The application will stop monitoring cameras.",
                 font=("SF Pro Text", 11), fg=c["label_secondary"],
                 bg=c["window_bg"]).pack(anchor="w", pady=(4, 16))

        btn_row = tk.Frame(frm, bg=c["window_bg"])
        btn_row.pack(anchor="e")
        cancel_btn = self._mac_button(btn_row, "Cancel", top.destroy, style="default", font_size=12, padx=16, pady=4)
        cancel_btn.pack(side="left", padx=(0, 8))
        quit_btn = self._mac_button(btn_row, "Quit", lambda: [top.destroy(), self._quit()], style="destructive", font_size=12, padx=16, pady=4)
        quit_btn.pack(side="left")

    # ── toolbar ─────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        c = self._col
        self._toolbar = tk.Frame(
            self._root, bg=c["toolbar_bg"], width=170, height=580,
        )
        self._toolbar.pack(side="left", fill="y")
        self._toolbar.pack_propagate(False)

        hdr = tk.Frame(self._toolbar, bg=c["toolbar_bg"], pady=18)
        hdr.pack(fill="x")
        tk.Label(hdr, text="\U0001F441", font=("SF Pro Text", 20),
                 bg=c["toolbar_bg"], fg=c["label_primary"]).pack()
        tk.Label(hdr, text="Clairvoyant-Optics",
                 font=("SF Pro Text", 11, "bold"),
                 bg=c["toolbar_bg"], fg=c["label_primary"]).pack(pady=(2, 0))

        sep = tk.Frame(self._toolbar, bg=c["separator"], height=1)
        sep.pack(fill="x", padx=14, pady=(10, 4))

        self._tab_buttons: dict[str, tk.Frame] = {}
        for tab_id, label, icon in TABS:
            btn = tk.Frame(self._toolbar, bg=c["toolbar_bg"],
                           padx=12, pady=6, cursor="hand2")
            btn.pack(fill="x")
            icon_lbl = tk.Label(btn, text=icon, font=("SF Pro Text", 14),
                                bg=c["toolbar_bg"], fg=c["label_secondary"])
            icon_lbl.pack(side="left", padx=(4, 8))
            text_lbl = tk.Label(btn, text=label,
                                font=("SF Pro Text", 12),
                                bg=c["toolbar_bg"], fg=c["label_secondary"])
            text_lbl.pack(side="left")
            for w in (btn, icon_lbl, text_lbl):
                w.bind("<Button-1>", lambda e, tid=tab_id: self._select_tab(tid))
                w.bind("<Enter>", lambda e, f=btn: f.configure(bg=c["toolbar_hover"]))
                w.bind("<Leave>", lambda e, f=btn, tid=tab_id:
                       f.configure(bg=c["toolbar_selected"] if self._active_tab == tid else c["toolbar_bg"]))
            self._tab_buttons[tab_id] = btn
            btn._icon = icon_lbl
            btn._text = text_lbl

        bot = tk.Frame(self._toolbar, bg=c["toolbar_bg"])
        bot.pack(side="bottom", fill="x", pady=12)
        tk.Label(bot, text=f"v{VERSION}", font=("SF Pro Text", 10),
                 bg=c["toolbar_bg"], fg=c["label_tertiary"]).pack()

    def _select_tab(self, tab_id: str) -> None:
        c = self._col
        self._active_tab = tab_id
        for tid, btn in self._tab_buttons.items():
            active = tid == tab_id
            btn.configure(bg=c["toolbar_selected"] if active else c["toolbar_bg"])
            btn._icon.configure(bg=btn["bg"],
                                fg=c["label_primary"] if active else c["label_secondary"])
            btn._text.configure(bg=btn["bg"],
                                fg=c["label_primary"] if active else c["label_secondary"])
        self._show_content(tab_id)

    # ── content area ────────────────────────────────────────────────────

    def _build_content_area(self) -> None:
        c = self._col
        self._content_frame = tk.Frame(self._root, bg=c["window_bg"])
        self._content_frame.pack(side="left", fill="both", expand=True)
        self._pages: dict[str, tk.Frame] = {}
        for tab_id, _, _ in TABS:
            page = tk.Frame(self._content_frame, bg=c["window_bg"])
            self._pages[tab_id] = page

    def _show_content(self, tab_id: str) -> None:
        for page in self._pages.values():
            page.pack_forget()
        page = self._pages[tab_id]
        page.pack(fill="both", expand=True, padx=2, pady=2)
        _clear_frame(page)
        getattr(self, f"_build_{tab_id}")(page)
        # Force immediate paint — on macOS Sequoia WindowServer defers
        # widget rendering until next user interaction without this.
        self._root.update_idletasks()
        self._root.update()

    # ── tab: General ────────────────────────────────────────────────────

    def _build_general(self, parent: tk.Frame) -> None:
        c = self._col
        self._section_header(parent, "General", "Application & API preferences")
        sf = self._section(parent)
        self._labeled_option(sf, "Log Level",
                             self._cfg.get("log_level", "INFO"),
                             ["DEBUG", "INFO", "WARNING", "ERROR"],
                             lambda v: self._set("log_level", v))
        self._mac_toggle(sf, "Launch at Login",
                         "Start automatically when you log in", "launch_at_login")

        # API server
        self._section_header(parent, "API Server", "Web dashboard & REST API", pad_top=24)
        api_sf = self._section(parent)
        api_host_var = tk.StringVar(value=self._cfg.get("api_host", "127.0.0.1"))
        api_port_var = tk.StringVar(value=str(self._cfg.get("api_port", 8765)))
        self._api_status_var = tk.StringVar(value="")

        self._api_debounce_id: str | None = None

        row1 = tk.Frame(api_sf, bg=c["window_bg"])
        row1.pack(fill="x", pady=(6, 0))
        tk.Label(row1, text="Host", font=("SF Pro Text", 12),
                 fg=c["label_secondary"], bg=c["window_bg"]).pack(side="left")
        host_ent = tk.Entry(row1, textvariable=api_host_var,
                            bg=c["entry_bg"], fg=c["label_primary"],
                            insertbackground=c["label_primary"],
                            font=("SF Mono", 12),
                            relief="flat", bd=0,
                            highlightbackground=c["entry_border"],
                            highlightcolor=c["control_active"],
                            highlightthickness=1)
        host_ent.pack(side="right", ipadx=6, ipady=4)

        row2 = tk.Frame(api_sf, bg=c["window_bg"])
        row2.pack(fill="x", pady=(6, 0))
        tk.Label(row2, text="Port", font=("SF Pro Text", 12),
                 fg=c["label_secondary"], bg=c["window_bg"]).pack(side="left")
        port_ent = tk.Entry(row2, textvariable=api_port_var,
                            bg=c["entry_bg"], fg=c["label_primary"],
                            insertbackground=c["label_primary"],
                            font=("SF Mono", 12),
                            relief="flat", bd=0,
                            highlightbackground=c["entry_border"],
                            highlightcolor=c["control_active"],
                            highlightthickness=1)
        port_ent.pack(side="right", ipadx=6, ipady=4)

        # Status label — auto-updates via trace debounce
        status_lbl = tk.Label(api_sf, textvariable=self._api_status_var,
                              font=("SF Pro Text", 11),
                              bg=c["window_bg"], fg=c["label_secondary"])
        status_lbl.pack(anchor="w", pady=(6, 0))

        # Hot reload: trace_add on both fields with 800ms debounce
        api_host_var.trace_add("write",
            lambda *a, hv=api_host_var, pv=api_port_var:
                self._schedule_api_validation(hv.get(), pv.get()))
        api_port_var.trace_add("write",
            lambda *a, hv=api_host_var, pv=api_port_var:
                self._schedule_api_validation(hv.get(), pv.get()))

        # Initial validation (without saving)
        self._api_status_var.set("✓ Settings loaded from config")

    def _schedule_api_validation(self, host: str, port_str: str) -> None:
        """Debounce API validation — fires 800ms after last keystroke."""
        if self._api_debounce_id is not None:
            self._root.after_cancel(self._api_debounce_id)
        self._api_debounce_id = self._root.after(
            800, lambda: self._validate_api_settings(host, port_str))

    def _validate_api_settings(self, host: str, port_str: str) -> None:
        """Validate API host/port and save on success."""
        try:
            port = int(port_str)
        except ValueError:
            self._api_status_var.set("❌ Port must be a number (1–65535)")
            return

        if not host.strip():
            self._api_status_var.set("❌ Host cannot be empty")
            return
        if port < 1 or port > 65535:
            self._api_status_var.set("❌ Port must be between 1–65535")
            return

        # Try binding to check availability
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            s.bind((host, port))
            s.close()
        except socket.error as e:
            self._api_status_var.set(f"❌ {host}:{port} — {e.strerror}")
            return

        # Save via IPC
        self._set("api_host", host)
        self._set("api_port", port)
        self._api_status_var.set(f"✅ {host}:{port} — saved")

    # ── tab: Streams ────────────────────────────────────────────────────

    def _build_streams(self, parent: tk.Frame) -> None:
        c = self._col
        self._section_header(parent, "Streams", "Manage camera feeds")
        cameras: list = self._cfg.get("cameras", [])
        if not cameras:
            self._streams_empty_state(parent)
        else:
            list_frame = tk.Frame(parent, bg=c["window_bg"], padx=20)
            list_frame.pack(fill="both", expand=True, pady=(4, 0))
            for i, cam in enumerate(cameras):
                self._build_camera_card(list_frame, i, cam)

        add_btn = self._mac_button(
            parent, "+ Add Camera", self._add_camera_from_streams,
            style="primary",
        )
        add_btn.pack(pady=(14, 20))

    def _build_camera_card(self, parent: tk.Frame, idx: int, cam: dict) -> None:
        c = self._col
        card = tk.Frame(parent, bg=c["control_bg"], bd=0,
                        highlightbackground=c["entry_border"],
                        highlightthickness=1)
        card.pack(fill="x", pady=(0, 10), ipadx=4, ipady=4)

        hdr = tk.Frame(card, bg=c["control_bg"])
        hdr.pack(fill="x", padx=12, pady=(10, 4))
        name = cam.get("name", f"Camera {idx + 1}")
        name_var = tk.StringVar(value=name)
        name_ent = tk.Entry(
            hdr, textvariable=name_var,
            font=("SF Pro Text", 14, "bold"),
            bg=c["control_bg"], fg=c["label_primary"],
            insertbackground=c["label_primary"],
            relief="flat", bd=0, highlightthickness=0,
        )
        name_ent.pack(side="left", fill="x", expand=True)
        name_var.trace_add("write", lambda *a, i=idx, v=name_var: self._update_camera_field(i, "name", v.get()))
        name_ent.bind("<FocusOut>", lambda e, i=idx, v=name_var: self._update_camera_field(i, "name", v.get()))
        name_ent.bind("<Return>", lambda e, i=idx, v=name_var: self._update_camera_field(i, "name", v.get()))

        rm_frame = self._mac_button(
            hdr, "\u2715", lambda i=idx: self._remove_camera(i),
            style="default", font_size=12, padx=6, pady=0,
        )
        rm_frame.pack(side="right")

        sep = tk.Frame(card, bg=c["entry_border"], height=1)
        sep.pack(fill="x", padx=12)

        fields_frame = tk.Frame(card, bg=c["control_bg"])
        fields_frame.pack(fill="x", padx=12, pady=(8, 12))
        self._camera_field(fields_frame, "Stream URL", "stream_url", cam.get("stream_url", ""), idx)
        self._camera_field(fields_frame, "Snap URL", "snap_url", cam.get("snap_url", ""), idx)

    def _camera_field(self, parent: tk.Frame, label: str, field: str, value: str, idx: int) -> None:
        c = self._col
        tk.Label(parent, text=label, font=("SF Pro Text", 10, "bold"),
                 fg=c["label_secondary"], bg=c["control_bg"]).pack(anchor="w", pady=(6, 2))
        var = tk.StringVar(value=value)
        ent = tk.Entry(
            parent, textvariable=var, font=("SF Mono", 11),
            bg=c["entry_bg"], fg=c["label_primary"],
            insertbackground=c["label_primary"],
            relief="flat", bd=0,
            highlightbackground=c["entry_border"],
            highlightcolor=c["control_active"],
            highlightthickness=1,
        )
        ent.pack(fill="x", ipady=5)
        ent.bind("<FocusOut>", lambda e, i=idx, f=field, v=var: self._update_camera_field(i, f, v.get()))
        ent.bind("<Return>", lambda e, i=idx, f=field, v=var: self._update_camera_field(i, f, v.get()))

    def _streams_empty_state(self, parent: tk.Frame) -> None:
        c = self._col
        ph = tk.Frame(parent, bg=c["window_bg"])
        ph.place(relx=0.5, rely=0.38, anchor="center")
        tk.Label(ph, text="No Cameras", font=("SF Pro Text", 16, "bold"),
                 fg=c["label_secondary"], bg=c["window_bg"]).pack()
        tk.Label(ph, text="Add a camera stream to start monitoring.",
                 font=("SF Pro Text", 12),
                 fg=c["label_tertiary"], bg=c["window_bg"]).pack(pady=(4, 0))

    def _add_camera_from_streams(self) -> None:
        cameras = self._cfg.get("cameras", [])
        cameras.append({"name": f"Camera {len(cameras) + 1}", "stream_url": "", "snap_url": ""})
        self._cfg["cameras"] = cameras
        save_cameras(cameras)
        self._refresh_streams_tab()

    def _remove_camera(self, idx: int) -> None:
        cameras = self._cfg.get("cameras", [])
        if 0 <= idx < len(cameras):
            cameras.pop(idx)
        self._cfg["cameras"] = cameras
        save_cameras(cameras)
        self._refresh_streams_tab()

    def _refresh_streams_tab(self) -> None:
        """Rebuild streams tab only if it's currently visible."""
        if getattr(self, "_active_tab", None) == "streams":
            self._select_tab("streams")

    def _update_camera_field(self, idx: int, field: str, value: str) -> None:
        cameras = self._cfg.get("cameras", [])
        if 0 <= idx < len(cameras):
            cameras[idx][field] = value
            self._cfg["cameras"] = cameras
            save_cameras(cameras)

    # ── tab: Notifications ──────────────────────────────────────────────

    def _build_notifications(self, parent: tk.Frame) -> None:
        c = self._col
        self._section_header(parent, "Notifications", "Alerts and sounds")
        sf = self._section(parent)
        self._mac_toggle(sf, "Enable Notifications",
                         "Show macOS notifications for detected persons", "notifications_enabled")
        self._mac_toggle(sf, "Notify on Family Members",
                         "Notify when a known family member is detected", "notify_on_family")
        self._mac_toggle(sf, "Notify on Unknown Persons",
                         "Alert when an unknown person is detected", "notify_on_unknown")

        sf2 = self._section(parent, "Sounds")
        sounds = ["default", "alarm", "basso", "blow", "bottle", "frog",
                  "funk", "glass", "hero", "morse", "ping", "pop",
                  "purr", "sosumi", "submarine", "tink"]
        self._labeled_option(sf2, "Family Member Sound",
                             self._cfg.get("notification_sound_family", "default"),
                             sounds, lambda v: self._set("notification_sound_family", v))
        self._labeled_option(sf2, "Unknown Person Alert",
                             self._cfg.get("notification_sound_alert", "alarm"),
                             sounds, lambda v: self._set("notification_sound_alert", v))

        sf3 = self._section(parent, "Do Not Disturb Schedule")
        self._labeled_entry(sf3, "Start (HH:MM)",
                            self._cfg.get("notification_dnd_start", ""),
                            lambda v: self._set("notification_dnd_start", v))
        self._labeled_entry(sf3, "End (HH:MM)",
                            self._cfg.get("notification_dnd_end", ""),
                            lambda v: self._set("notification_dnd_end", v))

    # ── tab: Advanced ───────────────────────────────────────────────────

    def _build_advanced(self, parent: tk.Frame) -> None:
        c = self._col
        self._section_header(parent, "Advanced", "Updates, power & networking")
        sf = self._section(parent)
        self._mac_toggle(sf, "Auto-Update",
                         "Check for updates every 6 hours", "auto_update")
        self._mac_toggle(sf, "Error Reporting",
                         "Send error reports to GitHub Issues automatically", "error_reporting")
        self._mac_toggle(sf, "Pause When on Battery",
                         "Pause recognition on battery power", "pause_on_battery")
        self._mac_toggle(sf, "Pause When Away from Home",
                         "Pause when not connected to home WiFi", "pause_when_away")

        sf2 = self._section(parent, "Home WiFi")
        self._labeled_entry(sf2, "SSIDs (comma-separated)",
                            self._cfg.get("home_ssids", ""),
                            lambda v: self._set("home_ssids", v))

        # ── Test Notifications (v5.2.0) ─────────────────────────────
        self._section_header(parent, "Test Notifications", "Verify alert delivery", pad_top=24)
        test_sf = self._section(parent)
        test_row = tk.Frame(test_sf, bg=c["window_bg"])
        test_row.pack(fill="x", pady=(8, 0))

        test_family_btn = self._mac_button(
            test_row, "Test Notification",
            self._test_family_notification, style="primary", padx=12, pady=4,
        )
        test_family_btn.pack(side="left", padx=(0, 12))

        test_alert_btn = self._mac_button(
            test_row, "Test Alert",
            self._test_alert_notification, style="destructive", padx=12, pady=4,
        )
        test_alert_btn.pack(side="left")

        self._test_status_var = tk.StringVar(value="")
        tk.Label(test_sf, textvariable=self._test_status_var,
                 font=("SF Pro Text", 11),
                 bg=c["window_bg"], fg=c["label_secondary"]).pack(anchor="w", pady=(8, 0))

    def _send_test_notification(self, title: str, subtitle: str, message: str) -> None:
        """Send a macOS notification or notify via IPC daemon."""
        # Try IPC: call daemon to send notification
        result = _ipc_call("config.get", {"section": "notifications"})
        if result:
            # IPC daemon available — use test_notify IPC method if available
            test_resp = _ipc_call("test_notify", {
                "title": title, "subtitle": subtitle, "message": message,
            })
            if test_resp:
                self._test_status_var.set("✅ Notification sent via daemon")
                return

        # Fallback: use rumps or subprocess osascript
        try:
            import subprocess
            script = f'''
            display notification "{message}" with title "{title}" subtitle "{subtitle}" sound name "default"
            '''
            subprocess.run(["osascript", "-e", script], timeout=3, check=False)
            self._test_status_var.set("✅ Notification sent")
        except Exception as e:
            self._test_status_var.set(f"❌ Failed: {e}")

    def _test_family_notification(self) -> None:
        self._send_test_notification(
            "Clairvoyant-Optics",
            "Family Member Detected",
            "👤 Pomo detected on Camera 1",
        )

    def _test_alert_notification(self) -> None:
        self._send_test_notification(
            "Clairvoyant-Optics",
            "⚠ Unknown Person Alert",
            "Unknown person detected on Camera 1!",
        )

    # ── reusable UI primitives ──────────────────────────────────────────

    def _section_header(self, parent: tk.Frame, title: str, subtitle: str = "",
                        pad_top: int = 20) -> None:
        c = self._col
        hdr = tk.Frame(parent, bg=c["window_bg"], padx=20)
        hdr.pack(fill="x", pady=(pad_top, 2))
        tk.Label(hdr, text=title, font=("SF Pro Text", 22, "bold"),
                 fg=c["label_primary"], bg=c["window_bg"]).pack(anchor="w")
        if subtitle:
            tk.Label(hdr, text=subtitle, font=("SF Pro Text", 13),
                     fg=c["label_secondary"], bg=c["window_bg"]).pack(anchor="w", pady=(2, 0))

    def _section(self, parent: tk.Frame, label: str = "") -> tk.Frame:
        c = self._col
        sf = tk.Frame(parent, bg=c["window_bg"], padx=20, pady=4)
        sf.pack(fill="x")
        if label:
            tk.Label(sf, text=label, font=("SF Pro Text", 11, "bold"),
                     fg=c["label_secondary"], bg=c["window_bg"]).pack(anchor="w", pady=(12, 4))
        return sf

    def _mac_toggle(self, parent: tk.Frame, title: str, subtitle: str, key: str) -> None:
        c = self._col
        row = tk.Frame(parent, bg=c["window_bg"])
        row.pack(fill="x", pady=(10, 0))
        left = tk.Frame(row, bg=c["window_bg"])
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=title, font=("SF Pro Text", 13),
                 fg=c["label_primary"], bg=c["window_bg"]).pack(anchor="w")
        tk.Label(left, text=subtitle, font=("SF Pro Text", 11),
                 fg=c["label_secondary"], bg=c["window_bg"]).pack(anchor="w", pady=(1, 0))
        var = tk.BooleanVar(value=bool(self._cfg.get(key)))
        cb = tk.Checkbutton(
            row, variable=var,
            command=lambda k=key, v=var: self._set(k, v.get()),
            bg=c["window_bg"], fg=c["label_primary"],
            selectcolor=c["window_bg"],
            activebackground=c["window_bg"],
            activeforeground=c["label_primary"],
            font=("SF Pro Text", 13), bd=0, highlightthickness=0,
        )
        cb.pack(side="right", padx=(16, 0))

    def _labeled_option(self, parent: tk.Frame, label: str,
                        value: str, choices: list[str], callback) -> None:
        c = self._col
        row = tk.Frame(parent, bg=c["window_bg"])
        row.pack(fill="x", pady=(8, 0))
        tk.Label(row, text=label, font=("SF Pro Text", 12),
                 fg=c["label_secondary"], bg=c["window_bg"]).pack(side="left")
        var = tk.StringVar(value=value)
        menu = tk.OptionMenu(row, var, *choices, command=lambda v, cb=callback: cb(v))
        menu.configure(bg=c["entry_bg"], fg=c["label_primary"],
                       activebackground=c["toolbar_selected"],
                       activeforeground=c["label_primary"],
                       font=("SF Pro Text", 12),
                       relief="flat", bd=0, highlightthickness=0)
        menu["menu"].configure(bg=c["entry_bg"], fg=c["label_primary"],
                               font=("SF Pro Text", 12))
        menu.pack(side="right")

    def _labeled_entry(self, parent: tk.Frame, label: str, value: str, callback) -> None:
        c = self._col
        row = tk.Frame(parent, bg=c["window_bg"])
        row.pack(fill="x", pady=(8, 0))
        tk.Label(row, text=label, font=("SF Pro Text", 12),
                 fg=c["label_secondary"], bg=c["window_bg"]).pack(side="left")
        var = tk.StringVar(value=value)
        ent = tk.Entry(row, textvariable=var,
                       bg=c["entry_bg"], fg=c["label_primary"],
                       insertbackground=c["label_primary"],
                       font=("SF Mono", 12),
                       relief="flat", bd=0,
                       highlightbackground=c["entry_border"],
                       highlightcolor=c["control_active"],
                       highlightthickness=1)
        ent.pack(side="right", ipadx=6, ipady=4)
        ent.bind("<FocusOut>", lambda e, cb=callback, v=var: cb(v.get()))
        ent.bind("<Return>", lambda e, cb=callback, v=var: cb(v.get()))

    # ── config mutation ─────────────────────────────────────────────────

    def _set(self, key: str, value) -> None:
        self._cfg[key] = value
        save_key(key, value)
        if key == "launch_at_login":
            self._manage_launch_agent(bool(value))
        self._notify_app_if_needed(key)

    def _manage_launch_agent(self, enable: bool) -> None:
        """Create or remove LaunchAgent plist for login auto-start."""
        import plistlib
        import subprocess

        launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
        plist_path = launch_agents_dir / "fi.kaikkonen.clairvoyantd.plist"

        if enable:
            launch_agents_dir.mkdir(parents=True, exist_ok=True)
            if IS_BUNDLED:
                app_exec = str(BUNDLE_DIR.parent / "MacOS" / "Clairvoyant-Optics")  # type: ignore[union-attr]
            else:
                app_exec = sys.executable
            plist_data = {
                "Label": "fi.kaikkonen.clairvoyantd",
                "ProgramArguments": [app_exec, "--daemon"],
                "RunAtLoad": True,
                "KeepAlive": False,
            }
            with open(plist_path, "wb") as f:
                plistlib.dump(plist_data, f)
            # Load it
            subprocess.run(
                ["launchctl", "load", str(plist_path)],
                capture_output=True, timeout=3, check=False,
            )
        else:
            # Unload and remove
            if plist_path.exists():
                subprocess.run(
                    ["launchctl", "unload", str(plist_path)],
                    capture_output=True, timeout=3, check=False,
                )
                plist_path.unlink(missing_ok=True)

    def _notify_app_if_needed(self, key: str) -> None:
        if key != "launch_at_login":
            return
        try:
            app_pid_file = CONFIG_DIR / "app.pid"
            if app_pid_file.exists():
                pid = int(app_pid_file.read_text().strip())
                os.kill(pid, signal.SIGUSR2)
        except Exception:
            pass


# ── helpers ─────────────────────────────────────────────────────────────

def _clear_frame(frame: tk.Frame) -> None:
    for w in frame.winfo_children():
        w.destroy()


# ── main ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    window = SettingsWindow()
    window._root.mainloop()
