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

VERSION = "5.6.0"

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
    "launch_at_login": False,
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
    "api_enabled": False,
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
            with open(path) as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}

def _save_yaml(path: Path, data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import yaml
        with open(path, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
    except Exception:
        with open(path, "w") as f:
            for k, v in data.items():
                f.write(f"{k}: {v}\n")

def load_config() -> dict:
    """Load config: try IPC first, fallback to YAML."""
    result = _ipc_call("config.get")
    if result and isinstance(result, dict):
        cfg = dict(DEFAULTS)
        # Reverse-map: daemon field name → UI flat key (per section)
        _daemon_to_flat = {
            "dnd_start": "notification_dnd_start",
            "dnd_end": "notification_dnd_end",
            "sound_family": "notification_sound_family",
            "sound_alert": "notification_sound_alert",
        }
        for section, prefix in (("general", ""), ("behavior", ""), ("cameras", ""),
                                ("notifications", ""), ("advanced", ""),
                                ("web", "api_"), ("battery", ""),
                                ("telemetry", "")):
            if section in result and isinstance(result[section], dict):
                for k, v in result[section].items():
                    # Check for section-specific reverse-map
                    if section == "notifications" and k in _daemon_to_flat:
                        cfg[_daemon_to_flat[k]] = v
                    elif k == "enabled" and section == "notifications":
                        cfg["notifications_enabled"] = v
                    elif k == "enabled" and section == "web":
                        cfg["api_enabled"] = v
                    else:
                        flat_key = f"{prefix}{k}"
                        cfg[flat_key] = _daemon_to_settings_value(section, k, v)
        # Cameras come as list of dicts, not a dict
        if "cameras" in result and isinstance(result["cameras"], list):
            cfg["cameras"] = list(result["cameras"])
        return cfg

    # Fallback: direct YAML
    cfg = dict(DEFAULTS)
    cfg.update(_load_yaml(CONFIG_FILE))
    return cfg

# ── Daemon ↔ Settings key/value mapping ─────────────────────────────

def _settings_key_to_daemon(key: str, value: object) -> tuple[str, str, object]:
    """Convert a settings flat key to (section, daemon_key, coerced_value) for IPC/YAML.

    Handles key translation, section mapping, and type coercion (e.g. home_ssids string→list).
    """
    section = _key_to_section(key)
    ipc_key = _key_to_ipc_key(key)

    # Type coercion for daemon dataclass field types
    if ipc_key == "home_ssids" and isinstance(value, str):
        # UI stores as comma-separated string, daemon expects list[str]
        value = [s.strip() for s in value.split(",") if s.strip()]
    elif ipc_key == "port" and isinstance(value, str):
        try:
            value = int(value)
        except ValueError:
            pass

    return section, ipc_key, value


def _daemon_to_settings_value(section: str, daemon_key: str, value: object) -> object:
    """Convert daemon field value back to settings UI flat value.

    Handles type coercion (e.g. home_ssids list→string for Entry widget).
    """
    if daemon_key == "home_ssids" and isinstance(value, list):
        return ", ".join(str(s) for s in value)
    return value


def save_key(key: str, value: object) -> None:
    """Save single key: try IPC first, fallback to section-aware YAML."""
    section, ipc_key, coerced = _settings_key_to_daemon(key, value)

    # Try IPC
    result = _ipc_call("config.set", {"section": section, "key": ipc_key, "value": coerced})
    if result:
        return

    # Fallback: section-aware YAML write (not flat root!)
    cfg = _load_yaml(CONFIG_FILE)
    if section not in cfg or not isinstance(cfg[section], dict):
        cfg[section] = {}
    cfg[section][ipc_key] = coerced
    _save_yaml(CONFIG_FILE, cfg)

def _key_to_section(key: str) -> str:
    mapping = {
        "log_level": "general", "launch_at_login": "general",
        "auto_update": "telemetry",
        "error_reporting": "telemetry",
        "pause_on_battery": "battery", "pause_when_away": "battery",
        "home_ssids": "battery",
        "battery_poll_interval": "battery",
        "api_host": "web", "api_port": "web", "api_enabled": "web",
        "notifications_enabled": "notifications",
        "notify_on_family": "notifications", "notify_on_unknown": "notifications",
        "notification_sound_family": "notifications",
        "notification_sound_alert": "notifications",
        "notification_dnd_start": "notifications",
        "notification_dnd_end": "notifications",
        "mqtt_enabled": "mqtt",
        "mqtt_broker": "mqtt",
        "mqtt_port": "mqtt",
        "mqtt_username": "mqtt",
        "mqtt_password": "mqtt",
        "mqtt_topic_prefix": "mqtt",
    }
    return mapping.get(key, "general")

def _key_to_ipc_key(key: str) -> str:
    """Map flat settings keys to daemon IPC keys (dataclass field names).

    Daemon config_store.py uses specific field names per section.
    This mapping decouples the Settings UI key namespace from daemon internals.
    """
    mapping: dict[str, str] = {
        # notifications section
        "notifications_enabled": "enabled",
        "notify_on_family": "notify_on_family",
        "notify_on_unknown": "notify_on_unknown",
        "notification_sound_family": "sound_family",
        "notification_sound_alert": "sound_alert",
        "notification_dnd_start": "dnd_start",
        "notification_dnd_end": "dnd_end",
        # web section (api_ prefix → daemon host/port)
        "api_host": "host",
        "api_port": "port",
        "api_enabled": "enabled",
        # battery section
        "home_ssids": "home_ssids",
        "pause_on_battery": "pause_on_battery",
        "pause_when_away": "pause_when_away",
        # telemetry section
        "auto_update": "auto_update",
        "error_reporting": "error_reporting",
        # general section
        "log_level": "log_level",
        "launch_at_login": "launch_at_login",
    }
    return mapping.get(key, key)

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
    ("models",        "Models",         "\U0001F52C"),   # 🔬 microscope
    ("faces",         "Faces",          "\U0001F464"),   # 👤 busts in silhouette
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
        # Refresh content for specific tabs
        if tab_id == "general" or tab_id == "advanced":
            self._refresh_web_status()
        elif tab_id == "notifications":
            self._check_dnd_times()
        elif tab_id == "models":
            self._refresh_ml_status()
        elif tab_id == "faces":
            self._refresh_faces()
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
        self._build_api_server(parent)

    def _build_api_server(self, parent: tk.Frame) -> None:
        c = self._col
        self._section_header(parent, "API Server", "Web dashboard & REST API", pad_top=24)
        api_sf = self._section(parent)

        # Toggle
        self._mac_toggle(api_sf, "Enable API Server",
                         "Allow web dashboard and REST API access", "api_enabled")

        # Host / Port fields
        api_host_var = tk.StringVar(value=self._cfg.get("api_host", "127.0.0.1"))
        api_port_var = tk.StringVar(value=str(self._cfg.get("api_port", 8765)))

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
        row2.pack(fill="x", pady=(4, 0))
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

        # --- Status row ---
        status_row = tk.Frame(api_sf, bg=c["window_bg"])
        status_row.pack(fill="x", pady=(10, 0))

        self._web_status_label = tk.Label(
            status_row, text="● Checking...",
            font=("SF Pro Text", 11),
            fg=c["label_tertiary"], bg=c["window_bg"], anchor="w",
        )
        self._web_status_label.pack(side="left", padx=(0, 8))

        # --- Button row ---
        btn_row = tk.Frame(api_sf, bg=c["window_bg"])
        btn_row.pack(fill="x", pady=(6, 0))

        self._web_btn_start = self._make_action_button(btn_row, "Start", c["success"], "web_start")
        self._web_btn_stop = self._make_action_button(btn_row, "Stop", c["danger"], "web_stop")
        self._web_btn_restart = self._make_action_button(btn_row, "Restart", c["warning"], "web_restart")

        # Bind field changes to re-check
        def _on_field_save(name=""):
            host = api_host_var.get().strip()
            try:
                port = int(api_port_var.get().strip())
            except ValueError:
                return
            self._set("api_host", host)
            self._set("api_port", port)
            self._refresh_web_status()

        host_ent.bind("<FocusOut>", lambda e: _on_field_save())
        host_ent.bind("<Return>", lambda e: _on_field_save())
        port_ent.bind("<FocusOut>", lambda e: _on_field_save())
        port_ent.bind("<Return>", lambda e: _on_field_save())

        # Initial check
        self._root.after(500, self._refresh_web_status)

    def _make_action_button(self, parent: tk.Frame, text: str, accent: str, ipc_method: str) -> tk.Frame:
        """Create Apple HIG -style button with hover/active feedback."""
        c = self._col
        btn = tk.Frame(parent, bg=c["btn_bg"], relief="flat", bd=0,
                       highlightbackground=c["entry_border"],
                       highlightthickness=1, padx=14, pady=6)
        btn.pack(side="left", padx=(0, 8))

        label = tk.Label(btn, text=text, font=("SF Pro Text", 11, "bold"),
                         fg=accent, bg=c["btn_bg"])
        label.pack()

        def _on_enter(event):
            btn.configure(bg=c["btn_hover"])
            label.configure(bg=c["btn_hover"])

        def _on_leave(event):
            btn.configure(bg=c["btn_bg"])
            label.configure(bg=c["btn_bg"])

        def _on_click(event):
            # Active flash: blue briefly
            btn.configure(bg=c["btn_active"])
            label.configure(bg=c["btn_active"])
            label.configure(fg="#FFFFFF")
            self._root.after(200, lambda: (
                btn.configure(bg=c["btn_bg"]),
                label.configure(bg=c["btn_bg"]),
                label.configure(fg=accent),
            ))
            # Call IPC
            self._web_call(ipc_method)

        btn.bind("<Enter>", _on_enter)
        btn.bind("<Leave>", _on_leave)
        btn.bind("<Button-1>", _on_click)
        label.bind("<Enter>", _on_enter)
        label.bind("<Leave>", _on_leave)
        label.bind("<Button-1>", _on_click)

        return btn

    def _web_call(self, method: str) -> None:
        """Call a web control method via IPC, then refresh status."""
        if method == "web_start":
            _ipc_call("web_start")
        elif method == "web_stop":
            _ipc_call("web_stop")
        elif method == "web_restart":
            _ipc_call("web_restart")
        # Wait a moment then check
        self._root.after(500, self._refresh_web_status)

    def _refresh_web_status(self) -> None:
        """Check web server with HTTP heartbeat (not IPC — IPC from settings.py to daemon is unreliable cross-process)."""
        host = self._cfg.get("api_host", "127.0.0.1")
        port = self._cfg.get("api_port", 8765)
        c = self._col
        try:
            import urllib.request
            url = f"http://{host}:{port}/api/status"
            req = urllib.request.Request(url, method="GET")
            resp = urllib.request.urlopen(req, timeout=2)
            if resp.getcode() == 200:
                self._web_status_label.configure(
                    text="● Running", fg=c["success"])
                self._web_btn_start.configure(bg=c["btn_bg"])  # keep as bg reference, actual state managed
            else:
                self._web_status_label.configure(
                    text="○ Stopped", fg=c["label_secondary"])
        except Exception:
            self._web_status_label.configure(
                text="○ Stopped", fg=c["label_secondary"])

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
        self._labeled_time_entry(sf3, "Start (HH:MM)",
                                 self._cfg.get("notification_dnd_start", ""),
                                 "notification_dnd_start")
        self._labeled_time_entry(sf3, "End (HH:MM)",
                                 self._cfg.get("notification_dnd_end", ""),
                                 "notification_dnd_end")

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
        
        # ── MQTT Configuration ──────────────────────────────────────────────
        mqtt_sf = self._section(parent, "MQTT")
        self._mac_toggle(mqtt_sf, "Enable MQTT",
                         "Publish detection events to MQTT broker", "mqtt_enabled")
        
        mqtt_host_var = tk.StringVar(value=self._cfg.get("mqtt_broker", ""))
        mqtt_port_var = tk.StringVar(value=str(self._cfg.get("mqtt_port", 1883)))
        mqtt_user_var = tk.StringVar(value=self._cfg.get("mqtt_username", ""))
        mqtt_pass_var = tk.StringVar(value=self._cfg.get("mqtt_password", ""))
        mqtt_topic_var = tk.StringVar(value=self._cfg.get("mqtt_topic_prefix", "clairvoyant"))
        
        row1 = tk.Frame(mqtt_sf, bg=c["window_bg"])
        row1.pack(fill="x", pady=(6, 0))
        tk.Label(row1, text="Broker", font=("SF Pro Text", 12),
                 fg=c["label_secondary"], bg=c["window_bg"]).pack(side="left")
        host_ent = tk.Entry(row1, textvariable=mqtt_host_var,
                            bg=c["entry_bg"], fg=c["label_primary"],
                            insertbackground=c["label_primary"],
                            font=("SF Mono", 12),
                            relief="flat", bd=0,
                            highlightbackground=c["entry_border"],
                            highlightcolor=c["control_active"],
                            highlightthickness=1)
        host_ent.pack(side="right", ipadx=6, ipady=4)
        
        row2 = tk.Frame(mqtt_sf, bg=c["window_bg"])
        row2.pack(fill="x", pady=(4, 0))
        tk.Label(row2, text="Port", font=("SF Pro Text", 12),
                 fg=c["label_secondary"], bg=c["window_bg"]).pack(side="left")
        port_ent = tk.Entry(row2, textvariable=mqtt_port_var,
                            bg=c["entry_bg"], fg=c["label_primary"],
                            insertbackground=c["label_primary"],
                            font=("SF Mono", 12),
                            relief="flat", bd=0,
                            highlightbackground=c["entry_border"],
                            highlightcolor=c["control_active"],
                            highlightthickness=1)
        port_ent.pack(side="right", ipadx=6, ipady=4)
        
        row3 = tk.Frame(mqtt_sf, bg=c["window_bg"])
        row3.pack(fill="x", pady=(4, 0))
        tk.Label(row3, text="Username", font=("SF Pro Text", 12),
                 fg=c["label_secondary"], bg=c["window_bg"]).pack(side="left")
        user_ent = tk.Entry(row3, textvariable=mqtt_user_var,
                            bg=c["entry_bg"], fg=c["label_primary"],
                            insertbackground=c["label_primary"],
                            font=("SF Mono", 12),
                            relief="flat", bd=0,
                            highlightbackground=c["entry_border"],
                            highlightcolor=c["control_active"],
                            highlightthickness=1)
        user_ent.pack(side="right", ipadx=6, ipady=4)
        
        row4 = tk.Frame(mqtt_sf, bg=c["window_bg"])
        row4.pack(fill="x", pady=(4, 0))
        tk.Label(row4, text="Password", font=("SF Pro Text", 12),
                 fg=c["label_secondary"], bg=c["window_bg"]).pack(side="left")
        pass_ent = tk.Entry(row4, textvariable=mqtt_pass_var,
                            bg=c["entry_bg"], fg=c["label_primary"],
                            insertbackground=c["label_primary"],
                            font=("SF Mono", 12),
                            relief="flat", bd=0,
                            highlightbackground=c["entry_border"],
                            highlightcolor=c["control_active"],
                            highlightthickness=1,
                            show="*")
        pass_ent.pack(side="right", ipadx=6, ipady=4)
        
        row5 = tk.Frame(mqtt_sf, bg=c["window_bg"])
        row5.pack(fill="x", pady=(4, 0))
        tk.Label(row5, text="Topic Prefix", font=("SF Pro Text", 12),
                 fg=c["label_secondary"], bg=c["window_bg"]).pack(side="left")
        topic_ent = tk.Entry(row5, textvariable=mqtt_topic_var,
                             bg=c["entry_bg"], fg=c["label_primary"],
                             insertbackground=c["label_primary"],
                             font=("SF Mono", 12),
                             relief="flat", bd=0,
                             highlightbackground=c["entry_border"],
                             highlightcolor=c["control_active"],
                             highlightthickness=1)
        topic_ent.pack(side="right", ipadx=6, ipady=4)
        
        # Bind field changes to save
        def _on_mqtt_field_save():
            try:
                port = int(mqtt_port_var.get().strip())
            except ValueError:
                port = 1883
            self._set("mqtt_broker", mqtt_host_var.get().strip())
            self._set("mqtt_port", port)
            self._set("mqtt_username", mqtt_user_var.get().strip())
            self._set("mqtt_password", mqtt_pass_var.get())
            self._set("mqtt_topic_prefix", mqtt_topic_var.get().strip())
        
        for entry in [host_ent, port_ent, user_ent, pass_ent, topic_ent]:
            entry.bind("<FocusOut>", lambda e: _on_mqtt_field_save())
            entry.bind("<Return>", lambda e: _on_mqtt_field_save())

        # ── Battery Configuration ──────────────────────────────────────────────
        battery_sf = self._section(parent, "Battery")
        self._mac_toggle(battery_sf, "Pause on Battery",
                         "Pause recognition when on battery power", "pause_on_battery")
        self._mac_toggle(battery_sf, "Pause When Away",
                         "Pause when not connected to home WiFi", "pause_when_away")
        
        poll_interval_var = tk.StringVar(value=str(self._cfg.get("battery_poll_interval", 30)))
        row6 = tk.Frame(battery_sf, bg=c["window_bg"])
        row6.pack(fill="x", pady=(6, 0))
        tk.Label(row6, text="Poll Interval (seconds)", font=("SF Pro Text", 12),
                 fg=c["label_secondary"], bg=c["window_bg"]).pack(side="left")
        poll_ent = tk.Entry(row6, textvariable=poll_interval_var,
                            bg=c["entry_bg"], fg=c["label_primary"],
                            insertbackground=c["label_primary"],
                            font=("SF Mono", 12),
                            relief="flat", bd=0,
                            highlightbackground=c["entry_border"],
                            highlightcolor=c["control_active"],
                            highlightthickness=1)
        poll_ent.pack(side="right", ipadx=6, ipady=4)
        
        def _on_battery_field_save():
            try:
                interval = int(poll_interval_var.get().strip())
            except ValueError:
                interval = 30
            self._set("battery_poll_interval", interval)
        
        poll_ent.bind("<FocusOut>", lambda e: _on_battery_field_save())
        poll_ent.bind("<Return>", lambda e: _on_battery_field_save())

        # ── Home WiFi list (käyttäjäystävällinen list-view) ──────────────
        sf2 = self._section(parent, "Home WiFi")
        self._home_ssids_list: list[str] = []
        raw = self._cfg.get("home_ssids", "")
        if isinstance(raw, str):
            self._home_ssids_list = [s.strip() for s in raw.split(",") if s.strip()]
        elif isinstance(raw, list):
            self._home_ssids_list = list(raw)

        # Listbox current SSIDs
        list_frame = tk.Frame(sf2, bg=c["window_bg"])
        list_frame.pack(fill="x", pady=(4, 0))
        self._ssid_lb = tk.Listbox(
            list_frame, height=4, bg=c["entry_bg"], fg=c["label_primary"],
            highlightbackground=c["entry_border"], highlightthickness=1,
            relief="flat", bd=0, selectbackground=c["control_active"],
            selectforeground=c["label_primary"], font=("SF Mono", 12),
        )
        self._ssid_lb.pack(side="left", fill="x", expand=True)
        for ssid in self._home_ssids_list:
            self._ssid_lb.insert("end", ssid)

        # Delete button
        del_btn = self._mac_button(
            list_frame, "✕", self._delete_selected_ssid,
            style="destructive", padx=8, pady=2, font_size=12,
        )
        del_btn.pack(side="right", padx=(6, 0))

        # Add row: Entry + Add button
        add_frame = tk.Frame(sf2, bg=c["window_bg"])
        add_frame.pack(fill="x", pady=(4, 0))
        self._ssid_entry_var = tk.StringVar()
        ssid_ent = tk.Entry(
            add_frame, textvariable=self._ssid_entry_var,
            bg=c["entry_bg"], fg=c["label_primary"],
            insertbackground=c["label_primary"],
            font=("SF Mono", 12),
            relief="flat", bd=0,
            highlightbackground=c["entry_border"],
            highlightcolor=c["control_active"],
            highlightthickness=1,
        )
        ssid_ent.pack(side="left", fill="x", expand=True, ipadx=6, ipady=4)

        # Enter key saves immediately
        def _add_ssid_enter(event=None):
            self._add_ssid()
        ssid_ent.bind("<Return>", _add_ssid_enter)

        add_btn = self._mac_button(
            add_frame, "Add", self._add_ssid,
            style="primary", padx=12, pady=4, font_size=12,
        )
        add_btn.pack(side="right", padx=(6, 0))

        self._ssid_status_var = tk.StringVar(value="")
        tk.Label(sf2, textvariable=self._ssid_status_var,
                 font=("SF Pro Text", 10),
                 bg=c["window_bg"], fg=c["label_tertiary"]).pack(anchor="w", pady=(2, 0))

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

    # ── tab: Models ─────────────────────────────────────────────────────

    def _build_models(self, parent: tk.Frame) -> None:
        c = self._col
        self._section_header(parent, "Model Download", "Download and manage AI models")
        
        # Model download section
        model_sf = self._section(parent)
        
        # Model data: name, filename, size (MB)
        models = [
            ("Person Detection", "yolov8n.onnx", 6.2),
            ("Face Detection", "det_10g.onnx", 4.8),
            ("Face Recognition", "w600k_r50.onnx", 95.1)
        ]
        
        self._model_status_labels = {}
        self._model_buttons = {}
        
        for name, filename, size in models:
            row = tk.Frame(model_sf, bg=c["window_bg"])
            row.pack(fill="x", pady=(4, 0))
            
            # Model info
            info_frame = tk.Frame(row, bg=c["window_bg"])
            info_frame.pack(side="left", fill="x", expand=True)
            tk.Label(info_frame, text=name, font=("SF Pro Text", 12, "bold"),
                     fg=c["label_primary"], bg=c["window_bg"]).pack(anchor="w")
            tk.Label(info_frame, text=f"{filename} ({size} MB)", font=("SF Pro Text", 10),
                     fg=c["label_secondary"], bg=c["window_bg"]).pack(anchor="w")
            
            # Status label
            status_var = tk.StringVar(value="Not Downloaded")
            self._model_status_labels[filename] = status_var
            status_label = tk.Label(row, textvariable=status_var, font=("SF Pro Text", 10),
                                    fg=c["label_secondary"], bg=c["window_bg"])
            status_label.pack(side="left", padx=(10, 0))
            
            # Download button
            btn = self._mac_button(
                row, "Download", 
                lambda f=filename: self._download_model(f),
                style="primary", padx=12, pady=2, font_size=11
            )
            self._model_buttons[filename] = btn
            btn.pack(side="right")
        
        # Download all button
        all_btn = self._mac_button(
            model_sf, "Download All Models", 
            self._download_all_models,
            style="primary", padx=12, pady=4, font_size=12
        )
        all_btn.pack(pady=(10, 0))
        
        # Model Settings section
        self._section_header(parent, "Model Settings", "Detection thresholds and timing", pad_top=24)
        settings_sf = self._section(parent)
        
        # Person detection confidence
        self._labeled_slider(settings_sf, "Person Detection Confidence",
                            self._cfg.get("person_confidence", 0.5),
                            0.0, 1.0, 0.05,
                            lambda v: self._set("person_confidence", v))
        
        # Face detection confidence
        self._labeled_slider(settings_sf, "Face Detection Confidence",
                            self._cfg.get("face_confidence", 0.7),
                            0.0, 1.0, 0.05,
                            lambda v: self._set("face_confidence", v))
        
        # Face recognition threshold
        self._labeled_slider(settings_sf, "Face Recognition Threshold",
                            self._cfg.get("recognition_threshold", 0.6),
                            0.0, 1.0, 0.05,
                            lambda v: self._set("recognition_threshold", v))
        
        # Frame interval
        self._labeled_entry(settings_sf, "Frame Interval (seconds)",
                           str(self._cfg.get("frame_interval", 0.5)),
                           lambda v: self._set("frame_interval", float(v) if v else 0.5))
        
        # Debounce seconds
        self._labeled_entry(settings_sf, "Debounce Time (seconds)",
                           str(self._cfg.get("debounce_seconds", 2)),
                           lambda v: self._set("debounce_seconds", int(v) if v else 2))

    def _set_btn_text(self, btn: tk.Frame, text: str) -> None:
        """Update _mac_button label text. btn is the outer Frame."""
        for child in btn.winfo_children():
            for grandchild in child.winfo_children():
                if isinstance(grandchild, tk.Label):
                    grandchild.configure(text=text)
                    return

    def _download_model(self, model_name: str) -> None:
        """Download a specific model via IPC."""
        try:
            self._model_status_labels[model_name].set("Downloading...")
            self._set_btn_text(self._model_buttons[model_name], "Downloading")
            _ipc_call("ml.download", {"model": model_name})
        except Exception as e:
            self._model_status_labels[model_name].set(f"Error: {str(e)}")
            self._set_btn_text(self._model_buttons[model_name], "Download")

    def _download_all_models(self) -> None:
        """Download all models via IPC."""
        try:
            for model_name in self._model_status_labels.keys():
                self._model_status_labels[model_name].set("Queued...")
                self._set_btn_text(self._model_buttons[model_name], "Downloading")
            _ipc_call("ml.download_all")
        except Exception as e:
            pass

    def _refresh_ml_status(self) -> None:
        """Refresh model download status from daemon."""
        try:
            result = _ipc_call("ml.status")
            if result and "models" in result:
                for model_name, status in result["models"].items():
                    if model_name in self._model_status_labels:
                        s = status.get("status")
                        if s == "complete":
                            self._model_status_labels[model_name].set("Complete")
                            self._set_btn_text(self._model_buttons[model_name], "Downloaded")
                        elif s == "downloading":
                            p = status.get("progress", 0)
                            self._model_status_labels[model_name].set(f"Downloading ({p}%)")
                            self._set_btn_text(self._model_buttons[model_name], "Downloading")
                        elif s == "error":
                            self._model_status_labels[model_name].set(f"Error: {status.get('error', 'Unknown')}")
                            self._set_btn_text(self._model_buttons[model_name], "Retry")
                        else:
                            self._model_status_labels[model_name].set("Not Downloaded")
                            self._set_btn_text(self._model_buttons[model_name], "Download")
        except Exception:
            pass

    # ── tab: Faces ──────────────────────────────────────────────────────

    def _build_faces(self, parent: tk.Frame) -> None:
        c = self._col
        self._section_header(parent, "Registered Faces", "Manage enrolled faces for recognition")
        
        # Faces list section
        faces_sf = self._section(parent)
        
        # Header row
        header = tk.Frame(faces_sf, bg=c["window_bg"])
        header.pack(fill="x", pady=(0, 6))
        tk.Label(header, text="Name", font=("SF Pro Text", 11, "bold"),
                 fg=c["label_primary"], bg=c["window_bg"]).pack(side="left", width=15)
        tk.Label(header, text="Camera", font=("SF Pro Text", 11, "bold"),
                 fg=c["label_primary"], bg=c["window_bg"]).pack(side="left", width=15)
        tk.Label(header, text="Samples", font=("SF Pro Text", 11, "bold"),
                 fg=c["label_primary"], bg=c["window_bg"]).pack(side="left", width=10)
        tk.Label(header, text="Last Seen", font=("SF Pro Text", 11, "bold"),
                 fg=c["label_primary"], bg=c["window_bg"]).pack(side="left", expand=True)
        
        # Faces list container
        self._faces_list_frame = tk.Frame(faces_sf, bg=c["window_bg"])
        self._faces_list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # Enroll new face section
        self._section_header(parent, "Enroll New Face", "Add a new face to recognize", pad_top=24)
        enroll_sf = self._section(parent)
        
        # Name entry
        self._face_name_var = tk.StringVar()
        self._labeled_entry(enroll_sf, "Name", "", 
                           lambda v: self._face_name_var.set(v))
        
        # Capture button
        self._enroll_status_var = tk.StringVar(value="Ready to enroll")
        tk.Label(enroll_sf, textvariable=self._enroll_status_var,
                 font=("SF Pro Text", 11),
                 bg=c["window_bg"], fg=c["label_secondary"]).pack(anchor="w", pady=(8, 0))
        
        self._capture_btn = self._mac_button(
            enroll_sf, "Capture from Camera", 
            self._capture_face,
            style="primary", padx=12, pady=4, font_size=12
        )
        self._capture_btn.pack(pady=(4, 0))
        
        # Refresh faces list
        self._refresh_faces()

    def _refresh_faces(self) -> None:
        """Refresh the list of registered faces."""
        # Clear existing list
        for widget in self._faces_list_frame.winfo_children():
            widget.destroy()
            
        c = self._col
        try:
            result = _ipc_call("faces.list")
            if result and isinstance(result, list):
                if not result:
                    tk.Label(self._faces_list_frame, text="No faces enrolled", 
                             font=("SF Pro Text", 11),
                             fg=c["label_secondary"], bg=c["window_bg"]).pack()
                else:
                    for face in result:
                        row = tk.Frame(self._faces_list_frame, bg=c["window_bg"])
                        row.pack(fill="x", pady=(4, 0))
                        
                        tk.Label(row, text=face.get("name", "Unknown"), 
                                font=("SF Pro Text", 11),
                                fg=c["label_primary"], bg=c["window_bg"]).pack(side="left", width=15)
                        tk.Label(row, text=face.get("camera", "Any"), 
                                font=("SF Pro Text", 10),
                                fg=c["label_secondary"], bg=c["window_bg"]).pack(side="left", width=15)
                        tk.Label(row, text=str(face.get("samples", 0)), 
                                font=("SF Pro Text", 10),
                                fg=c["label_secondary"], bg=c["window_bg"]).pack(side="left", width=10)
                        tk.Label(row, text=face.get("last_seen", "Never"), 
                                font=("SF Pro Text", 10),
                                fg=c["label_secondary"], bg=c["window_bg"]).pack(side="left", expand=True)
                        
                        # Delete button
                        del_btn = self._mac_button(
                            row, "Delete", 
                            lambda n=face.get("name"): self._delete_face(n),
                            style="destructive", padx=8, pady=2, font_size=10
                        )
                        del_btn.pack(side="right")
            else:
                tk.Label(self._faces_list_frame, text="Error loading faces", 
                         font=("SF Pro Text", 11),
                         fg=c["label_secondary"], bg=c["window_bg"]).pack()
        except Exception as e:
            tk.Label(self._faces_list_frame, text=f"Error: {str(e)}", 
                     font=("SF Pro Text", 11),
                     fg=c["label_secondary"], bg=c["window_bg"]).pack()

    def _delete_face(self, name: str) -> None:
        """Delete a registered face."""
        try:
            _ipc_call("faces.delete", {"name": name})
            self._refresh_faces()  # Refresh the list
        except Exception as e:
            # In a real implementation we'd show an error to the user
            pass

    def _capture_face(self) -> None:
        """Capture a new face for enrollment."""
        name = self._face_name_var.get().strip()
        if not name:
            self._enroll_status_var.set("Please enter a name")
            return
            
        self._enroll_status_var.set("Capturing...")
        self._capture_btn.configure(state="disabled")
        self._capture_btn.config(text="Capturing...")
        
        try:
            # In a real implementation this would capture from camera
            result = _ipc_call("faces.enroll", {"name": name})
            if result and result.get("success"):
                self._enroll_status_var.set(f"Enrolled: {name}")
                self._refresh_faces()  # Refresh the list
            else:
                error = result.get("error", "Unknown error") if result else "No response"
                self._enroll_status_var.set(f"Error: {error}")
        except Exception as e:
            self._enroll_status_var.set(f"Error: {str(e)}")
        finally:
            self._capture_btn.configure(state="normal")
            self._capture_btn.config(text="Capture from Camera")

    # ── IPC helpers ─────────────────────────────────────────────────────

    def _check_dnd_times(self) -> None:
        """Validate DND times and update UI indicators."""
        # In a real implementation we would check if the times are valid
        # For now we'll just pass
        pass

    def _send_test_notification(self, title: str, subtitle: str, message: str,
                                sound_key: str = "sound_family") -> None:
        """Send a macOS notification or notify via IPC daemon."""
        # Try IPC: call daemon to send notification
        result = _ipc_call("config.get", {"section": "notifications"})
        if result:
            # IPC daemon available — use test_notify with configured sound
            test_resp = _ipc_call("test_notify", {
                "title": title, "subtitle": subtitle, "message": message,
                "sound_key": sound_key,
            })
            if test_resp:
                msg = test_resp.get("message", "Notification sent via daemon")
                self._test_status_var.set(f"✅ {msg}")
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
            sound_key="sound_family",
        )

    def _test_alert_notification(self) -> None:
        self._send_test_notification(
            "Clairvoyant-Optics",
            "⚠ Unknown Person Alert",
            "Unknown person detected on Camera 1!",
            sound_key="sound_alert",
        )

    # ── Home WiFi list helpers ───────────────────────────────────────────

    def _add_ssid(self) -> None:
        name = self._ssid_entry_var.get().strip()
        if not name:
            self._ssid_status_var.set("⏎ Enter an SSID name")
            return
        if name in self._home_ssids_list:
            self._ssid_status_var.set(f"⚠ SSID '{name}' already in list")
            return
        self._home_ssids_list.append(name)
        self._ssid_lb.insert("end", name)
        self._ssid_entry_var.set("")
        self._ssid_status_var.set(f"✅ Added '{name}'")
        self._set("home_ssids", ", ".join(self._home_ssids_list))

    def _delete_selected_ssid(self) -> None:
        sel = self._ssid_lb.curselection()
        if not sel:
            self._ssid_status_var.set("⚠ Select an SSID to remove")
            return
        idx = sel[0]
        removed = self._home_ssids_list.pop(idx)
        self._ssid_lb.delete(idx)
        self._ssid_status_var.set(f"🗑 Removed '{removed}'")
        self._set("home_ssids", ", ".join(self._home_ssids_list))

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

    def _labeled_slider(self, parent: tk.Frame, label: str, value: float,
                        min_val: float, max_val: float, step: float, callback) -> None:
        """Slider with label and value display."""
        c = self._col
        row = tk.Frame(parent, bg=c["window_bg"])
        row.pack(fill="x", pady=(8, 0))
        
        # Label on left
        tk.Label(row, text=label, font=("SF Pro Text", 12),
                 fg=c["label_secondary"], bg=c["window_bg"]).pack(side="left")
        
        # Value display and slider container on right
        right_frame = tk.Frame(row, bg=c["window_bg"])
        right_frame.pack(side="right")
        
        # Value display
        value_var = tk.StringVar(value=f"{value:.2f}")
        value_label = tk.Label(right_frame, textvariable=value_var, font=("SF Mono", 11),
                               fg=c["label_primary"], bg=c["window_bg"])
        value_label.pack()
        
        # Slider
        slider_var = tk.DoubleVar(value=value)
        slider = tk.Scale(right_frame, from_=min_val, to=max_val, resolution=step,
                         variable=slider_var, orient="horizontal", length=200,
                         bg=c["window_bg"], fg=c["label_primary"],
                         activebackground=c["control_active"],
                         highlightthickness=0, bd=0,
                         font=("SF Pro Text", 10),
                         command=lambda v: [
                             value_var.set(f"{float(v):.2f}"),
                             callback(float(v))
                         ])
        slider.pack()

    def _labeled_entry(self, parent: tk.Frame, label: str, value: str, callback) -> None:
        """Text entry with label and auto-save."""
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
        
        def _do_save(val: str) -> None:
            callback(val)
        
        ent.bind("<FocusOut>", lambda e: _do_save(var.get()))
        ent.bind("<Return>", lambda e: _do_save(var.get()))

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

    def _labeled_time_entry(self, parent: tk.Frame, label: str, value: str, key: str) -> None:
        """Time entry (HH:MM) with auto-save + format validation + flash on error."""
        import re
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

        def _do_save(raw: str) -> None:
            raw = raw.strip()
            if raw and not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", raw):
                # Flash red border briefly
                ent.config(highlightbackground="#ff4444")
                self._root.after(2000, lambda: ent.config(highlightbackground=c["entry_border"]))
                return
            self._set(key, raw)
        ent.bind("<FocusOut>", lambda e, cb=_do_save, v=var: cb(v.get()))
        ent.bind("<Return>", lambda e, cb=_do_save, v=var: cb(v.get()))

    # ── config mutation ─────────────────────────────────────────────────

    def _set(self, key: str, value) -> None:
        self._cfg[key] = value
        save_key(key, value)
        if key == "launch_at_login":
            self._manage_launch_agent(bool(value))
        self._notify_app_if_needed(key)

    def _manage_launch_agent(self, enable: bool) -> None:
        """Create or remove LaunchAgent plist for login auto-start.

        Uses python + daemon.py directly (NOT Clairvoyant-Optics --daemon),
        to avoid spawning a duplicate menu bar process.
        """
        import plistlib
        import subprocess

        launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
        plist_path = launch_agents_dir / "fi.kaikkonen.clairvoyantd.plist"

        if enable:
            launch_agents_dir.mkdir(parents=True, exist_ok=True)
            if IS_BUNDLED:
                python_bin = str(BUNDLE_DIR.parent / "MacOS" / "python")  # type: ignore[union-attr]
                daemon_script = str(BUNDLE_DIR / "lib" / "python3.11" / "src" / "service" / "daemon.py")  # type: ignore[union-attr]
            else:
                python_bin = sys.executable
                daemon_script = str(Path(__file__).resolve().parent.parent.parent / "src" / "service" / "daemon.py")
            plist_data = {
                "Label": "fi.kaikkonen.clairvoyantd",
                "ProgramArguments": [python_bin, daemon_script],
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
