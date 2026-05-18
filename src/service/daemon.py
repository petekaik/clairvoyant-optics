#!/usr/bin/env python3
"""clairvoyantd — Clairvoyant-Optics v5.0 Service Daemon.

Entry point for the background service. Starts:
  1. ConfigStore (loads config.yaml)
  2. IPCServer (Unix domain socket, JSON newline-delimited)
  3. Orchestrator (state machine, pipeline lifecycle)

Runs forever until SIGTERM or SIGINT. Handles SIGHUP for config reload.
"""

import logging
import os
import signal
import sys
import time
import subprocess
from pathlib import Path

# Ensure project root is on path (for src.* imports when running standalone)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.service.config_store import ConfigStore, CONFIG_DIR, CameraConfig
from src.service.ipc_server import IPCServer
from src.service.orchestrator import Orchestrator

logger = logging.getLogger("clairvoyantd")

VERSION = "5.5.0"


_web_proc: subprocess.Popen | None = None


def _web_start(cfg_store) -> dict:
    global _web_proc
    if _web_proc and _web_proc.poll() is None:
        return {"result": {"running": True, "message": "already running"}}
    enabled = cfg_store.config.web.enabled
    host = cfg_store.config.web.host
    port = cfg_store.config.web.port
    script = find_web_dashboard_script()
    if not script:
        return {"error": {"message": "web_dashboard.py not found"}}
    try:
        _web_proc = subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"result": {"running": True, "pid": _web_proc.pid, "host": host, "port": port}}
    except Exception as e:
        return {"error": {"message": str(e)}}


def _web_stop() -> dict:
    global _web_proc
    if _web_proc and _web_proc.poll() is None:
        _web_proc.terminate()
        try:
            _web_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _web_proc.kill()
        _web_proc = None
        return {"result": {"running": False}}
    return {"result": {"running": False, "message": "was not running"}}


def find_web_dashboard_script() -> Path | None:
    # Bundle mode: Resources/lib/python3.11/src/desktop/web_dashboard.py
    # Dev mode: projektin src/desktop/web_dashboard.py
    candidates = []
    # Bundle mode
    bundle_resources = Path(__file__).resolve().parent.parent.parent / "desktop"
    candidates.append(bundle_resources / "web_dashboard.py")
    # Development mode
    candidates.append(Path(__file__).resolve().parent.parent / "desktop" / "web_dashboard.py")
    for c in candidates:
        if c.exists():
            return c
    return None


