"""Notification bus for Clairvoyant-Optics v5.0.

Routes detection events to: macOS notifications, MQTT (Home Assistant).
Extensible: webhooks, Telegram, etc. can be added as notification channels.
"""

import logging
import threading
from typing import Any, Optional

logger = logging.getLogger("clairvoyantd.notifications")


class NotificationBus:
    """Fan-out bus for detection events → notification channels."""

    def __init__(self, config: Any, orchestrator):
        self._config = config
        self._orchestrator = orchestrator
        self._running = False
        self._mac_notifier = None
        self._mqtt_notifier = None

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Initialize notification channels."""
        self._running = True

        cfg = self._config

        # macOS notifications
        if cfg.notifications.enabled:
            try:
                from src.macos.notifier import MacNotifier
                self._mac_notifier = MacNotifier({
                    "notification_sound_family": cfg.notifications.sound_family,
                    "notification_sound_alert": cfg.notifications.sound_alert,
                    "notification_dnd_start": cfg.notifications.dnd_start,
                    "notification_dnd_end": cfg.notifications.dnd_end,
                })
                logger.info("macOS notifications enabled")
            except ImportError:
                logger.warning("macOS notifier not available")

        # MQTT (Home Assistant)
        if cfg.mqtt.enabled and cfg.mqtt.broker:
            try:
                from src.integration.mqtt_notifier import MQTTNotifier
                self._mqtt_notifier = MQTTNotifier(
                    broker=cfg.mqtt.broker,
                    port=cfg.mqtt.port,
                    username=cfg.mqtt.username,
                    password=cfg.mqtt.password,
                    topic_prefix=cfg.mqtt.topic_prefix,
                )
                if self._mqtt_notifier.connect():
                    logger.info(f"MQTT connected: {cfg.mqtt.broker}:{cfg.mqtt.port}")
            except Exception:
                logger.exception("MQTT connection failed")

    def stop(self) -> None:
        """Shutdown all notification channels."""
        self._running = False
        if self._mqtt_notifier:
            try:
                self._mqtt_notifier.disconnect()
            except Exception:
                pass
            self._mqtt_notifier = None
        logger.info("NotificationBus stopped")

    def update_config(self, new_config: Any) -> None:
        """Hot-update notification settings from config reload."""
        self._config = new_config

    # ── Notification triggers ────────────────────────────────────────

    def notify_family(self, name: str, camera: str, confidence: float) -> None:
        """Send family member detection notification."""
        cfg = self._config
        if not cfg.notifications.enabled or not cfg.notifications.notify_on_family:
            return

        # macOS
        if self._mac_notifier:
            try:
                self._mac_notifier.notify_family(name, camera, confidence)
            except Exception:
                logger.exception("macOS family notification failed")

        # MQTT
        if self._mqtt_notifier and self._mqtt_notifier.is_connected:
            try:
                self._mqtt_notifier.notify_person_detected(name, camera, confidence)
            except Exception:
                logger.exception("MQTT family notification failed")

    def notify_alert(self, camera: str) -> None:
        """Send unknown person alert."""
        cfg = self._config
        if not cfg.notifications.enabled or not cfg.notifications.notify_on_unknown:
            return

        if self._mac_notifier:
            try:
                self._mac_notifier.notify_alert(camera)
            except Exception:
                logger.exception("macOS alert notification failed")
