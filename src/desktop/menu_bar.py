#!/usr/bin/env python3
"""Clairvoyant-Optics v5.0 — Menu Bar (rumps, IPC client).

LSUIElement menu bar app. Communicates with clairvoyantd via Unix socket IPC.
Shows pipeline status, camera health, quick start/stop, opens Settings.

Architecture:
  menu_bar.py (rumps) ──IPC──▶ clairvoyantd (daemon)
                                    └── spawns ──▶ Settings.app (tkinter)
"""

import os
import signal
import sys
import threading
import time
from pathlib import Path

try:
    import rumps
except ImportError:
    rumps = None

VERSION = "5.0.0"

# ── Paths ──────────────────────────────────────────────────────────────

IS_BUNDLED = getattr(sys, "frozen", False) or (
    "Contents/Resources" in str(Path(__file__).resolve())
)
CONFIG_DIR = Path.home() / ".clairvoyant-optics"

if IS_BUNDLED:
    BUNDLE_DIR = Path(__file__).resolve().parent
    BUNDLE_CONTENTS = BUNDLE_DIR.parent
    ASSETS = BUNDLE_DIR
    SETTINGS_APP = BUNDLE_DIR / "Settings.app"
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    ASSETS = PROJECT_ROOT / "assets"
    SETTINGS_APP = None

# ── IPC Client ─────────────────────────────────────────────────────────

from src.desktop.ipc_client import IPCClient

# ── Menu Bar App ───────────────────────────────────────────────────────