def setup_logging(log_level: str = "INFO"):
    """Configure logging to file + stderr."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = CONFIG_DIR / "clairvoyantd.log"

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stderr),
        ],
    )


def main():
    """Entry point."""
    setup_logging()
    logger.info(f"clairvoyantd v{VERSION} starting (PID {os.getpid()})")

    # 1. Config
    config_store = ConfigStore()
    config_store.setup_sighup()

    # 2. Orchestrator
    orchestrator = Orchestrator(config_store)

    # 3. IPC Server
    ipc = IPCServer()
    ipc.register_methods(_build_ipc_methods(config_store, orchestrator))
    ipc.start()

    # 4. Shutdown handler
    running = True

    def _shutdown(signum=None, frame=None):
        nonlocal running
        running = False
        logger.info("Shutdown signal received")

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("clairvoyantd ready — awaiting IPC commands")

    # Main loop: keep alive until shutdown signal
    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    logger.info("Shutting down...")
    orchestrator.stop()
    ipc.stop()
    config_store._config_path = None  # no-op but satisfies cleanup
    logger.info("clairvoyantd stopped")


def _build_ipc_methods(config_store: ConfigStore, orchestrator: Orchestrator) -> dict:
    """Build IPC method handlers bound to config_store and orchestrator."""

    from src.service.ipc_server import IPCError

    def status(params: dict) -> dict:
        return orchestrator.get_status()

    def start(params: dict) -> dict:
        ok = orchestrator.start()
        if not ok:
            raise IPCError(IPCError.SERVER_ERROR, "Cannot start: pipeline already running or in error state")
        return {"started": True}

    def stop(params: dict) -> dict:
        ok = orchestrator.stop()
        if not ok:
            raise IPCError(IPCError.SERVER_ERROR, "Cannot stop: pipeline not running")
        return {"stopped": True}

    def config_get(params: dict) -> dict:
        section = params.get("section")
        key = params.get("key")
        return config_store.get(section, key) if section else config_store.get_all()

    def config_set(params: dict) -> dict:
        section = params.get("section")
        key = params.get("key")
        value = params.get("value")
        if not section or not key:
            raise IPCError(IPCError.INVALID_PARAMS, "section and key required")

        # ── Special case: cameras is a list, not a dataclass attr ───
        if section == "cameras" and key == "cameras":
            if not isinstance(value, list):
                raise IPCError(IPCError.INVALID_PARAMS, "cameras must be a list")
            camera_objs = [CameraConfig(**c) for c in value if isinstance(c, dict)]
            with config_store._lock:
                config_store._config.cameras = camera_objs
                config_store._persist()
            logger.info(f"Cameras updated: {len(camera_objs)} cameras")
            return {"ok": True}

        ok = config_store.set(section, key, value)
        if not ok:
            raise IPCError(IPCError.INVALID_PARAMS, f"Invalid section/key: {section}.{key}")
        return {"ok": True}

    def config_reload(params: dict) -> dict:
        ok = config_store.reload()
        return {"reloaded": ok}

    def cameras_list(params: dict) -> dict:
        cfg = config_store.config
        cameras = [
            {"name": c.name, "stream_url": c.stream_url, "snap_url": c.snap_url, "enabled": c.enabled}
            for c in cfg.cameras
        ]
        return {"cameras": cameras}

    def faces_list(params: dict) -> dict:
        # Face DB is managed by MLManager, check if available
        if orchestrator.ml_manager and orchestrator.ml_manager.face_db:
            faces = orchestrator.ml_manager.face_db.get_all_faces()
            return {"faces": [{"name": f["name"], "samples": f.get("samples", 1)} for f in faces]}
        return {"faces": [], "error": "Face database not available"}

    def history(params: dict) -> dict:
        limit = params.get("limit", 50)
        if orchestrator.ml_manager and orchestrator.ml_manager.face_db:
            db = orchestrator.ml_manager.face_db
            rows = db._conn.execute(
                "SELECT person_name, camera, confidence, detected_at "
                "FROM detections ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return {"history": [
                {"person": r[0], "camera": r[1], "confidence": r[2], "when": r[3]}
                for r in rows
            ]}
        return {"history": [], "error": "History not available"}

    def snapshot(params: dict) -> dict:
        camera = params.get("camera")
        if not camera:
            raise IPCError(IPCError.INVALID_PARAMS, "camera required")
        frame = orchestrator.get_camera_snapshot(camera)
        if frame is None:
            return {"snapshot": None, "error": "No frame available"}
        import base64
        return {"snapshot": base64.b64encode(frame).decode()}

    def ping(params: dict) -> dict:
        return {"ok": True, "version": VERSION}

    def test_notify(params: dict) -> dict:
        """Send a test notification — reads configured sound from config."""
        title = params.get("title", "Test")
        subtitle = params.get("subtitle", "")
        message = params.get("message", "Test notification")
        # Read configured sound from current config
        cfg = config_store.config
        sound_key = params.get("sound_key", "sound_family")
        sound_name = "default"
        if cfg.notifications:
            sound_name = getattr(cfg.notifications, sound_key, "default") or "default"
        try:
            import subprocess
            script = f'display notification "{message}" with title "{title}" subtitle "{subtitle}" sound name "{sound_name}"'
            subprocess.run(
                ["osascript", "-e", script],
                timeout=3, check=False, capture_output=True,
            )
            logger.info(f"Test notification sent: {title} (sound={sound_name})")
            return {"ok": True, "message": f"Notification sent with sound '{sound_name}'"}
        except Exception as e:
            logger.warning(f"Test notification failed: {e}")
            return {"ok": False, "error": str(e)}

    def web_restart(params: dict) -> dict:
        _web_stop()
        return _web_start(config_store)

    return {
        "status": status,
        "start": start,
        "stop": stop,
        "config.get": config_get,
        "config.set": config_set,
        "config.reload": config_reload,
        "cameras.list": cameras_list,
        "faces.list": faces_list,
        "history": history,
        "snapshot": snapshot,
        "ping": ping,
        "test_notify": test_notify,
        "web_status": lambda params: {
            "result": {
                "running": _web_proc is not None and _web_proc.poll() is None,
                "pid": _web_proc.pid if _web_proc and _web_proc.poll() is None else None,
                "host": config_store.config.web.host,
                "port": config_store.config.web.port,
            }
        },
        "web_start": lambda params: _web_start(config_store),
        "web_stop": lambda params: _web_stop(),
        "web_restart": web_restart,
    }


if __name__ == "__main__":
    main()
