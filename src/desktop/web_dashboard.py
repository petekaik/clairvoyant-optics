#!/usr/bin/env python3
"""Clairvoyant-Optics v5.0.1 — Web Dashboard (stdlib http.server).

Lightweight HTTP server for the web dashboard. No external dependencies
(no FastAPI/uviicorn). Communicates with clairvoyantd via IPC.

Serves:
  GET /           — Dashboard HTML page
  GET /api/status — Pipeline status from daemon (IPC)
  GET /api/cameras — Camera list from daemon (IPC)

Binds to 127.0.0.1:8765. Runs as standalone process spawned by menu_bar.py.
"""

import json
import os
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

VERSION = "5.4.0"
CONFIG_DIR = Path.home() / ".clairvoyant-optics"

# ── IPC client (minimal, avoids src.* imports for standalone bundle compat) ─

def _ipc_call(method: str, params: dict | None = None, timeout: float = 5.0) -> dict | None:
    """Direct IPC call to daemon. Returns None if daemon unreachable."""
    import socket
    try:
        sock_path = str(CONFIG_DIR / "ipc.sock")
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(sock_path)
        msg = json.dumps({"id": "web", "method": method, "params": params or {}})
        s.sendall(msg.encode() + b"\n")
        import select
        ready, _, _ = select.select([s], [], [], timeout)
        if ready:
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
            s.close()
            if data:
                return json.loads(data.decode())
        s.close()
    except Exception:
        pass
    return None


