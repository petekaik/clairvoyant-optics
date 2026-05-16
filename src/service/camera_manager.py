"""Camera manager stub for Clairvoyant-Optics v5.1.

Placeholder until HLS/RTSP stream support is enabled (requires cv2).
All methods are no-ops that return safe defaults.
"""

import logging
import threading
from typing import Any, Optional

logger = logging.getLogger("clairvoyantd.cameras")


class CameraManager:
    """Graceful stub — reports no cameras, no errors."""

    def __init__(self, cameras: list[Any], orchestrator):
        self._cameras = cameras
        self._orchestrator = orchestrator
        self._readers: dict[str, Any] = {}
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        if not self._cameras:
            logger.info("No cameras configured — CameraManager idle")
            return
        logger.info(f"CameraManager stub: {len(self._cameras)} camera(s) configured, streams not started (cv2 missing)")

    def stop(self) -> None:
        self._running = False
        self._readers.clear()

    def get_snapshot(self, camera_name: str) -> Optional[bytes]:
        return None
