"""ML Manager with lazy model loading + model download.

Loads YOLOv8n and InsightFace models on first pipeline start.
Downloads models from HuggingFace / GitHub releases if missing.
Reports model status to Orchestrator.
"""

import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("clairvoyantd.ml")

# Default model download URLs
MODEL_URLS = {
    "yolov8n.onnx": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.onnx",
    "det_10g.onnx": "https://github.com/deepinsight/insightface/releases/download/v0.7/det_10g.onnx",
    "w600k_r50.onnx": "https://github.com/deepinsight/insightface/releases/download/v0.7/w600k_r50.onnx",
}

MODEL_SIZES = {
    "yolov8n.onnx": 6_200_000,       # ~6.2 MB
    "det_10g.onnx": 17_300_000,      # ~17.3 MB
    "w600k_r50.onnx": 163_000_000,   # ~163 MB
}


class MLManager:
    """Manages ML model lifecycle: download, load, inference."""

    def __init__(self, config: Any, models_dir: Path, orchestrator, camera_manager):
        self._config = config
        self._models_dir = models_dir
        self._orchestrator = orchestrator
        self._camera_manager = camera_manager
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Lazy-loaded models
        self.person_detector = None
        self.face_recognizer = None
        self.face_db = None

        # Download state (shared across UI queries)
        self._download_progress: dict[str, float] = {}  # model_name → 0.0–100.0 or "complete"
        self._model_loaded: dict[str, bool] = {"yolo": False, "face_detection": False, "face_recognition": False}
        self._download_lock = threading.Lock()

    # ── Public status API (for UI) ──────────────────────────────────

    def get_model_status(self) -> dict:
        """Return model download/load status dict."""
        with self._download_lock:
            progress = dict(self._download_progress)
            loaded = dict(self._model_loaded)
        return {
            "progress": progress,
            "loaded": loaded,
            "models_dir": str(self._models_dir),
            "available": self._models_dir.exists() and any(
                (self._models_dir / name).exists()
                for name in ["yolov8n.onnx", "det_10g.onnx", "w600k_r50.onnx"]
            ),
        }

    def is_ready(self) -> bool:
        """All models downloaded and loaded."""
        with self._download_lock:
            return (self._model_loaded.get("yolo", False) and
                    self._model_loaded.get("face_detection", False) and
                    self._model_loaded.get("face_recognition", False))

    def download_model(self, model_name: str, callback=None) -> bool:
        """Download a single model in background thread. Returns True if started."""
        model_path = self._models_dir / model_name
        if model_path.exists():
            with self._download_lock:
                self._download_progress[model_name] = "complete"
            logger.info(f"Model already exists: {model_name}")
            return True
        url = MODEL_URLS.get(model_name)
        if not url:
            logger.error(f"No download URL for {model_name}")
            return False
        t = threading.Thread(target=self._do_download, args=(model_name, url), daemon=True)
        t.start()
        return True

    def download_all_models(self) -> None:
        """Download all missing models in parallel."""
        for name in ["yolov8n.onnx", "det_10g.onnx", "w600k_r50.onnx"]:
            model_path = self._models_dir / name
            if not model_path.exists():
                self.download_model(name)
            else:
                with self._download_lock:
                    self._download_progress[name] = "complete"

    # ── Lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._models_dir.mkdir(parents=True, exist_ok=True)

        # Start model loading in background
        self._thread = threading.Thread(target=self._load_all, daemon=True)
        self._thread.start()
        logger.info("MLManager starting — models will load in background")

    def _load_all(self) -> None:
        """Background: download missing models, then load ML pipeline."""
        # Step 1: Download missing models
        for name in ["yolov8n.onnx", "det_10g.onnx", "w600k_r50.onnx"]:
            model_path = self._models_dir / name
            if not model_path.exists():
                logger.info(f"Downloading {name} ({MODEL_SIZES.get(name, 0) / 1e6:.0f} MB)...")
                self.download_model(name)

        # Step 2: Wait for downloads to complete (max 5 minutes)
        deadline = time.time() + 300
        while time.time() < deadline:
            all_done = True
            for name in ["yolov8n.onnx", "det_10g.onnx", "w600k_r50.onnx"]:
                model_path = self._models_dir / name
                if not model_path.exists():
                    all_done = False
                    break
            if all_done:
                break
            time.sleep(2)

        # Step 3: Load models
        self._load_yolo()
        self._load_insightface()

    def _load_yolo(self) -> None:
        """Load YOLOv8 ONNX model for person detection."""
        model_path = self._models_dir / self._config.models.yolo
        if not model_path.exists():
            logger.warning(f"YOLO model not found: {model_path}")
            return
        try:
            from src.detection.person_detector import PersonDetector
            self.person_detector = PersonDetector(
                model_path=model_path,
                confidence_threshold=self._config.detection.person_confidence,
            )
            with self._download_lock:
                self._model_loaded["yolo"] = True
            logger.info("YOLOv8 person detector loaded")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")

    def _load_insightface(self) -> None:
        """Load InsightFace models for face detection + recognition."""
        det_path = self._models_dir / self._config.models.face_detection
        rec_path = self._models_dir / self._config.models.face_recognition
        if not det_path.exists() or not rec_path.exists():
            logger.warning(f"Face models not found: {det_path} / {rec_path}")
            return
        try:
            from src.recognition.face_recognizer import FaceDatabase, FaceRecognizer
            db_path = self._models_dir.parent / "faces.db"  # ~/.clairvoyant-optics/faces.db
            self.face_db = FaceDatabase(db_path=db_path)
            self.face_recognizer = FaceRecognizer(
                detection_model=det_path,
                recognition_model=rec_path,
                db=self.face_db,
                detection_confidence=self._config.detection.face_confidence,
                recognition_threshold=self._config.detection.recognition_threshold,
            )
            with self._download_lock:
                self._model_loaded["face_detection"] = True
                self._model_loaded["face_recognition"] = True
            logger.info("InsightFace face recognizer loaded")
        except Exception as e:
            logger.error(f"Failed to load face models: {e}")

    def stop(self) -> None:
        self._running = False
        self.person_detector = None
        self.face_recognizer = None

    def update_config(self, new_config: Any) -> None:
        self._config = new_config

    # ── Internal ────────────────────────────────────────────────────

    def _do_download(self, name: str, url: str) -> None:
        """Download model file with progress tracking."""
        model_path = self._models_dir / name
        tmp_path = model_path.with_suffix(".part")
        try:
            with self._download_lock:
                self._download_progress[name] = 0.0
            urllib.request.urlretrieve(url, tmp_path, reporthook=lambda b, bs, total: self._update_progress(name, b, bs, total))
            os.replace(tmp_path, model_path)
            with self._download_lock:
                self._download_progress[name] = "complete"
            total_mb = MODEL_SIZES.get(name, 0) / 1e6
            logger.info(f"Downloaded {name} ({total_mb:.0f} MB)")
        except Exception as e:
            logger.error(f"Download failed for {name}: {e}")
            if tmp_path.exists():
                tmp_path.unlink()
            with self._download_lock:
                self._download_progress[name] = -1.0  # error indicator

    def _update_progress(self, name: str, block: int, blocksize: int, total: int) -> None:
        """URL retrieve progress callback."""
        if total > 0:
            pct = min(100.0, block * blocksize / total * 100)
            with self._download_lock:
                self._download_progress[name] = round(pct, 1)