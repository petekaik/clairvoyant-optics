"""Shared IPC client library for Clairvoyant-Optics v5.0 desktop apps.

Used by menu bar, settings GUI, and web dashboard to communicate
with the clairvoyantd service daemon via Unix domain socket.

Protocol: newline-delimited JSON over Unix domain socket.
"""

import json
import logging
import os
import socket
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

SOCKET_PATH = Path.home() / ".clairvoyant-optics" / "ipc.sock"


class IPCClient:
    """Synchronous IPC client with auto-reconnect and event subscription.

    Usage:
        client = IPCClient()
        client.connect()
        status = client.call("status")  # blocks until response
        client.subscribe("detection", my_callback)
        client.close()
    """

    def __init__(self, socket_path: Optional[Path] = None, timeout: float = 5.0):
        self._socket_path = str(socket_path or SOCKET_PATH)
        self._timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._running = False
        self._reader_thread: Optional[threading.Thread] = None
        self._pending: dict[str, threading.Event] = {}  # msg_id → event
        self._results: dict[str, dict] = {}              # msg_id → result/error dict
        self._event_callbacks: dict[str, list[Callable]] = {}  # event → [callback, ...]
        self._reconnect_delay: float = 1.0
        self._on_disconnect: Optional[Callable] = None

    # ── Connection ───────────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to the daemon. Returns True on success."""
        with self._lock:
            if self._sock and self._running:
                return True

            try:
                self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self._sock.settimeout(self._timeout)
                self._sock.connect(self._socket_path)
                self._sock.setblocking(False)
                self._running = True

                # Start reader thread
                self._reader_thread = threading.Thread(
                    target=self._reader_loop, daemon=True, name="ipc-reader"
                )
                self._reader_thread.start()

                logger.info(f"IPC connected: {self._socket_path}")
                return True

            except Exception as e:
                logger.warning(f"IPC connect failed: {e}")
                if self._sock:
                    try:
                        self._sock.close()
                    except Exception:
                        pass
                    self._sock = None
                return False

    def close(self) -> None:
        """Disconnect from the daemon."""
        with self._lock:
            self._running = False
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
            # Wake up all pending requests
            for evt in self._pending.values():
                evt.set()
            self._pending.clear()

    @property
    def connected(self) -> bool:
        return self._sock is not None and self._running

    def wait_until_ready(self, max_wait: float = 30.0) -> bool:
        """Block until daemon is available. Returns True when connected."""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            if self.connect():
                return True
            time.sleep(1.0)
        return False

    # ── Request/Response ─────────────────────────────────────────────

    def call(self, method: str, params: Optional[dict] = None, timeout: float = 10.0) -> dict:
        """Synchronous RPC call. Returns {'result': ...} or {'error': ...}."""
        if not self.connected:
            return {"error": {"code": -1, "message": "Not connected to daemon"}}

        msg_id = str(uuid.uuid4())
        request = {"id": msg_id, "method": method, "params": params or {}}
        evt = threading.Event()

        with self._lock:
            self._pending[msg_id] = evt

        try:
            self._send(request)
        except Exception as e:
            with self._lock:
                self._pending.pop(msg_id, None)
            return {"error": {"code": -1, "message": f"Send failed: {e}"}}

        # Wait for response
        if evt.wait(timeout=timeout):
            with self._lock:
                result = self._results.pop(msg_id, None)
                self._pending.pop(msg_id, None)
            if result:
                return result
            return {"error": {"code": -1, "message": "No response"}}

        # Timeout
        with self._lock:
            self._pending.pop(msg_id, None)
        return {"error": {"code": -1, "message": f"Request timed out ({timeout}s)"}}

    # ── Event subscription ───────────────────────────────────────────

    def subscribe(self, event: str, callback: Callable[[dict], None]) -> None:
        """Register callback for server-pushed events.

        callback(data_dict) called on each event from the daemon.
        Subscription is client-side only (no IPC subscribe needed yet).
        """
        if event not in self._event_callbacks:
            self._event_callbacks[event] = []
        self._event_callbacks[event].append(callback)
        logger.debug(f"Subscribed to event: {event}")

    def unsubscribe(self, event: str, callback: Optional[Callable] = None) -> None:
        """Remove event subscription."""
        if callback is None:
            self._event_callbacks.pop(event, None)
        elif event in self._event_callbacks:
            self._event_callbacks[event] = [
                cb for cb in self._event_callbacks[event] if cb is not callback
            ]

    def on_disconnect(self, callback: Callable[[], None]) -> None:
        """Register callback for disconnect events."""
        self._on_disconnect = callback

    # ── Internal ─────────────────────────────────────────────────────

    def _send(self, msg: dict) -> None:
        """Send a JSON message to the daemon."""
        data = json.dumps(msg, ensure_ascii=False) + "\n"
        self._sock.sendall(data.encode("utf-8"))

    def _reader_loop(self) -> None:
        """Background thread: read responses from daemon."""
        buf = b""
        import select

        while self._running:
            try:
                if self._sock is None:
                    break
                ready, _, _ = select.select([self._sock], [], [], 1.0)
                if not ready:
                    continue

                data = self._sock.recv(4096)
                if not data:
                    # Server closed connection
                    logger.warning("IPC server disconnected")
                    self._handle_disconnect()
                    break

                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    self._handle_message(line.decode("utf-8"))

            except (socket.timeout, BlockingIOError):
                continue
            except Exception:
                if self._running:
                    logger.debug("IPC read error", exc_info=True)
                    self._handle_disconnect()
                break

    def _handle_message(self, raw: str) -> None:
        """Process one JSON response from daemon."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"IPC parse error: {raw[:100]}")
            return

        msg_id = msg.get("id")

        # Server push event
        if "event" in msg and msg_id is None:
            event_name = msg["event"]
            data = msg.get("data", {})
            callbacks = self._event_callbacks.get(event_name, [])
            for cb in callbacks:
                try:
                    cb(data)
                except Exception:
                    logger.exception(f"Event callback error: {event_name}")
            return

        # RPC response
        if msg_id and msg_id in self._pending:
            with self._lock:
                self._results[msg_id] = msg
            self._pending[msg_id].set()

    def _handle_disconnect(self) -> None:
        """Clean up after daemon disconnect."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

        if self._on_disconnect:
            try:
                self._on_disconnect()
            except Exception:
                pass

        # Auto-reconnect in background
        if self._reconnect_delay > 0:
            t = threading.Thread(target=self._auto_reconnect, daemon=True)
            t.start()

    def _auto_reconnect(self) -> None:
        """Attempt reconnection with backoff."""
        delay = 1.0
        max_delay = 30.0
        while not self._running:
            logger.info(f"IPC reconnect in {delay:.1f}s...")
            time.sleep(delay)
            if self.connect():
                logger.info("IPC reconnected")
                return
            delay = min(delay * 2, max_delay)
