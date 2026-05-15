"""Battery and WiFi monitor for Clairvoyant-Optics v5.0.

Monitors power status and WiFi SSID on macOS via pmset + airport CLI.
Notifies Orchestrator of state changes for auto-suspend/resume.
"""

import logging
import re
import subprocess
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("clairvoyantd.battery")


class BatteryManager:
    """Monitors battery and WiFi, notifies Orchestrator of changes."""

    def __init__(self, orchestrator, config_store: Any):
        self._orchestrator = orchestrator
        self._config_store = config_store
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._was_suspended = False

        # Last known state
        self._last_on_power: Optional[bool] = None
        self._last_ssid: Optional[str] = None
        self._last_is_home: Optional[bool] = None

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Start monitoring in background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="battery-monitor")
        self._thread.start()
        logger.info("BatteryManager started")

    def stop(self) -> None:
        """Stop monitoring."""
        self._running = False

    def update_config(self, new_config: Any) -> None:
        """Hot-update from config reload."""
        pass  # Config read from config_store on each poll

    # ── Monitor loop ─────────────────────────────────────────────────

    def _monitor_loop(self) -> None:
        """Poll battery and WiFi state every 30 seconds."""
        while self._running:
            cfg = self._config_store.config
            poll = cfg.battery.poll_interval if hasattr(cfg, 'battery') else 30

            if cfg.battery.pause_on_battery:
                self._check_battery(cfg)

            if cfg.battery.pause_when_away and cfg.battery.home_ssids:
                self._check_wifi(cfg)

            time.sleep(poll)

    def _check_battery(self, cfg: Any) -> None:
        """Check AC vs battery via pmset."""
        try:
            result = subprocess.run(
                ["pmset", "-g", "batt"],
                capture_output=True, text=True, timeout=5,
            )
            on_power = "AC Power" in result.stdout
            pct = None
            for match in re.finditer(r"(\d+)%", result.stdout):
                pct = int(match.group(1))
                break

            self._orchestrator.on_battery_change(on_power, pct)

            # Suspend/resume logic
            if self._last_on_power is not None and on_power != self._last_on_power:
                if not on_power and not self._was_suspended:
                    self._orchestrator.on_battery_suspend("On battery")
                    self._was_suspended = True
                elif on_power and self._was_suspended:
                    self._orchestrator.on_battery_resume()
                    self._was_suspended = False

            self._last_on_power = on_power

        except Exception:
            logger.debug("Battery check failed", exc_info=True)

    def _check_wifi(self, cfg: Any) -> None:
        """Check WiFi SSID via airport CLI."""
        try:
            result = subprocess.run(
                ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
                capture_output=True, text=True, timeout=5,
            )
            ssid = None
            for line in result.stdout.split("\n"):
                if " SSID:" in line:
                    ssid = line.split(":", 1)[1].strip()
                    break

            is_home = ssid in cfg.battery.home_ssids if ssid and cfg.battery.home_ssids else True

            self._orchestrator.on_wifi_change(ssid, is_home)

            # Suspend/resume logic
            if self._last_is_home is not None and is_home != self._last_is_home:
                if not is_home and not self._was_suspended:
                    self._orchestrator.on_battery_suspend(f"Away from home WiFi (SSID: {ssid})")
                    self._was_suspended = True
                elif is_home and self._was_suspended:
                    self._orchestrator.on_battery_resume()
                    self._was_suspended = False

            self._last_ssid = ssid
            self._last_is_home = is_home

        except Exception:
            logger.debug("WiFi check failed", exc_info=True)
