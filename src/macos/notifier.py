"""macOS-notifikaatiot — perheenjäsen vs hälytys.

Käyttää macos-notifications Python-pakettia (puhdas Python, ei pyobjc).
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_HAS_NOTIFICATIONS = False
try:
    from macos_notifications import Notification
    _HAS_NOTIFICATIONS = True
except ImportError:
    pass


class MacNotifier:
    """macOS-järjestelmänotifikaatiot kasvontunnistuksen tuloksille."""

    def __init__(self, config: dict | None = None):
        """
        Args:
            config: Notifikaatioasetukset:
                - sound_family: ääni perheenjäsenelle (oletus: "default")
                - sound_alert: ääni vieraalle (oletus: "alarm")
                - dnd_start: Do Not Disturb alku (HH:MM), None = ei käytössä
                - dnd_end: Do Not Disturb loppu (HH:MM)
        """
        self.config = config or {}
        self.sound_family = self.config.get("sound_family", "default")
        self.sound_alert = self.config.get("sound_alert", "alarm")
        self.dnd_start = self.config.get("dnd_start")
        self.dnd_end = self.config.get("dnd_end")

    @property
    def available(self) -> bool:
        return _HAS_NOTIFICATIONS

    def notify_family(self, name: str, camera: str, confidence: float = 0.0) -> bool:
        """Lähetä ilmoitus perheenjäsenen havainnosta.

        Args:
            name: Henkilön nimi
            camera: Kameran nimi
            confidence: Tunnistuksen varmuus (0-1)

        Returns:
            True jos onnistui.
        """
        if not _HAS_NOTIFICATIONS:
            logger.warning("macos-notifications not installed")
            return False
        if self._in_dnd():
            logger.debug(f"DND active — suppressing notification for {name}")
            return False

        try:
            Notification(
                title=f"🏠 {name}",
                subtitle=(
                    f"Camera: {camera} — {confidence:.0%} confidence"
                    if confidence > 0
                    else f"Camera: {camera}"
                ),
                sound=self.sound_family,
            ).send()
            logger.info(f"Family notification: {name} @ {camera}")
            return True
        except Exception as e:
            logger.error(f"Notification failed: {e}")
            return False

    def notify_alert(self, camera: str, snapshot_path: str | None = None) -> bool:
        """Lähetä hälytys tuntemattomasta henkilöstä.

        Args:
            camera: Kameran nimi
            snapshot_path: Polku snapshot-kuvaan (valinnainen)

        Returns:
            True jos onnistui.
        """
        if not _HAS_NOTIFICATIONS:
            logger.warning("macos-notifications not installed")
            return False
        if self._in_dnd():
            logger.debug(f"DND active — suppressing alert")
            return False

        try:
            notif = Notification(
                title="⚠️ Tuntematon henkilö",
                subtitle=f"Camera: {camera}",
                sound=self.sound_alert,
            )
            notif.send()
            logger.info(f"Alert: unknown person @ {camera}")
            return True
        except Exception as e:
            logger.error(f"Alert failed: {e}")
            return False

    def _in_dnd(self) -> bool:
        """Tarkista onko Do Not Disturb aktiivinen."""
        if not self.dnd_start or not self.dnd_end:
            return False

        from datetime import datetime

        now = datetime.now().time()
        start = datetime.strptime(self.dnd_start, "%H:%M").time()
        end = datetime.strptime(self.dnd_end, "%H:%M").time()

        if start <= end:
            return start <= now <= end
        else:
            # Yli keskiyön (esim. 22:00-07:00)
            return now >= start or now <= end