class ClairvoyantApp(rumps.App):
    """Menu bar app with live status from daemon via IPC."""

    def __init__(self):
        icon = str(ASSETS / "eye_22.png") if (ASSETS / "eye_22.png").exists() else None
        super().__init__(name="Clairvoyant-Optics", title="", icon=icon, quit_button=None)

        self._ipc = IPCClient()
        self._status = {"state": "disconnected", "cameras": {}, "last_detection": None}
        self._poll_thread: threading.Thread | None = None
        self._polling = False

        self._build_menu()
        self._connect_daemon()

    # ── Menu construction ───────────────────────────────────────────

    def _build_menu(self):
        self.menu.clear()

        # Status line (updates live)
        self._status_item = rumps.MenuItem("● Disconnected")
        self.menu.add(self._status_item)

        # Camera submenu
        self._cameras_menu = rumps.MenuItem("Cameras")
        self.menu.add(self._cameras_menu)

        self.menu.add(rumps.separator)

        # Start / Stop
        self._start_item = rumps.MenuItem("▶ Start")
        self._start_item.set_callback(self._on_start)
        self.menu.add(self._start_item)

        self._stop_item = rumps.MenuItem("⏸ Stop")
        self._stop_item.set_callback(self._on_stop)
        self.menu.add(self._stop_item)

        self.menu.add(rumps.separator)

        # Settings
        settings = rumps.MenuItem("Settings…", key="s")
        settings.set_callback(self._on_settings)
        self.menu.add(settings)

        # Web Dashboard
        web = rumps.MenuItem("Web Dashboard")
        web.set_callback(self._on_web)
        self.menu.add(web)

        self.menu.add(rumps.separator)

        # Quit
        quit_item = rumps.MenuItem("Quit Clairvoyant-Optics", key="q")
        quit_item.set_callback(self._on_quit)
        self.menu.add(quit_item)

    # ── Daemon connection ───────────────────────────────────────────

    def _connect_daemon(self):
        """Connect to daemon and start polling."""
        if self._ipc.connect():
            self._start_polling()

        # If daemon not running yet, try reconnecting
        if not self._ipc.connected:
            self._ipc.on_disconnect = self._on_daemon_disconnect
            t = threading.Thread(target=self._reconnect_loop, daemon=True)
            t.start()

    def _reconnect_loop(self):
        """Background attempt to reconnect to daemon."""
        deadline = time.time() + 60  # give it 60 seconds
        while time.time() < deadline and not self._ipc.connected:
            time.sleep(2)
            if self._ipc.connect():
                self._start_polling()
                return

    def _start_polling(self):
        """Start 2-second status polling."""
        if self._polling:
            return
        self._polling = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _poll_loop(self):
        """Poll daemon status every 2 seconds."""
        while self._polling and self._ipc.connected:
            resp = self._ipc.call("status", timeout=3)
            if "result" in resp:
                self._status = resp["result"]
                self._update_ui()
            elif "error" in resp:
                self._status = {"state": "error", "cameras": {}, "error": resp["error"].get("message", "Unknown")}
                self._update_ui()
            time.sleep(2)

    def _on_daemon_disconnect(self):
        """Callback when daemon disconnects."""
        self._polling = False
        self._status = {"state": "disconnected", "cameras": {}}
        self._update_ui()

    # ── UI updates ──────────────────────────────────────────────────

    def _update_ui(self):
        """Refresh menu items based on current _status. Called from poll thread."""
        state = self._status.get("state", "disconnected")
        cameras = self._status.get("cameras", {})
        last = self._status.get("last_detection")

        # Status icon/text
        emoji, color_prefix = {
            "running":      ("●", "green"),
            "starting":     ("◐", "yellow"),
            "stopping":     ("◑", "yellow"),
            "idle":         ("○", "gray"),
            "error":        ("◉", "red"),
            "disconnected": ("✕", "gray"),
        }.get(state, ("?", "gray"))

        self._status_item.title = f"{emoji} {state.title()}"

        # Camera submenu
        self._cameras_menu.clear()
        if cameras:
            for name, cs in cameras.items():
                icon = "✅" if cs.get("connected") else "⚠"
                item = rumps.MenuItem(f"  {icon} {name}")
                self._cameras_menu.add(item)
        else:
            self._cameras_menu.add(rumps.MenuItem("  (no cameras)"))

        # Start/Stop enabled state
        self._start_item.set_callback(None if state == "running" else self._on_start)
        self._stop_item.set_callback(None if state in ("idle", "stopped", "error", "disconnected") else self._on_stop)

        # Icon color (rumps doesn't support dynamic icon color natively,
        # but we could swap icon files. For v5.0: text in menu is enough.)

    # ── Actions ─────────────────────────────────────────────────────

    def _on_start(self, sender):
        resp = self._ipc.call("start")
        if "error" in resp:
            rumps.notification(
                title="Clairvoyant-Optics",
                subtitle="Start failed",
                message=resp["error"].get("message", "Unknown error"),
            )

    def _on_stop(self, sender):
        resp = self._ipc.call("stop")
        if "error" in resp:
            rumps.notification(
                title="Clairvoyant-Optics",
                subtitle="Stop failed",
                message=resp["error"].get("message", "Unknown error"),
            )

    def _on_settings(self, sender):
        """Open Settings.app (GUI for config)."""
        if IS_BUNDLED and SETTINGS_APP and SETTINGS_APP.exists():
            import subprocess
            subprocess.run(["open", "-a", str(SETTINGS_APP)], check=False)
        else:
            # Dev mode: run settings.py directly
            import subprocess
            settings_script = PROJECT_ROOT / "src" / "macos" / "settings.py"
            if settings_script.exists():
                subprocess.Popen(
                    [sys.executable, str(settings_script)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            else:
                rumps.notification(
                    title="Clairvoyant-Optics",
                    subtitle="Settings not available",
                    message="Settings.app or settings.py not found",
                )

    def _on_web(self, sender):
        """Open web dashboard in browser."""
        cfg_resp = self._ipc.call("config.get", {"section": "web"})
        host = "127.0.0.1"
        port = 8765
        if "result" in cfg_resp and cfg_resp["result"]:
            host = cfg_resp["result"].get("host", host)
            port = cfg_resp["result"].get("port", port)
        url = f"http://{host}:{port}"
        import subprocess
        subprocess.run(["open", url], check=False)

    def _on_quit(self, sender):
        self._polling = False
        self._ipc.close()
        rumps.quit_application()


# ── Main ───────────────────────────────────────────────────────────────

def main():
    if rumps is None:
        print("ERROR: rumps not installed. Run: pip install rumps", file=sys.stderr)
        sys.exit(1)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    ClairvoyantApp().run()


if __name__ == "__main__":
    main()
