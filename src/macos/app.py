#!/usr/bin/env python3
"""Clairvoyant-Optics v4.0.2 — Menu bar application (rumps).

This is the main app. It lives in the macOS menu bar (top-right).
No Dock icon. Settings window runs as a separate process.

Architecture:
  app.py (rumps, LSUIElement=True) → spawns → settings.py (tkinter)
  Communication: SIGUSR1 = show settings, SIGTERM = quit settings
"""

import os
import signal
import subprocess
import sys
from pathlib import Path

try:
    import rumps
except ImportError:
    rumps = None

VERSION = "4.2.3"

# Bundle-aware paths
IS_BUNDLED = getattr(sys, "frozen", False) or (
    # Detect bundle even when running via python app.py directly
    "Contents/Resources" in str(Path(__file__).resolve())
)
if IS_BUNDLED:
    # py2app bundle: resources are alongside app.py in Contents/Resources/
    BUNDLE_DIR = Path(__file__).resolve().parent
    BUNDLE_CONTENTS = BUNDLE_DIR.parent
    ASSETS = BUNDLE_DIR
    SETTINGS_SCRIPT = BUNDLE_DIR / "settings.py"
    BUNDLED_PYTHON = BUNDLE_CONTENTS / "MacOS" / "python"
else:
    # Development mode
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    ASSETS = PROJECT_ROOT / "assets"
    SETTINGS_SCRIPT = PROJECT_ROOT / "src" / "macos" / "settings.py"

CONFIG_DIR = Path.home() / ".clairvoyant-optics"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
APP_PID_FILE = CONFIG_DIR / "app.pid"
SETTINGS_PID_FILE = CONFIG_DIR / "settings.pid"

APP_BUNDLE_ID = "fi.kaikkonen.clairvoyant-optics"
LAUNCH_AGENT_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{APP_BUNDLE_ID}.plist"

DEFAULTS = {
    "log_level": "INFO",
    "launch_at_login": False,
    "auto_update": False,
    "error_reporting": False,
    "pause_on_battery": False,
    "home_ssids": "",
    "pause_when_away": False,
    "log_level": "INFO",
}

# ── Config helpers ──────────────────────────────────────────

def _load_yaml(path: Path) -> dict:
    try:
        import yaml
        if path.exists():
            data = yaml.safe_load(open(path))
            return data if isinstance(data, dict) else {}
    except ImportError:
        pass
    return {}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(_load_yaml(CONFIG_FILE))
    return cfg


# ── Launch at Login (LaunchAgent plist) ─────────────────────

def manage_launch_at_login(enable: bool):
    LAUNCH_AGENT_PLIST.parent.mkdir(parents=True, exist_ok=True)
    if enable:
        # In bundle mode, use the .app bundle executable; in dev, use venv python + source
        if IS_BUNDLED:
            app_exec = str(BUNDLE_CONTENTS / "MacOS" / "Clairvoyant-Optics")
            program_args = f"        <string>{app_exec}</string>"
        else:
            py = sys.executable
            script = PROJECT_ROOT / "src" / "macos" / "app.py"
            program_args = f"        <string>{py}</string>\n        <string>{script}</string>"

        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{APP_BUNDLE_ID}</string>
    <key>ProgramArguments</key>
    <array>
{program_args}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>"""
        LAUNCH_AGENT_PLIST.write_text(plist)
    else:
        LAUNCH_AGENT_PLIST.unlink(missing_ok=True)


# ── Settings process management ─────────────────────────────

def _read_pid(path: Path) -> int | None:
    try:
        if path.exists():
            return int(path.read_text().strip())
    except (ValueError, OSError):
        pass
    return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def spawn_settings(debug: bool = False) -> bool:
    """Spawn settings window via Settings.app wrapper.

    Uses open -a because LSUIElement parents (rumps menu bar app)
    cannot spawn visible tkinter windows directly on macOS —
    the child inherits the background-only window server context.
    The Settings.app wrapper (bundled inside Resources/) is a
    normal foreground .app that gets its own window-server connection.
    """
    if IS_BUNDLED:
        settings_app = BUNDLE_DIR / "Settings.app"
        if settings_app.exists():
            subprocess.run(["open", "-a", str(settings_app)], check=False)
            return True
        return False
    # Development: spawn directly (this works outside LSUIElement)
    if not SETTINGS_SCRIPT.exists():
        return False
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [sys.executable, str(SETTINGS_SCRIPT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True


def show_settings() -> bool:
    """Bring settings window to front. Spawn if not running."""
    pid = _read_pid(SETTINGS_PID_FILE)
    if pid and _pid_alive(pid):
        os.kill(pid, signal.SIGUSR1)
        return True
    # Spawn — settings.py shows itself automatically after hide-from-dock
    return spawn_settings()


def quit_settings():
    """Terminate settings process."""
    pid = _read_pid(SETTINGS_PID_FILE)
    if pid and _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            os.kill(pid, signal.SIGKILL)  # force if SIGTERM ignored
        except OSError:
            pass
    SETTINGS_PID_FILE.unlink(missing_ok=True)


# ── Menu Bar App ────────────────────────────────────────────

class ClairvoyantApp(rumps.App):

    def __init__(self):
        icon = str(ASSETS / "eye_22.png") if (ASSETS / "eye_22.png").exists() else None
        super().__init__(name="Clairvoyant-Optics", title="", icon=icon, quit_button=None)
        self._build_menu()

    def _build_menu(self):
        self.menu.clear()

        # macOS convention: "Settings…" with ellipsis, ⌘, shortcut
        settings = rumps.MenuItem("Settings…", key="s")
        settings.set_callback(self._on_settings)
        self.menu.add(settings)

        self.menu.add(rumps.separator)

        # macOS convention: "Quit <AppName>" with ⌘Q
        quit_item = rumps.MenuItem("Quit Clairvoyant-Optics", key="q")
        quit_item.set_callback(self._on_quit)
        self.menu.add(quit_item)

    def _on_settings(self, sender):
        show_settings()

    def _on_quit(self, sender):
        quit_settings()
        APP_PID_FILE.unlink(missing_ok=True)
        rumps.quit_application()


# ── Main ────────────────────────────────────────────────────

def _on_sigusr2(signum, frame):
    """Settings window notified us to reload config."""
    cfg = load_config()
    manage_launch_at_login(cfg.get("launch_at_login", False))


def main():
    if rumps is None:
        print("ERROR: rumps not installed. Run: pip install rumps", file=sys.stderr)
        sys.exit(1)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    APP_PID_FILE.write_text(str(os.getpid()))

    signal.signal(signal.SIGUSR2, _on_sigusr2)

    cfg = load_config()
    manage_launch_at_login(cfg.get("launch_at_login", False))

    ClairvoyantApp().run()


if __name__ == "__main__":
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        sys.path.insert(0, sys._MEIPASS)
    main()
