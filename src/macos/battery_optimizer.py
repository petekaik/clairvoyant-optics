"""Akunhallinta ja WiFi-pohjainen Home/Away -tila.

Pysäyttää tunnistusputken kun:
- Läppäri on akulla (ei laturissa) — Battery Saver
- WiFi-verkko ei ole kotiverkko — Away Mode

Palauttaa putken automaattisesti kun tila normalisoituu.
Käyttäjän manuaalinen start/stop ohittaa automaattiset säännöt.
"""

import logging
import re
import subprocess
import threading
import time

logger = logging.getLogger(__name__)


class BatteryOptimizer:
    """Valvoo akkua ja WiFi-verkkoa, ohjaa putken käynnistystä."""

    def __init__(
        self,
        pipeline=None,
        *,
        pause_on_battery: bool = False,
        home_ssids: list[str] | None = None,
        pause_when_away: bool = False,
        poll_interval: int = 30,
    ):
        self.pipeline = pipeline
        self.pause_on_battery = pause_on_battery
        self.home_ssids = home_ssids or []
        self.pause_when_away = pause_when_away
        self.poll_interval = poll_interval

        self._running = False
        self._thread: threading.Thread | None = None
        self._manual_override = False

        # Tila (näkyviin menubariin ja dashboardiin)
        self.suspended_reason: str | None = None
        self.is_on_power: bool = True
        self.is_home_wifi: bool = True
        self._last_battery_pct: float | None = None
        self._last_ssid: str | None = None

    @property
    def should_run(self) -> bool:
        """Pitäisikö putken olla päällä?"""
        if self._manual_override:
            return True

        if self.pause_on_battery and not self.is_on_power:
            self.suspended_reason = "On battery"
            return False

        if self.pause_when_away and not self.is_home_wifi:
            self.suspended_reason = "Away from home WiFi"
            return False

        self.suspended_reason = None
        return True

    def start(self):
        """Käynnistä valvontasäie."""
        if self._running:
            return
        if not self.pause_on_battery and not self.pause_when_away:
            return  # Ei mitään valvottavaa

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("BatteryOptimizer started")

    def stop(self):
        """Pysäytä valvonta."""
        self._running = False

    # ── Internal monitoring ────────────────────────────────────────────

    def _monitor_loop(self):
        """Päävalvontasilmukka."""
        while self._running:
            self._check_battery()
            self._check_wifi()
            self._apply_state()
            time.sleep(self.poll_interval)

    def _check_battery(self):
        """Lue akun tila macOS:lta (pmset)."""
        try:
            result = subprocess.run(
                ["pmset", "-g", "batt"],
                capture_output=True, text=True, timeout=5,
            )
            output = result.stdout
            self.is_on_power = "AC Power" in output

            for line in output.split("\n"):
                m = re.search(r"(\d+)%", line)
                if m:
                    self._last_battery_pct = int(m.group(1))
                    break
        except Exception as e:
            logger.debug(f"Battery check failed: {e}")

    def _check_wifi(self):
        """Lue WiFi SSID macOS:lta."""
        if not self.pause_when_away:
            return

        try:
            result = subprocess.run(
                ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.split("\n"):
                if " SSID:" in line:
                    self._last_ssid = line.split(":", 1)[1].strip()
                    break

            if self.home_ssids:
                self.is_home_wifi = self._last_ssid in self.home_ssids
            else:
                self.is_home_wifi = True
        except Exception as e:
            logger.debug(f"WiFi check failed: {e}")

    def _apply_state(self):
        """Automaattinen pause/resume akun ja WiFi:n perusteella."""
        if self.pipeline is None:
            return

        if not self.pipeline._running:
            self._manual_override = False

        if self._manual_override:
            return

        if self.pipeline._running and not self.should_run:
            logger.info(f"Auto-pausing: {self.suspended_reason}")
            self.pipeline.stop()

        elif not self.pipeline._running and self.should_run and self.suspended_reason is None:
            logger.info("Auto-resuming: conditions normal")
            self._manual_override = True
            t = threading.Thread(target=self.pipeline.start, daemon=True)
            t.start()
