"""MQTT-integraatio Home Assistantiin paho-mqtt:llä."""

import json
import logging
import time
from typing import Optional
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTNotifier:
    """Lähettää tunnistustapahtumat MQTT:lla Home Assistantiin."""

    def __init__(
        self,
        broker: str,
        port: int = 1883,
        username: str = "",
        password: str = "",
        topic_prefix: str = "clairvoyant",
        availability_topic: str = "status",
    ):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.topic_prefix = topic_prefix
        self.availability_topic = f"{topic_prefix}/{availability_topic}"

        self._client: Optional[mqtt.Client] = None
        self._connected = False

    def connect(self) -> bool:
        """Muodosta yhteys MQTT-brokeriin."""
        if not self.broker:
            logger.warning("MQTT broker not configured, skipping")
            return False

        self._client = mqtt.Client(
            client_id=f"clairvoyant-{int(time.time())}",
            protocol=mqtt.MQTTv5,
        )

        if self.username:
            self._client.username_pw_set(self.username, self.password)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        # LWT (Last Will Testament) — ilmoita kun yhteys katkeaa
        self._client.will_set(
            self.availability_topic,
            payload="offline",
            qos=1,
            retain=True,
        )

        try:
            self._client.connect(self.broker, self.port, keepalive=60)
            self._client.loop_start()
            logger.info(f"MQTT connected to {self.broker}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")
            return False

    def disconnect(self) -> None:
        """Sulje MQTT-yhteys."""
        if self._client:
            self._client.publish(self.availability_topic, "offline", qos=1, retain=True)
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
        self._connected = False

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if reason_code == 0:
            self._connected = True
            logger.info("MQTT connection established")
            # Ilmoita online-status
            client.publish(self.availability_topic, "online", qos=1, retain=True)
        else:
            logger.error(f"MQTT connection failed with reason code: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None) -> None:
        self._connected = False
        if reason_code != 0:
            logger.warning(f"MQTT unexpected disconnect (reason: {reason_code})")

    def notify_person_detected(
        self,
        person_name: str,
        camera: str,
        confidence: float,
        timestamp: Optional[str] = None,
    ) -> None:
        """Ilmoita henkilön tunnistuksesta Home Assistantiin.

        Lähettää JSON-payloadin muodossa:
        {
            "name": "Matti",
            "camera": "etupiha",
            "confidence": 0.92,
            "timestamp": "2026-05-08T19:00:00+00:00"
        }
        """
        if not self._connected or self._client is None:
            return

        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        topic = f"{self.topic_prefix}/{camera}/person"

        payload = {
            "name": person_name,
            "camera": camera,
            "confidence": round(confidence, 3),
            "timestamp": timestamp,
        }

        result = self._client.publish(topic, json.dumps(payload), qos=1, retain=False)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"MQTT → {topic}: {person_name} (conf: {confidence:.2f})")
        else:
            logger.warning(f"MQTT publish failed: {result.rc}")

    def notify_unknown_person(self, camera: str, bbox: tuple) -> None:
        """Ilmoita tunnistamattomasta henkilöstä."""
        if not self._connected or self._client is None:
            return

        timestamp = datetime.now(timezone.utc).isoformat()
        topic = f"{self.topic_prefix}/{camera}/unknown"

        payload = {
            "camera": camera,
            "timestamp": timestamp,
            "bbox": list(bbox),
        }

        self._client.publish(topic, json.dumps(payload), qos=1, retain=False)
        logger.info(f"MQTT → {topic}: unknown person detected")

    def notify_person_gone(self, person_name: str, camera: str) -> None:
        """Ilmoita kun henkilö poistui kuvasta."""
        if not self._connected or self._client is None:
            return

        timestamp = datetime.now(timezone.utc).isoformat()
        topic = f"{self.topic_prefix}/{camera}/person_gone"

        payload = {
            "name": person_name,
            "camera": camera,
            "timestamp": timestamp,
        }

        self._client.publish(topic, json.dumps(payload), qos=1, retain=False)

    @property
    def is_connected(self) -> bool:
        return self._connected
