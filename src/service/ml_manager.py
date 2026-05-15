"""ML manager for Clairvoyant-Optics v5.0.

Manages YOLOv8 person detection and InsightFace face recognition.
Coordinates with CameraManager for frame retrieval and Orchestrator for state.
"""

import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("clairvoyantd.ml")


class MLManager:
    """Manages ML inference pipeline: person detection → face recognition."""

    def __init__(self, config: Any, models_dir: Path, orchestrator, camera_manager):
        self._config = config
        self._models_dir = models_dir
        self._orchestrator = orchestrator
        self._camera_manager = camera_manager
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # ML components (lazy-initialized)
        self.person_detector = None
        self.face_recognizer = None
        self.face_db = None

        # Debounce state
        self._last_detection: dict[str, float] = {}
        self._active_persons: dict[str, set[str]] = {}

        logger.info("MLManager created (models loaded on first frame)")

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Start ML inference loop in background thread."""
        if self._running:
            return

        # Initialize face DB if not already done
        if self.face_db is None:
            from src.recognition.face_recognizer import FaceDatabase
            db_path = self._models_dir.parent / "data" / "faces.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.face_db = FaceDatabase(db_path)

        self._running = True
        self._thread = threading.Thread(target=self._inference_loop, daemon=True, name="ml-inference")
        self._thread.start()
        logger.info("MLManager started")

    def stop(self) -> None:
        """Stop inference loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        if self.face_db:
            try:
                self.face_db.close()
            except Exception:
                pass
        logger.info("MLManager stopped")

    def update_config(self, new_config: Any) -> None:
        """Hot-update ML thresholds from config reload."""
        self._config = new_config
        if self.person_detector:
            self.person_detector.confidence_threshold = new_config.detection.person_confidence
        if self.face_recognizer:
            self.face_recognizer.detection_confidence = new_config.detection.face_confidence
            self.face_recognizer.recognition_threshold = new_config.detection.recognition_threshold

    # ── Inference loop ───────────────────────────────────────────────

    def _inference_loop(self) -> None:
        """Background: process frames from cameras, run ML inference."""
        interval = self._config.detection.frame_interval
        frame_counter = 0

        # Lazy-init ML models on first iteration
        self._init_models()

        while self._running:
            frame_counter += 1
            if frame_counter % interval != 0:
                time.sleep(0.5)
                continue

            # Process each camera
            for cam in self._config.cameras:
                if not cam.enabled:
                    continue

                frame = self._camera_manager.get_snapshot(cam.name)
                if frame is None:
                    continue

                try:
                    import cv2
                    import numpy as np
                    img = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if img is None:
                        continue
                except ImportError:
                    continue

                # Person detection
                if self.person_detector:
                    persons = self.person_detector.detect(img)
                    if not persons:
                        continue

                # Face recognition (if models available)
                if self.face_recognizer:
                    results = self.face_recognizer.recognize_in_frame(img, cam.name)
                    for r in results:
                        name = r["name"]
                        conf = r["confidence"]

                        if name == "unknown":
                            from src.service.orchestrator import DetectionEvent
                            self._orchestrator.on_detection(DetectionEvent(
                                camera=cam.name, person="unknown", confidence=conf,
                                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                            ))
                            continue

                        # Debounce
                        key = f"{cam.name}:{name}"
                        now = time.time()
                        last = self._last_detection.get(key, 0)
                        if now - last < self._config.detection.debounce_seconds:
                            continue
                        self._last_detection[key] = now

                        from src.service.orchestrator import DetectionEvent
                        self._orchestrator.on_detection(DetectionEvent(
                            camera=cam.name, person=name, confidence=conf,
                            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        ))

            time.sleep(0.1)

    def _init_models(self) -> None:
        """Lazy-load ML models. Non-fatal if missing — runs in person-detection-only mode."""
        # Person detector (YOLOv8)
        try:
            from src.detection.person_detector import PersonDetector
            yolo_path = self._models_dir / self._config.models.yolo
            if yolo_path.exists():
                self.person_detector = PersonDetector(
                    model_path=yolo_path,
                    confidence_threshold=self._config.detection.person_confidence,
                )
                logger.info(f"Person detector loaded: {yolo_path}")
            else:
                logger.warning(f"YOLO model not found: {yolo_path} — person detection disabled")
        except Exception:
            logger.exception("Failed to load person detector")

        # Face recognizer (InsightFace)
        try:
            from src.recognition.face_recognizer import FaceRecognizer
            face_det = self._models_dir / self._config.models.face_detection
            face_rec = self._models_dir / self._config.models.face_recognition
            if face_det.exists() and face_rec.exists():
                self.face_recognizer = FaceRecognizer(
                    detection_model=face_det,
                    recognition_model=face_rec,
                    db=self.face_db,
                    detection_confidence=self._config.detection.face_confidence,
                    recognition_threshold=self._config.detection.recognition_threshold,
                )
                logger.info(f"Face recognizer loaded: {face_det}, {face_rec}")
            else:
                logger.warning("Face models not found — face recognition disabled")
        except Exception:
            logger.exception("Failed to load face recognizer")
