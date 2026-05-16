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
from pathlib import Path

# Ensure project root is on path (for src.* imports when running standalone)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.service.config_store import ConfigStore, CONFIG_DIR
from src.service.ipc_server import IPCServer
from src.service.orchestrator import Orchestrator

logger = logging.getLogger("clairvoyantd")

VERSION = "5.1.0"


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
    }


if __name__ == "__main__":
    main()
