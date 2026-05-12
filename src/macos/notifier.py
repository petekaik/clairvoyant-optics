"""macOS-notifikaatiot — perheenjäsen vs hälytys.

Käyttää osascript display notification -komentoa (natiivi macOS, nolla Python-riippuvuutta).
"""

import logging
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)


class MacNotifier:
    """macOS-järjestelmänotifikaatiot. Nolla ulkoista riippuvuutta."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.sound_family = self.config.get("notification_sound_family", "default")
        self.sound_alert = self.config.get("notification_sound_alert", "alarm")
        self.dnd_start = self.config.get("notification_dnd_start", "")
        self.dnd_end = self.config.get("notification_dnd_end", "")

    @property
    def available(self) -> bool:
        return True  # osascript on aina macOS:llä

    def notify_family(self, name: str, camera: str, confidence: float = 0.0) -> bool:
        if self._in_dnd():
            return False
        subtitle = f"Camera: {camera}"
        if confidence > 0:
            subtitle += f" — {confidence:.0%} confidence"
        try:
            subprocess.run([
                "osascript", "-e",
                f'display notification "{subtitle}" with title "🏠 {name}" sound name "{self.sound_family}"'
            ], capture_output=True, timeout=5)
            return True
        except Exception as e:
            logger.error(f"Family notification failed: {e}")
            return False

    def notify_alert(self, camera: str, snapshot_path: str | None = None) -> bool:
        if self._in_dnd():
            return False
        try:
            subprocess.run([
                "osascript", "-e",
                f'display notification "Camera: {camera}" with title "⚠️ Unknown Person" sound name "{self.sound_alert}"'
            ], capture_output=True, timeout=5)
            return True
        except Exception as e:
            logger.error(f"Alert failed: {e}")
            return False

    def _in_dnd(self) -> bool:
        if not self.dnd_start or not self.dnd_end:
            return False
        now = datetime.now().time()
        try:
            start = datetime.strptime(self.dnd_start, "%H:%M").time()
            end = datetime.strptime(self.dnd_end, "%H:%M").time()
        except ValueError:
            return False
        if start <= end:
            return start <= now <= end
        return now >= start or now <= end