# ── Dashboard HTML ────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Clairvoyant-Optics Dashboard</title>
    <style>
        :root {
            --bg: #1e1e20;
            --card-bg: #2c2c2e;
            --text: #f5f5f7;
            --text-secondary: #98989d;
            --accent: #0a84ff;
            --green: #30d158;
            --red: #ff453a;
            --yellow: #ffd60a;
            --border: #48484a;
        }
        @media (prefers-color-scheme: light) {
            :root {
                --bg: #f5f5f7;
                --card-bg: #ffffff;
                --text: #1d1d1f;
                --text-secondary: #6e6e73;
                --accent: #007aff;
                --green: #34c759;
                --red: #ff3b30;
                --yellow: #ffcc00;
                --border: #c6c6c8;
            }
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
        }
        header {
            padding: 24px 32px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        header h1 { font-size: 22px; font-weight: 700; }
        header .version { font-size: 12px; color: var(--text-secondary); }
        .status-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }
        .status-running { background: var(--green); color: #000; }
        .status-idle { background: var(--text-secondary); color: #fff; }
        .status-error { background: var(--red); color: #fff; }
        .status-disconnected { background: var(--red); color: #fff; }
        main {
            max-width: 800px;
            margin: 0 auto;
            padding: 32px;
        }
        .card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            border: 1px solid var(--border);
        }
        .card h2 {
            font-size: 14px;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 12px;
        }
        .stat-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid var(--border);
        }
        .stat-row:last-child { border-bottom: none; }
        .stat-label { color: var(--text-secondary); font-size: 14px; }
        .stat-value { font-size: 14px; font-weight: 500; }
        .camera-item {
            display: flex;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid var(--border);
            gap: 12px;
        }
        .camera-item:last-child { border-bottom: none; }
        .camera-status {
            width: 10px; height: 10px;
            border-radius: 50%;
            flex-shrink: 0;
        }
        .camera-active { background: var(--green); }
        .camera-inactive { background: var(--text-secondary); }
        .camera-name { font-weight: 600; flex: 1; }
        .camera-url { font-size: 12px; color: var(--text-secondary); word-break: break-all; }
        .empty-state {
            text-align: center;
            padding: 32px;
            color: var(--text-secondary);
        }
        .loading { text-align: center; padding: 32px; color: var(--text-secondary); }
        footer {
            text-align: center;
            padding: 24px;
            font-size: 11px;
            color: var(--text-secondary);
        }
    </style>
</head>
<body>
    <header>
        <div>
            <h1>Clairvoyant-Optics</h1>
            <span class="version">v""" + VERSION + """</span>
        </div>
        <div id="status-badge"></div>
    </header>
    <main>
        <div class="card">
            <h2>System Status</h2>
            <div id="system-stats"></div>
        </div>
        <div class="card">
            <h2>Cameras</h2>
            <div id="cameras-list"></div>
        </div>
    </main>
    <footer>Clairvoyant-Optics Dashboard &middot; Local only (127.0.0.1:8765)</footer>
    <script>
        function statusBadge(state) {
            const cls = {
                running: 'status-running', idle: 'status-idle',
                starting: 'status-idle', stopping: 'status-idle',
                error: 'status-error'
            };
            let s = state || 'disconnected';
            return '<span class="status-badge ' + (cls[s] || 'status-disconnected') + '">' + s.toUpperCase() + '</span>';
        }

        async function loadStatus() {
            try {
                const r = await fetch('/api/status');
                const d = await r.json();
                document.getElementById('status-badge').innerHTML = statusBadge(d.state);

                let html = '';
                const stats = [
                    ['State', d.state],
                    ['Active Detections', d.active_detections || '0'],
                    ['On Power', d.is_on_power ? 'Yes' : 'No'],
                    ['Battery', d.battery_pct ? d.battery_pct + '%' : '—'],
                    ['Home WiFi', d.is_home_wifi ? 'Yes' : 'No'],
                    ['Suspended', d.suspended_reason || 'None'],
                    ['Uptime', d.uptime_seconds ? Math.round(d.uptime_seconds) + 's' : '—'],
                    ['Last Detection', d.last_detection || 'None'],
                ];
                for (const [label, value] of stats) {
                    html += '<div class="stat-row"><span class="stat-label">' + label + '</span><span class="stat-value">' + value + '</span></div>';
                }
                document.getElementById('system-stats').innerHTML = html || '<div class="empty-state">No data</div>';
            } catch(e) {
                document.getElementById('status-badge').innerHTML = statusBadge('disconnected');
                document.getElementById('system-stats').innerHTML = '<div class="empty-state">Daemon unreachable — start clairvoyantd first</div>';
            }
        }

        async function loadCameras() {
            try {
                const r = await fetch('/api/cameras');
                const d = await r.json();
                const cameras = d.cameras || [];
                if (cameras.length === 0) {
                    document.getElementById('cameras-list').innerHTML = '<div class="empty-state">No cameras configured</div>';
                    return;
                }
                let html = '';
                for (const cam of cameras) {
                    const activeCls = cam.connected ? 'camera-active' : 'camera-inactive';
                    html += '<div class="camera-item">' +
                        '<div class="camera-status ' + activeCls + '"></div>' +
                        '<div><div class="camera-name">' + (cam.name || 'Unnamed') + '</div>' +
                        '<div class="camera-url">' + (cam.stream_url || '—') + '</div></div></div>';
                }
                document.getElementById('cameras-list').innerHTML = html;
            } catch(e) {
                document.getElementById('cameras-list').innerHTML = '<div class="empty-state">Failed to load cameras</div>';
            }
        }

        loadStatus();
        loadCameras();
        setInterval(loadStatus, 5000);
        setInterval(loadCameras, 30000);
    </script>
</body>
</html>"""


# ── HTTP handler ─────────────────────────────────────────────────────────

class DashboardHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # Suppress access logs

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._send_html(DASHBOARD_HTML)
        elif self.path == "/api/status":
            resp = _ipc_call("status")
            if resp and "result" in resp:
                self._send_json(resp["result"])
            else:
                self._send_json({"state": "disconnected", "error": "Daemon unreachable"})
        elif self.path == "/api/cameras":
            resp = _ipc_call("cameras.list")
            if resp and "result" in resp:
                self._send_json(resp["result"])
                return
            # Fallback: try config.get
            resp = _ipc_call("config.get", {"section": "streams"})
            if resp and "result" in resp:
                cameras = resp["result"].get("cameras", [])
                self._send_json({"cameras": [{"name": c.get("name", ""), "stream_url": c.get("stream_url", ""),
                                              "connected": False} for c in cameras]})
            else:
                self._send_json({"cameras": []})
        elif self.path == "/health":
            self._send_json({"ok": True, "version": VERSION})
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    host = "127.0.0.1"
    port = 8765
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Read config.yaml for web host/port/enabled
    config_file = CONFIG_DIR / "config.yaml"
    if config_file.exists():
        try:
            import yaml
            with open(config_file) as f:
                cfg = yaml.safe_load(f) or {}
            web_cfg = cfg.get("web", {})
            host = web_cfg.get("host", host)
            port = web_cfg.get("port", port)
            enabled = web_cfg.get("enabled", True)
            if not enabled:
                print("Web dashboard disabled in config — exiting", file=sys.stderr)
                sys.exit(0)
        except Exception:
            pass

    print(f"Web dashboard starting: http://{host}:{port}", file=sys.stderr)
    server = HTTPServer((host, port), DashboardHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
