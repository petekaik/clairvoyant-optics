"""Unified configuration store for Clairvoyant-Optics v5.0.

Single source of truth for all settings. Replaces:
- config.py (dataclass-based, .env loader)
- DEFAULTS dict in app.py
- DEFAULTS dict in settings.py

Reads/writes config.yaml from ~/.clairvoyant-optics/.
Supports hot-reload via SIGHUP signal.
"""

import logging
import os
import signal
import shutil
import threading
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("clairvoyantd.config")

CONFIG_DIR = Path.home() / ".clairvoyant-optics"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
CONFIG_BACKUP_DIR = CONFIG_DIR / "config-backups"

# ── Schema ─────────────────────────────────────────────────────────────

DEFAULT_CONFIG_YAML = """# Clairvoyant-Optics v5.0 Configuration
# Muokkaa Settings.app:sta (GUI) tai suoraan tästä tiedostosta.
# Service-layer (clairvoyantd) lataa tämän automaattisesti SIGHUP:lla.

general:
  log_level: INFO
  launch_at_login: false

cameras:
  # - name: etupiha
  #   stream_url: http://192.168.1.100:8080/hls/stream.m3u8
  #   snap_url: http://192.168.1.100:8080/snap.jpg
  #   enabled: true

detection:
  person_confidence: 0.5
  face_confidence: 0.7
  recognition_threshold: 0.6
  frame_interval: 5
  debounce_seconds: 30

models:
  dir: models
  yolo: yolov8n.onnx
  face_detection: det_10g.onnx
  face_recognition: w600k_r50.onnx

mqtt:
  broker: ""
  port: 1883
  username: ""
  password: ""
  topic_prefix: clairvoyant
  enabled: false

notifications:
  enabled: true
  notify_on_family: true
  notify_on_unknown: true
  sound_family: default
  sound_alert: alarm
  dnd_start: ""
  dnd_end: ""

battery:
  pause_on_battery: false
  home_ssids: []
  pause_when_away: false
  poll_interval: 30

telemetry:
  auto_update: false
  error_reporting: false

web:
  enabled: false
  host: 127.0.0.1
  port: 8765
"""


# ── Dataclasses ─────────────────────────────────────────────────────────

@dataclass
class CameraConfig:
    name: str
    stream_url: str = ""
    snap_url: str = ""
    enabled: bool = True


@dataclass
class GeneralConfig:
    log_level: str = "INFO"
    launch_at_login: bool = False


@dataclass
class DetectionConfig:
    person_confidence: float = 0.5
    face_confidence: float = 0.7
    recognition_threshold: float = 0.6
    frame_interval: int = 5
    debounce_seconds: int = 30


@dataclass
class ModelConfig:
    dir: str = "models"
    yolo: str = "yolov8n.onnx"
    face_detection: str = "det_10g.onnx"
    face_recognition: str = "w600k_r50.onnx"


@dataclass
class MQTTConfig:
    broker: str = ""
    port: int = 1883
    username: str = ""
    password: str = ""
    topic_prefix: str = "clairvoyant"
    enabled: bool = False


@dataclass
class NotificationConfig:
    enabled: bool = True
    notify_on_family: bool = True
    notify_on_unknown: bool = True
    sound_family: str = "default"
    sound_alert: str = "alarm"
    dnd_start: str = ""
    dnd_end: str = ""


@dataclass
class BatteryConfig:
    pause_on_battery: bool = False
    home_ssids: list[str] = field(default_factory=list)
    pause_when_away: bool = False
    poll_interval: int = 30


@dataclass
class TelemetryConfig:
    auto_update: bool = False
    error_reporting: bool = False


@dataclass
class WebConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass
class Config:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    cameras: list[CameraConfig] = field(default_factory=list)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    models: ModelConfig = field(default_factory=ModelConfig)
    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    battery: BatteryConfig = field(default_factory=BatteryConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    web: WebConfig = field(default_factory=WebConfig)


# ── YAML helpers ────────────────────────────────────────────────────────

def _ensure_yaml():
    """Try importing yaml, return the module or raise."""
    try:
        import yaml
        return yaml
    except ImportError:
        raise ImportError("PyYAML required: pip install pyyaml")


def _dict_to_dataclass(cls, data: dict) -> Any:
    """Recursively convert dict to dataclass instance."""
    if not is_dataclass(cls) or not isinstance(data, dict):
        return data
    field_types = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}
    for key, value in data.items():
        if key in field_types:
            target_type = field_types[key]
            if is_dataclass(target_type) and isinstance(value, dict):
                kwargs[key] = _dict_to_dataclass(target_type, value)
            elif hasattr(target_type, '__origin__') and target_type.__origin__ is list:
                # Handle list[CameraConfig], list[str], etc.
                item_type = target_type.__args__[0] if target_type.__args__ else str
                if is_dataclass(item_type) and isinstance(value, list):
                    kwargs[key] = [_dict_to_dataclass(item_type, item) if isinstance(item, dict) else item for item in value]
                else:
                    kwargs[key] = value
            else:
                kwargs[key] = value
    return cls(**kwargs)


# ── ConfigStore ─────────────────────────────────────────────────────────

