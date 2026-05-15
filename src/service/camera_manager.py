"""Camera manager for Clairvoyant-Optics v5.0.

Manages HLSStreamReader instances, aggregates status, provides snapshots.
Lazy-loads src.streams.HLSStreamReader only when cameras are configured.
"""

import logging
import threading
from typing import Any, Optional

logger = logging.getLogger("clairvoyantd.cameras")


class CameraManager:
    """Orchestrates HLS streams for all configured cameras."""

    def __init__(self, cameras: list[Any], orchestrator):
        self._cameras = cameras
        self._orchestrator = orchestrator
        self._readers: dict[str, Any] = {}  # name → HLSStreamReader
        self._running = False
        self._lock = threading.Lock()

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Start all camera streams in background threads."""
        if self._running:
            return
        self._running = True

        if not self._cameras:
            logger.info("No cameras configured, CameraManager idle")
            return

        try:
            from src.streams.hls_reader import HLSStreamReader

            for cam in self._cameras:
                if not cam.enabled:
                    continue
                name = cam.name
                reader = HLSStreamReader(stream_url=cam.stream_url, name=name)
                self._readers[name] = reader
                reader.start()
                self._orchestrator.on_camera_status(name, True)

            logger.info(f"CameraManager started: {len(self._readers)} camera(s)")
        except ImportError:
            logger.warning("HLS stream support not available (opencv-python missing)")
        except Exception:
            logger.exception("Failed to start cameras")

    def stop(self) -> None:
        """Stop all camera streams."""
        self._running = False
        for name, reader in self._readers.items():
            try:
                reader.stop()
            except Exception:
                logger.exception(f"Error stopping camera: {name}")
        self._readers.clear()
        logger.info("CameraManager stopped")

    # ── Queries ──────────────────────────────────────────────────────

    def get_snapshot(self, camera_name: str) -> Optional[bytes]:
        """Get latest JPEG frame from a camera. Returns raw bytes or None."""
        reader = self._readers.get(camera_name)
        if reader is None:
            return None
        result = reader.get_latest_frame()
        if result is None:
            return None
        frame, _ = result
        try:
            import cv2
            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            return jpeg.tobytes()
        except ImportError:
            # Fallback: return raw BGR as bytes (not ideal)
            return frame.tobytes()
