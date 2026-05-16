"""ML manager stub for Clairvoyant-Optics v5.1.

Placeholder until ML models (YOLO, InsightFace) are available.
All methods are no-ops that return safe defaults.
"""

import logging
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("clairvoyantd.ml")


class MLManager:
    """Graceful stub — reports no detections, no errors."""

    def __init__(self, config: Any, models_dir: Path, orchestrator, camera_manager):
        self._config = config
        self._models_dir = models_dir
        self._orchestrator = orchestrator
        self._camera_manager = camera_manager
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.person_detector = None
        self.face_recognizer = None
        self.face_db = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        logger.info("MLManager stub started — ML models not loaded (ONNX/CoreML not bundled)")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def update_config(self, new_config: Any) -> None:
        self._config = new_config
