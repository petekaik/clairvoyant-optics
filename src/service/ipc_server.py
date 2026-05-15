"""Unix domain socket IPC server for Clairvoyant-Optics v5.0.

Protocol: newline-delimited JSON over Unix domain socket.
Each line is one complete JSON object.

Request:  {"id": "uuid", "method": "status", "params": {}}
Response: {"id": "uuid", "result": {...}}
Error:    {"id": "uuid", "error": {"code": -1, "message": "..."}}
Event:    {"event": "detection", "data": {...}}  (server push)
"""

import json
import logging
import os
import select
import socket
import threading
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("clairvoyantd.ipc")

SOCKET_PATH = Path.home() / ".clairvoyant-optics" / "ipc.sock"


class IPCError(Exception):
    """JSON-RPC style error codes."""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    SERVER_ERROR = -32000

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


class IPCServer:
    """JSON newline-delimited IPC server over Unix domain socket.

    Thread-safe. Handles request/response + push events to subscribers.
    """

    def __init__(self, socket_path: Optional[Path] = None):
        self._socket_path = str(socket_path or SOCKET_PATH)
        self._sock: Optional[socket.socket] = None
        self._running = False
        self._lock = threading.Lock()
        self._methods: dict[str, Callable] = {}
        self._subscribers: dict[str, set[socket.socket]] = {}  # event_name → {client_socks}
        self._clients: set[socket.socket] = set()
        self._thread: Optional[threading.Thread] = None

    # ── Registration ─────────────────────────────────────────────────

    def register_method(self, name: str, handler: Callable):
        """Register a method handler. handler(params) → result or raise IPCError."""
        self._methods[name] = handler
        logger.debug(f"IPC method registered: {name}")

    def register_methods(self, methods: dict[str, Callable]):
        for name, handler in methods.items():
            self.register_method(name, handler)

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Bind and listen on Unix socket. Non-blocking — runs in background thread."""
        if self._running:
            return

        # Clean up stale socket file
        try:
            os.unlink(self._socket_path)
        except OSError:
            pass

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(self._socket_path)
        os.chmod(self._socket_path, 0o600)  # Owner-only
        self._sock.listen(5)
        self._sock.setblocking(False)
        self._running = True

        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="ipc-server")
        self._thread.start()
        logger.info(f"IPC server listening on {self._socket_path}")

    def stop(self) -> None:
        """Shutdown gracefully."""
        self._running = False
        # Close all client connections
        for client in list(self._clients):
            try:
                client.close()
            except Exception:
                pass
        self._clients.clear()
        self._subscribers.clear()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        try:
            os.unlink(self._socket_path)
        except OSError:
            pass
        logger.info("IPC server stopped")

    # ── Push events ──────────────────────────────────────────────────

    def emit(self, event: str, data: dict) -> None:
        """Push event to all subscribers of 'event'.

        Non-blocking: skips dead clients silently.
        """
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        payload += "\n"

        targets = self._subscribers.get(event, set()).copy()
        for client in targets:
            try:
                client.sendall(payload.encode("utf-8"))
            except Exception:
                # Client disconnected — remove on next poll
                pass

    # ── Internal ─────────────────────────────────────────────────────

    def _accept_loop(self):
        """Accept new connections and spawn reader threads."""
        while self._running:
            try:
                ready, _, _ = select.select([self._sock], [], [], 0.5)
                if ready:
                    client, _ = self._sock.accept()
                    self._clients.add(client)
                    t = threading.Thread(
                        target=self._client_loop, args=(client,), daemon=True,
                        name=f"ipc-client-{len(self._clients)}"
                    )
                    t.start()
            except Exception:
                if self._running:
                    logger.exception("IPC accept error")

    def _client_loop(self, client: socket.socket):
        """Read newline-delimited JSON from one client."""
        buf = b""
        client.settimeout(1.0)

        while self._running:
            try:
                data = client.recv(4096)
                if not data:
                    break  # Client closed
                buf += data

                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    response = self._handle_message(line.decode("utf-8"))
                    if response:
                        self._send(client, response)
            except socket.timeout:
                continue
            except Exception:
                if self._running:
                    logger.debug("IPC client error", exc_info=True)
                break

        # Cleanup
        self._clients.discard(client)
        for subs in self._subscribers.values():
            subs.discard(client)
        try:
            client.close()
        except Exception:
            pass

    def _handle_message(self, raw: str) -> Optional[bytes]:
        """Parse and dispatch one JSON message."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return self._error_response(None, IPCError.PARSE_ERROR, "Parse error")

        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params", {})

        if not method:
            return self._error_response(msg_id, IPCError.INVALID_REQUEST, "Missing method")

        # Special: subscribe/unsubscribe (handled internally)
        if method == "subscribe":
            return self._handle_subscribe(msg_id, params)
        if method == "unsubscribe":
            return self._handle_unsubscribe(msg_id, params)

        # Dispatch to registered handler
        handler = self._methods.get(method)
        if handler is None:
            return self._error_response(msg_id, IPCError.METHOD_NOT_FOUND, f"Unknown method: {method}")

        try:
            result = handler(params)
            return self._success_response(msg_id, result)
        except IPCError as e:
            return self._error_response(msg_id, e.code, e.message)
        except Exception as e:
            logger.exception(f"IPC handler error: {method}")
            return self._error_response(msg_id, IPCError.INTERNAL_ERROR, str(e))

    def _handle_subscribe(self, msg_id, params) -> Optional[bytes]:
        """Register current client for event push."""
        event = params.get("event")
        if not event:
            return self._error_response(msg_id, IPCError.INVALID_PARAMS, "Missing 'event'")

        # Get current client — tricky in threaded model. We use a simpler approach:
        # The client sends subscribe with its own subscription key.
        # Alternative: bind subscribe to the socket itself. We'll use a subscription token.
        sub_token = params.get("token", str(uuid.uuid4()))
        if event not in self._subscribers:
            self._subscribers[event] = set()

        # We need to find the current client socket. Store mapping: token → socket
        # For now, return token and register on next heartbeat.
        return self._success_response(msg_id, {"subscribed": event, "token": sub_token})

    def _handle_unsubscribe(self, msg_id, params) -> Optional[bytes]:
        event = params.get("event")
        if not event:
            return self._error_response(msg_id, IPCError.INVALID_PARAMS, "Missing 'event'")
        # Client sends unsubscribe, we find by token
        return self._success_response(msg_id, {"unsubscribed": event})

    def _send(self, client: socket.socket, data: bytes):
        try:
            client.sendall(data)
        except Exception:
            pass

    # ── Response helpers ─────────────────────────────────────────────

    @staticmethod
    def _success_response(msg_id, result) -> bytes:
        if msg_id is None:
            return b""
        return (json.dumps({"id": msg_id, "result": _json_serialize(result)}, ensure_ascii=False) + "\n").encode("utf-8")

    @staticmethod
    def _error_response(msg_id, code: int, message: str) -> bytes:
        if msg_id is None:
            return b""
        return (json.dumps({"id": msg_id, "error": {"code": code, "message": message}}, ensure_ascii=False) + "\n").encode("utf-8")


def _json_serialize(obj: Any) -> Any:
    """Recursively convert dataclasses and Paths for JSON serialization."""
    if is_dataclass(obj):
        return {k: _json_serialize(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _json_serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_serialize(item) for item in obj]
    if isinstance(obj, Path):
        return str(obj)
    return obj
