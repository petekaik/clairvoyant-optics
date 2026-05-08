"""Konfiguraation lataus .env-tiedostosta."""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


@dataclass
class CameraConfig:
    stream_url: str
    snap_url: str
    name: str


@dataclass
class MQTTConfig:
    broker: str
    port: int
    username: str
    password: str
    topic_prefix: str


@dataclass
class ModelConfig:
    dir: Path
    yolo: Path
    face_detection: Path
    face_recognition: Path


@dataclass
class DetectionConfig:
    person_confidence: float
    face_confidence: float
    recognition_threshold: float
    frame_interval: int


@dataclass
class Config:
    cameras: list[CameraConfig]
    mqtt: MQTTConfig
    models: ModelConfig
    detection: DetectionConfig
    log_level: str
    project_root: Path = field(init=False)

    def __post_init__(self) -> None:
        self.project_root = Path(__file__).resolve().parent.parent


def load_config(env_path: Optional[Path] = None) -> Config:
    """Lataa konfiguraatio .env-tiedostosta.

    Jos env_path on annettu, ladataan kyseisestä tiedostosta.
    Muuten käytetään projektin juuressa olevaa .env-tiedostoa.
    """
    if env_path is None:
        # Etsi projektin juuri (2 tasoa ylös src/config.py:stä)
        project_root = Path(__file__).resolve().parent.parent
        env_path = project_root / ".env"

    if env_path.exists():
        _load_dotenv(env_path)

    models_dir = Path(_env("MODELS_DIR", "./models"))

    cameras = []
    # Tuki dynaamiselle määrälle kameroita (CAM1, CAM2, ...)
    for i in range(1, 10):
        stream = _env(f"CAM{i}_STREAM")
        if not stream:
            break
        snap = _env(f"CAM{i}_SNAP")
        name = _env(f"CAM{i}_NAME", f"camera{i}")
        cameras.append(CameraConfig(stream_url=stream, snap_url=snap, name=name))

    return Config(
        cameras=cameras,
        mqtt=MQTTConfig(
            broker=_env("MQTT_BROKER"),
            port=_env_int("MQTT_PORT", 1883),
            username=_env("MQTT_USERNAME"),
            password=_env("MQTT_PASSWORD"),
            topic_prefix=_env("MQTT_TOPIC_PREFIX", "clairvoyant"),
        ),
        models=ModelConfig(
            dir=models_dir,
            yolo=models_dir / _env("YOLO_MODEL", "yolov8n.onnx"),
            face_detection=models_dir / _env("FACE_DETECTION_MODEL", "det_10g.onnx"),
            face_recognition=models_dir / _env("FACE_RECOGNITION_MODEL", "w600k_r50.onnx"),
        ),
        detection=DetectionConfig(
            person_confidence=_env_float("PERSON_DETECT_CONFIDENCE", 0.5),
            face_confidence=_env_float("FACE_DETECT_CONFIDENCE", 0.7),
            recognition_threshold=_env_float("FACE_RECOGNITION_THRESHOLD", 0.6),
            frame_interval=_env_int("FRAME_INTERVAL", 5),
        ),
        log_level=_env("LOG_LEVEL", "INFO").upper(),
    )


def _load_dotenv(path: Path) -> None:
    """Yksinkertainen .env-lataaja ilman python-dotenv-riippuvuutta."""
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key not in os.environ:
                os.environ[key] = value
