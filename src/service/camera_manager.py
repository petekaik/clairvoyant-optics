"""Camera manager with OpenCV HLS stream support.

Manages multiple HLSStreamReader instances, provides snapshots
and reports per-camera status to Orchestrator.
"""

import cv2
import logging
import threading
import time
from typing import Optional

from src.streams.hls_reader import HLSStreamReader

logger = logging.getLogger("clairvoyantd.cameras")


class CameraManager:
    """Manages multiple HLS camera streams."""

    def __init__(self, cameras: list[dict], orchestrator):
        self._cameras_config = cameras
        self._orchestrator = orchestrator
        self._readers: dict[str, HLSStreamReader] = {}
        self._running = False
        self._lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        for cam_cfg in self._cameras_config:
            name = cam_cfg.get("name", "unnamed")
            stream_url = cam_cfg.get("stream_url", "")
            if not stream_url or not cam_cfg.get("enabled", True):
                logger.info(f"[{name}] Skipped (no URL or disabled)")
                continue
            reader = HLSStreamReader(
                stream_url=stream_url,
                name=name,
                max_reconnect_attempts=10,
                reconnect_base_delay=2.0,
            )
            self._readers[name] = reader
            reader.start()
            logger.info(f"[{name}] Started HLS stream: {stream_url}")
        # Monitor thread: report status every 5s
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info(f"CameraManager started: {len(self._cameras_config)} configured, {len(self._readers)} active")

    def stop(self) -> None:
        self._running = False
        for name, reader in self._readers.items():
            reader.stop()
        self._readers.clear()

    def get_snapshot(self, camera_name: str) -> Optional[bytes]:
        reader = self._readers.get(camera_name)
        if reader is None:
            return None
        result = reader.get_latest_frame()
        if result is None:
            return None
        frame, _ = result
        ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ret:
            return buf.tobytes()
        return None

    def get_reader(self, name: str) -> Optional[HLSStreamReader]:
        return self._readers.get(name)

    def _monitor_loop(self):
        while self._running:
            for name, reader in self._readers.items():
                connected = reader.is_connected
                fps = reader.fps
                self._orchestrator.on_camera_status(name, connected, fps)
            time.sleep(5)