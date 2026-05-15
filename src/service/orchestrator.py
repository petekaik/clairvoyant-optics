"""Orchestrator — state machine for Clairvoyant-Optics v5.0.

Manages the detection pipeline lifecycle:
  idle → starting → running → stopping → idle

Integrates CameraManager, MLManager, BatteryManager, NotificationBus.
All mutations are thread-safe via a single lock.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.service.config_store import Config, ConfigStore

logger = logging.getLogger("clairvoyantd.orchestrator")

State = str
STATE_IDLE = "idle"
STATE_STARTING = "starting"
STATE_RUNNING = "running"
STATE_STOPPING = "stopping"
STATE_ERROR = "error"

VALID_TRANSITIONS = {
    STATE_IDLE: {STATE_STARTING},
    STATE_STARTING: {STATE_RUNNING, STATE_ERROR, STATE_IDLE},
    STATE_RUNNING: {STATE_STOPPING, STATE_ERROR},
    STATE_STOPPING: {STATE_IDLE, STATE_ERROR},
    STATE_ERROR: {STATE_IDLE},
}


@dataclass
class CameraStatus:
    name: str
    connected: bool = False
    fps: float = 0.0
    last_frame: float = 0.0
    reconnect_attempts: int = 0


@dataclass
class DetectionEvent:
    camera: str
    person: str
    confidence: float
    timestamp: str


@dataclass
class PipelineState:
    state: State = STATE_IDLE
    cameras: dict[str, CameraStatus] = field(default_factory=dict)
    active_detections: int = 0
    last_detection: Optional[DetectionEvent] = None
    suspended_reason: Optional[str] = None
    is_on_power: bool = True
    battery_pct: Optional[float] = None
    ssid: Optional[str] = None
    is_home_wifi: bool = True
    uptime_seconds: float = 0.0
    started_at: Optional[float] = None
    error: Optional[str] = None


class Orchestrator:
    """Central orchestrator for the detection pipeline."""

    def __init__(self, config_store: ConfigStore):
        self._config_store = config_store
        self._lock = threading.RLock()
        self._state = PipelineState()
        self._config_store.on_reload(self._on_config_reload)

        # Sub-components (lazy-loaded on start)
        self.camera_manager = None  # CameraManager
        self.ml_manager = None      # MLManager
        self.notification_bus = None  # NotificationBus

        # Start battery monitoring immediately (always on)
        from src.service.battery_manager import BatteryManager
        self.battery_manager = BatteryManager(orchestrator=self, config_store=config_store)
        self.battery_manager.start()

        logger.info("Orchestrator initialized")

    # ── Public API ──────────────────────────────────────────────────

    @property
    def state(self) -> str:
        with self._lock:
            return self._state.state

    def get_status(self) -> dict:
        """Return full pipeline status as dict (for IPC)."""
        with self._lock:
            s = self._state
            return {
                "state": s.state,
                "cameras": {
                    name: {
                        "name": cs.name,
                        "connected": cs.connected,
                        "fps": cs.fps,
                        "reconnect_attempts": cs.reconnect_attempts,
                    }
                    for name, cs in s.cameras.items()
                },
                "active_detections": s.active_detections,
                "last_detection": {
                    "camera": s.last_detection.camera,
                    "person": s.last_detection.person,
                    "confidence": s.last_detection.confidence,
                    "timestamp": s.last_detection.timestamp,
                } if s.last_detection else None,
                "suspended_reason": s.suspended_reason,
                "is_on_power": s.is_on_power,
                "battery_pct": s.battery_pct,
                "ssid": s.ssid,
                "is_home_wifi": s.is_home_wifi,
                "uptime_seconds": s.uptime_seconds,
                "error": s.error,
            }

    def start(self) -> bool:
        """Initiate pipeline start. Returns True if transition started."""
        with self._lock:
            if self._state.state not in (STATE_IDLE, STATE_ERROR):
                logger.warning(f"Cannot start from state: {self._state.state}")
                return False
            self._transition(STATE_STARTING)

        # Run startup in background thread to not block the IPC handler
        t = threading.Thread(target=self._do_start, daemon=True, name="orchestrator-start")
        t.start()
        return True

    def stop(self) -> bool:
        """Initiate pipeline stop. Returns True."""
        with self._lock:
            if self._state.state not in (STATE_RUNNING, STATE_ERROR):
                logger.warning(f"Cannot stop from state: {self._state.state}")
                return False
            self._transition(STATE_STOPPING)

        t = threading.Thread(target=self._do_stop, daemon=True, name="orchestrator-stop")
        t.start()
        return True

    def get_camera_snapshot(self, camera_name: str) -> Optional[bytes]:
        """Get latest JPEG frame from a camera. Returns raw bytes or None."""
        if self.camera_manager is None:
            return None
        return self.camera_manager.get_snapshot(camera_name)

    # ── Internal callbacks (called by sub-components) ────────────────

    def on_camera_status(self, camera_name: str, connected: bool, fps: float = 0.0):
        """Called by CameraManager when camera status changes."""
        with self._lock:
            if camera_name not in self._state.cameras:
                self._state.cameras[camera_name] = CameraStatus(name=camera_name)
            cs = self._state.cameras[camera_name]
            cs.connected = connected
            cs.fps = fps
            cs.last_frame = time.time()

    def on_detection(self, event: DetectionEvent):
        """Called by MLManager on new detection."""
        with self._lock:
            self._state.last_detection = event
            self._state.active_detections += 1
            # Reset after a timeout? Simpler: just count.

    def on_person_gone(self, camera: str, person: str):
        """Called when person leaves frame."""
        with self._lock:
            if self._state.active_detections > 0:
                self._state.active_detections -= 1

    def on_battery_change(self, on_power: bool, pct: Optional[float]):
        """Called by BatteryManager."""
        with self._lock:
            self._state.is_on_power = on_power
            self._state.battery_pct = pct

    def on_wifi_change(self, ssid: Optional[str], is_home: bool):
        """Called by BatteryManager."""
        with self._lock:
            self._state.ssid = ssid
            self._state.is_home_wifi = is_home

    def on_battery_suspend(self, reason: str):
        """BatteryManager requests pipeline suspension."""
        with self._lock:
            if self._state.state == STATE_RUNNING:
                self._state.suspended_reason = reason
                self._transition(STATE_STOPPING)
                t = threading.Thread(target=self._do_stop, daemon=True)
                t.start()

    def on_battery_resume(self):
        """BatteryManager requests pipeline resume."""
        with self._lock:
            if self._state.state == STATE_IDLE and self._state.suspended_reason:
                self._state.suspended_reason = None
                self._transition(STATE_STARTING)
                t = threading.Thread(target=self._do_start, daemon=True)
                t.start()

    def on_error(self, error_msg: str):
        """Called by any sub-component on fatal error."""
        with self._lock:
            self._state.error = error_msg
            self._transition(STATE_ERROR)
        logger.error(f"Pipeline error: {error_msg}")

    # ── Internal ────────────────────────────────────────────────────

    def _transition(self, target: State):
        """Atomically transition state. No-op if invalid."""
        current = self._state.state
        if target not in VALID_TRANSITIONS.get(current, set()):
            logger.warning(f"Invalid transition: {current} → {target}")
            return
        old = current
        self._state.state = target
        logger.info(f"State: {old} → {target}")

    def _do_start(self):
        """Background: initialize and start detection pipeline."""
        try:
            cfg = self._config_store.config

            # Initialize CameraManager
            from src.service.camera_manager import CameraManager  # Lazy import
            self.camera_manager = CameraManager(
                cameras=cfg.cameras,
                orchestrator=self,
            )
            self.camera_manager.start()

            # Initialize MLManager (if models configured)
            project_root = Path(__file__).resolve().parent.parent.parent  # ~/projects/Clairvoyant-Optics
            models_dir = project_root / cfg.models.dir
            if not models_dir.exists():
                models_dir = project_root / "models"  # fallback

            from src.service.ml_manager import MLManager
            self.ml_manager = MLManager(
                config=cfg,
                models_dir=models_dir,
                orchestrator=self,
                camera_manager=self.camera_manager,
            )
            self.ml_manager.start()

            # Initialize NotificationBus
            from src.service.notification_bus import NotificationBus
            self.notification_bus = NotificationBus(config=cfg, orchestrator=self)
            self.notification_bus.start()

            with self._lock:
                self._state.started_at = time.time()
                self._state.error = None
                self._transition(STATE_RUNNING)

            logger.info("Pipeline started successfully")

        except Exception as e:
            logger.exception("Pipeline start failed")
            self.on_error(str(e))

    def _do_stop(self):
        """Background: gracefully stop detection pipeline."""
        try:
            for comp in [self.ml_manager, self.camera_manager, self.notification_bus]:
                if comp is not None:
                    try:
                        comp.stop()
                    except Exception:
                        logger.exception(f"Error stopping {comp.__class__.__name__}")

            self.ml_manager = None
            self.camera_manager = None
            self.notification_bus = None

            with self._lock:
                self._state.started_at = None
                self._state.uptime_seconds = 0.0
                if not self._state.suspended_reason:
                    self._state.error = None
                self._transition(STATE_IDLE)

            logger.info("Pipeline stopped")

        except Exception as e:
            logger.exception("Pipeline stop failed")
            self.on_error(str(e))

    def _on_config_reload(self, new_config: Config):
        """Called when config is reloaded (SIGHUP or IPC config.reload)."""
        logger.info("Config reloaded — updating running pipeline if active")
        with self._lock:
            if self._state.state == STATE_RUNNING:
                # Hot-update: ML confidence thresholds, battery settings
                if self.ml_manager:
                    self.ml_manager.update_config(new_config)
                if self.battery_manager:
                    self.battery_manager.update_config(new_config)
                if self.notification_bus:
                    self.notification_bus.update_config(new_config)
