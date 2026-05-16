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

try:
    from src.version import VERSION
except ImportError:
    VERSION = "5.1.0"

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

# ── Web Server ─────────────────────────────────────────────────────────────

_web_server_pid: int | None = None


def _spawn_web_server(bundle_resources: Path, python_bin: Path, is_bundled: bool) -> int | None:
    """Spawn the web dashboard server. Returns PID or None."""
    import subprocess

    if is_bundled:
        web_script = bundle_resources / "web_dashboard.py"
    else:
        web_script = PROJECT_ROOT / "src" / "desktop" / "web_dashboard.py"

    if not web_script.exists():
        return None

    try:
        proc = subprocess.Popen(
            [str(python_bin), str(web_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return proc.pid
    except Exception:
        return None

# ── Menu Bar App ───────────────────────────────────────────────────────

class ClairvoyantApp(rumps.App):
    """Menu bar app with live status from daemon via IPC."""

    def __init__(self):
        icon = str(ASSETS / "eye_22.png") if (ASSETS / "eye_22.png").exists() else None
        super().__init__(name="Clairvoyant-Optics", title="", icon=icon, quit_button=None)

        # Spawn web dashboard server
        global _web_server_pid
        if _web_server_pid is None:
            self._start_web_server()

        self._ipc = IPCClient()
        self._status = {"state": "disconnected", "cameras": {}, "last_detection": None}
        self._poll_thread: threading.Thread | None = None
        self._polling = False

        self._build_menu()
        self._connect_daemon()

    # ── Web server management ───────────────────────────────────────

    def _start_web_server(self):
        """Spawn web dashboard as background process."""
        global _web_server_pid
        bundle_resources = Path(__file__).resolve().parent
        if IS_BUNDLED:
            python_bin = bundle_resources.parent / "MacOS" / "python"
        else:
            python_bin = Path(sys.executable)
        pid = _spawn_web_server(bundle_resources, python_bin, IS_BUNDLED)
        if pid:
            _web_server_pid = pid

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
        """Connect to daemon, spawning it if necessary."""
        if self._ipc.connect():
            self._start_polling()
            return

        # Spawn daemon as background process
        daemon_started = self._spawn_daemon()
        if daemon_started:
            # Wait for daemon socket to appear
            deadline = time.time() + 15
            while time.time() < deadline and not self._ipc.connected:
                time.sleep(0.5)
                if self._ipc.connect():
                    self._start_polling()
                    return

        # Fallback: keep trying reconnect
        if not self._ipc.connected:
            self._ipc.on_disconnect = self._on_daemon_disconnect
            t = threading.Thread(target=self._reconnect_loop, daemon=True)
            t.start()

    def _spawn_daemon(self) -> bool:
        """Spawn clairvoyantd as a background process. Returns True if started."""
        import subprocess

        if IS_BUNDLED:
            # Bundle mode: daemon.py is at Resources/lib/python3.11/src/service/daemon.py
            bundle_resources = Path(__file__).resolve().parent
            daemon_script = bundle_resources / "lib" / "python3.11" / "src" / "service" / "daemon.py"
            python_bin = bundle_resources.parent / "MacOS" / "python"
        else:
            daemon_script = PROJECT_ROOT / "src" / "service" / "daemon.py"
            python_bin = sys.executable

        if not daemon_script.exists():
            return False

        try:
            subprocess.Popen(
                [str(python_bin), str(daemon_script)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except Exception:
            return False

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
        # Try SIGUSR1 first if settings.py is already running (withdrawn)
        settings_pid_file = CONFIG_DIR / "settings.pid"
        if settings_pid_file.exists():
            try:
                pid = int(settings_pid_file.read_text().strip())
                os.kill(pid, 0)  # check if alive
                os.kill(pid, signal.SIGUSR1)
                return
            except Exception:
                pass

        if IS_BUNDLED and SETTINGS_APP and SETTINGS_APP.exists():
            import subprocess
            subprocess.run(["open", "-a", str(SETTINGS_APP)], check=False)
        else:
            # Dev mode: run settings.py directly
            import subprocess
            settings_script = PROJECT_ROOT / "src" / "desktop" / "settings.py"
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
        # Kill daemon
        global _web_server_pid
        import subprocess
        try:
            subprocess.run(["pkill", "-f", "daemon.py"], timeout=3, check=False)
        except Exception:
            pass
        # Kill web server
        if _web_server_pid:
            try:
                subprocess.run(["kill", str(_web_server_pid)], timeout=3, check=False)
            except Exception:
                pass
            _web_server_pid = None
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
