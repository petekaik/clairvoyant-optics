"""Web-hallintapaneeli FastAPI:lla.

Tarjoaa REST-API:n ja staattisen hallintakäyttöliittymän.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_HAS_WEB = False
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
    _HAS_WEB = True
except ImportError:
    pass


class WebServer:
    """Clairvoyant-Optics web-hallintapaneeli."""

    def __init__(
        self,
        pipeline=None,
        config=None,
        host: str = "127.0.0.1",
        port: int = 8765,
    ):
        self.pipeline = pipeline
        self.config = config
        self.host = host
        self.port = port
        self._server = None

    @property
    def available(self) -> bool:
        return _HAS_WEB

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def create_app(self) -> "FastAPI":
        """Luo FastAPI-sovellus reitityksineen."""
        if not _HAS_WEB:
            raise RuntimeError("FastAPI/uvicorn not installed")

        app = FastAPI(title="Clairvoyant-Optics", version="2.0.0")

        static_dir = Path(__file__).parent.parent / "web" / "static"
        if static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/")
        async def index():
            """Hallintapaneelin etusivu."""
            if (static_dir / "index.html").exists():
                return FileResponse(static_dir / "index.html")
            return self._html_dashboard()

        @app.get("/api/status")
        async def status():
            """Putken tila."""
            if self.pipeline is None:
                return {"state": "not_initialized"}

            all_faces = self.pipeline.face_db.get_all_faces() if self.pipeline.face_db else []

            return {
                "state": "running" if self.pipeline._running else "stopped",
                "cameras": [
                    {
                        "name": cam.name,
                        "stream": cam.stream_url,
                        "active": cam.name in self.pipeline.streams,
                    }
                    for cam in (self.config.cameras if self.config else [])
                ],
                "faces": [
                    {"name": f["name"], "samples": f.get("samples", 1)}
                    for f in all_faces
                ],
                "detections_today": self._get_detection_count(),
            }

        @app.get("/api/cameras")
        async def cameras():
            if self.config is None:
                return []
            return [
                {
                    "name": cam.name,
                    "stream_url": cam.stream_url,
                    "snap_url": cam.snap_url,
                }
                for cam in self.config.cameras
            ]

        @app.get("/api/faces")
        async def faces():
            if self.pipeline is None or self.pipeline.face_db is None:
                return []
            return [
                {"name": f["name"], "samples": f.get("samples", 1)}
                for f in self.pipeline.face_db.get_all_faces()
            ]

        @app.get("/api/history")
        async def history(limit: int = 50):
            """Viimeisimmät tunnistukset."""
            if self.pipeline is None or self.pipeline.face_db is None:
                return []

            db = self.pipeline.face_db
            rows = db._conn.execute(
                "SELECT person_name, camera, confidence, detected_at "
                "FROM detections ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

            return [
                {
                    "person": row[0],
                    "camera": row[1],
                    "confidence": row[2],
                    "when": row[3],
                }
                for row in rows
            ]

        @app.get("/api/snapshot/{camera_name}")
        async def snapshot(camera_name: str):
            """Viimeisin frame kameralta (base64 JPEG)."""
            import base64
            import cv2
            import numpy as np

            if self.pipeline is None:
                raise HTTPException(503, "Pipeline not running")

            stream = self.pipeline.streams.get(camera_name)
            if stream is None:
                raise HTTPException(404, f"Camera '{camera_name}' not found")

            result = stream.get_latest_frame()
            if result is None:
                raise HTTPException(404, "No frame available")

            frame, _ = result
            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            b64 = base64.b64encode(jpeg.tobytes()).decode()

            return JSONResponse({"camera": camera_name, "image": f"data:image/jpeg;base64,{b64}"})

        @app.post("/api/photos/import")
        async def import_from_photos(person_names: list[str] | None = None):
            """Tuo henkilöiden kasvogalleriat Photos.app:sta."""
            if self.pipeline is None:
                raise HTTPException(503, "Pipeline not initialized")

            try:
                from src.macos.photos_importer import PhotosImporter
            except ImportError:
                raise HTTPException(500, "osxphotos not installed")

            importer = PhotosImporter(face_recognizer=self.pipeline.face_recognizer)
            if not importer.available:
                raise HTTPException(500, "osxphotos not installed")

            results = importer.import_faces(person_names=person_names)
            return {"imported": results}

        return app

    def _get_detection_count(self) -> int:
        """Päivän tunnistusten määrä."""
        if self.pipeline is None or self.pipeline.face_db is None:
            return 0
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        row = self.pipeline.face_db._conn.execute(
            "SELECT COUNT(*) FROM detections WHERE detected_at >= ?",
            (today,),
        ).fetchone()
        return row[0] if row else 0

    def _html_dashboard(self) -> str:
        """Sisäänrakennettu HTML-dashboard (fallback)."""
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Clairvoyant-Optics</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, system-ui, sans-serif; background: #000; color: #fff; padding: 40px; }
        h1 { font-size: 28px; font-weight: 600; margin-bottom: 30px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .card { background: #1c1c1e; border-radius: 12px; padding: 24px; }
        .card h2 { font-size: 14px; font-weight: 500; color: #8e8e93; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 16px; }
        .stat { font-size: 36px; font-weight: 700; color: #fff; }
        .label { font-size: 13px; color: #8e8e93; margin-top: 4px; }
        .list { list-style: none; }
        .list li { padding: 8px 0; border-bottom: 1px solid #2c2c2e; display: flex; justify-content: space-between; font-size: 14px; }
        .list li:last-child { border-bottom: none; }
        .badge { padding: 2px 8px; border-radius: 10px; font-size: 12px; }
        .badge-green { background: #30d158; color: #000; }
        .badge-yellow { background: #ffd60a; color: #000; }
        .btn { background: #0071e3; color: #fff; border: none; padding: 8px 16px; border-radius: 8px; font-size: 14px; cursor: pointer; }
        .btn:hover { opacity: 0.9; }
    </style>
</head>
<body>
    <h1>👁 Clairvoyant-Optics</h1>
    <div class="grid" id="grid">
        <div class="card">
            <h2>Status</h2>
            <div class="stat" id="state">—</div>
            <div class="label" id="subtitle">Loading...</div>
        </div>
        <div class="card">
            <h2>Cameras</h2>
            <ul class="list" id="cameras"><li>Loading...</li></ul>
        </div>
        <div class="card">
            <h2>Faces Enrolled</h2>
            <ul class="list" id="faces"><li>Loading...</li></ul>
        </div>
        <div class="card">
            <h2>Actions</h2>
            <button class="btn" onclick="importPhotos()">Import from Photos.app</button>
        </div>
    </div>
    <script>
        async function load() {
            try {
                const r = await fetch('/api/status');
                const d = await r.json();
                document.getElementById('state').textContent = d.state;
                document.getElementById('subtitle').textContent = d.cameras.length + ' cameras · ' + d.faces.length + ' faces';
                
                document.getElementById('cameras').innerHTML = d.cameras.map(c =>
                    '<li><span>' + c.name + '</span><span class="badge ' + (c.active ? 'badge-green' : 'badge-yellow') + '">' + (c.active ? 'active' : 'inactive') + '</span></li>'
                ).join('') || '<li>No cameras</li>';
                
                document.getElementById('faces').innerHTML = d.faces.map(f =>
                    '<li><span>' + f.name + '</span><span>' + f.samples + ' samples</span></li>'
                ).join('') || '<li>No faces enrolled</li>';
            } catch(e) {
                document.getElementById('state').textContent = 'Error';
                document.getElementById('subtitle').textContent = e.message;
            }
        }
        
        async function importPhotos() {
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = 'Importing...';
            try {
                const r = await fetch('/api/photos/import', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}' });
                const d = await r.json();
                btn.textContent = 'Done! ' + Object.values(d.imported).reduce((a,b)=>a+b,0) + ' faces';
                load();
            } catch(e) {
                btn.textContent = 'Error: ' + e.message;
                btn.disabled = false;
            }
        }
        
        load();
    </script>
</body>
</html>"""