class ConfigStore:
    """Thread-safe configuration store with hot-reload support."""

    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or CONFIG_FILE
        self._lock = threading.RLock()
        self._config: Config = Config()
        self._callbacks: list = []  # Called on reload: fn(new_config)
        self._change_callbacks: dict[str, list] = {}  # section → [fn(section, key, value)]
        self._load()
        logger.info(f"ConfigStore initialized: {self._config_path}")

    # ── Public API ──────────────────────────────────────────────────

    @property
    def config(self) -> Config:
        with self._lock:
            return self._config

    def get_all(self) -> dict:
        """Return full config as nested dict (for IPC serialization)."""
        return _dataclass_to_nested_dict(self.config)

    def get(self, section: str, key: Optional[str] = None) -> Any:
        """Get a config value. section='general', key='log_level' or key=None for whole section."""
        cfg = self.config
        section_obj = getattr(cfg, section, None)
        if section_obj is None:
            return None
        if key is None:
            return _dataclass_to_nested_dict(section_obj)
        return getattr(section_obj, key, None)

    def set(self, section: str, key: str, value: Any) -> bool:
        """Set a single config value, persist atomically. Returns True on success."""
        with self._lock:
            section_obj = getattr(self._config, section, None)
            if section_obj is None:
                logger.warning(f"Unknown config section: {section}")
                return False
            if not hasattr(section_obj, key):
                logger.warning(f"Unknown config key: {section}.{key}")
                return False

            # Type-coerce: match existing field type
            current = getattr(section_obj, key)
            value = _coerce_type(value, type(current))

            setattr(section_obj, key, value)
            self._persist()
            logger.info(f"Config updated: {section}.{key} = {value}")

            # Fire change callbacks for this section
            for cb in self._change_callbacks.get(section, []):
                try:
                    cb(section, key, value)
                except Exception:
                    logger.exception(f"Change callback failed for {section}.{key}")

            return True

    def set_section(self, section: str, data: dict) -> bool:
        """Replace an entire config section from dict."""
        with self._lock:
            if not hasattr(self._config, section):
                logger.warning(f"Unknown config section: {section}")
                return False
            cls = type(getattr(self._config, section))
            section_obj = _dict_to_dataclass(cls, data)
            setattr(self._config, section, section_obj)
            self._persist()
            logger.info(f"Config section updated: {section}")
            return True

    def reload(self) -> bool:
        """Force reload from disk. Returns True if config changed."""
        with self._lock:
            old = self._config
            try:
                self._load()
            except Exception:
                logger.exception("Reload failed, keeping current config")
                self._config = old
                return False

            if old != self._config:
                for cb in self._callbacks:
                    try:
                        cb(self._config)
                    except Exception:
                        logger.exception("Config reload callback failed")
                return True
            return False

    def on_reload(self, callback):
        """Register callback(new_config) called after each successful reload."""
        self._callbacks.append(callback)

    def on_change(self, section: str, callback):
        """Register callback(section, key, value) called after each set() update."""
        self._change_callbacks.setdefault(section, []).append(callback)

    def setup_sighup(self):
        """Register SIGHUP handler for hot-reload."""
        signal.signal(signal.SIGHUP, lambda signum, frame: self.reload())
        logger.info(f"SIGHUP handler registered (PID {os.getpid()})")

    # ── Internal ────────────────────────────────────────────────────

    def _load(self):
        """Load config from YAML file, with fallback to defaults."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        if not self._config_path.exists():
            self._write_default()
            self._config = Config()
            return

        yaml = _ensure_yaml()
        try:
            with open(self._config_path) as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to read {self._config_path}: {e} — using defaults")
            self._config = Config()
            return

        # Merge loaded data with defaults (handle missing sections)
        defaults = yaml.safe_load(DEFAULT_CONFIG_YAML) or {}
        for section in defaults:
            if section not in data:
                data[section] = defaults[section]

        self._config = _dict_to_dataclass(Config, data)

    def _persist(self):
        """Atomically write config to disk (write temp → rename)."""
        yaml = _ensure_yaml()
        data = _dataclass_to_nested_dict(self.config)

        tmp_path = self._config_path.with_suffix(".tmp")
        backup_path = self._config_path.with_suffix(".bak")

        try:
            with open(tmp_path, "w") as f:
                f.write("# Clairvoyant-Optics v5.0 Configuration\n")
                f.write(f"# Last modified: {datetime.now().isoformat()}\n\n")
                # Custom representer: strings that look like sexagesimal numbers or
                # contain colons must be quoted (prevents YAML 1.1 sexagesimal parsing)
                def str_representer(dumper, data):
                    if ":" in data or " " in data or any(c in data for c in "{}[]&*!|>\"'%@`"):
                        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")
                    return dumper.represent_scalar("tag:yaml.org,2002:str", data)
                yaml.add_representer(str, str_representer)
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

            # Keep one backup
            if self._config_path.exists():
                shutil.copy2(self._config_path, backup_path)

            # Atomic rename
            os.replace(tmp_path, self._config_path)

        except Exception:
            logger.exception("Failed to persist config")
            raise

    def _write_default(self):
        """Write default config if no file exists."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(DEFAULT_CONFIG_YAML)
        logger.info(f"Default config written: {self._config_path}")


# ── Helpers ─────────────────────────────────────────────────────────────

def _dataclass_to_nested_dict(obj) -> dict:
    """Convert dataclass hierarchy to nested dict for YAML/JSON."""
    if is_dataclass(obj):
        result = {}
        for f_name, f_def in obj.__dataclass_fields__.items():
            value = getattr(obj, f_name)
            result[f_name] = _dataclass_to_nested_dict(value)
        return result
    if isinstance(obj, list):
        return [_dataclass_to_nested_dict(item) for item in obj]
    return obj


def _coerce_type(value: Any, target_type: type) -> Any:
    """Coerce value to match target_type, or return as-is."""
    if target_type is bool and isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    if target_type is int and isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return value
    if target_type is float and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    if target_type is list and isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value
