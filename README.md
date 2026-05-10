# Clairvoyant-Optics v2

**Your digital eye for macOS.** Monitors surveillance cameras in the background, recognizes family members from Photos.app face galleries, and sends native notifications — all running 100% locally on Apple Silicon.

```
Surveillance Cameras ──→ YOLOv8n + InsightFace ──→ macOS Notifications
      HLS/RTSP              M1 Neural Engine        Family = info
                                                     Stranger = alert
```

## What's New in v2

- **🖥 macOS native** — No longer requires Home Assistant. Runs as a menubar app with native notifications.
- **📸 Photos.app integration** — Imports face galleries directly from your macOS Photos library. Zero manual photo copying.
- **🔔 Smart notifications** — Family members get a subtle notification. Strangers trigger an alert sound.
- **🌐 Web dashboard** — Manage cameras, enrolled faces, and alerts at `http://localhost:8765`.
- **🔌 Home Assistant optional** — MQTT support remains if you want HA integration.

## How It Works

1. **Continuous monitoring** — Reads HLS streams from your cameras (via MediaMTX or direct RTSP)
2. **Person detection** — YOLOv8n on low-res frames (640×360), 5-10ms on M1 Neural Engine
3. **Face recognition** — When a person is detected, fetches a 1080p snap JPEG and runs InsightFace/ArcFace
4. **Match & notify** — Compares against enrolled family members. Known = gentle notification. Unknown = alert.
5. **Photos.app sync** — Face galleries can be imported from Photos.app with one command

## Requirements

| Component | Details |
|---|---|
| **Hardware** | Mac with Apple Silicon (M1+) and 8+ GB RAM |
| **OS** | macOS 14+ (Sonoma or newer) |
| **Python** | 3.10+ |
| **Cameras** | Any RTSP/HLS-capable camera. Tested with UniFi G3 + MediaMTX |

## Quick Start

### Option A: DMG Installer (recommended — no Python needed)

1. Download `Clairvoyant-Optics-X.Y.Z.dmg` from [Releases](https://github.com/petekaik/clairvoyant-optics/releases)
2. Open the DMG and drag `Clairvoyant-Optics.app` to `/Applications`
3. **Right-click the app** → **Open** (macOS Gatekeeper requires this once for ad-hoc signed apps)
4. Configure cameras in `~/.clairvoyant/.env` (see `CAM1_STREAM` example below)

### Option B: From Source (developers)

```bash
git clone git@github.com:petekaik/clairvoyant-optics.git
cd clairvoyant-optics
pip install -e .
```

### Configure

```bash
cp .env.example .env
# Edit .env with your camera stream URLs
```

### 3. Download ML models

```bash
python download_models.py
```

### 4. Import faces from Photos.app

```bash
clairvoyant import-from-photos
```

This reads your Photos.app person galleries and generates face embeddings. No images are copied — only the mathematical face vectors are stored locally.

If Photos.app images are iCloud-only, use manual enrollment instead:

```bash
mkdir -p photos/alice
# Copy 5-10 photos of Alice to photos/alice/
clairvoyant enroll "Alice" photos/alice/
```

### 5. Start

```bash
clairvoyant start
```

This launches the detection pipeline, menubar app, and web dashboard.

## Commands

| Command | Description |
|---|---|
| `clairvoyant start` | Start pipeline + menubar + web dashboard |
| `clairvoyant serve` | Web dashboard only |
| `clairvoyant enroll <name> <dir>` | Enroll a person from photos |
| `clairvoyant import-from-photos` | Import all faces from Photos.app |
| `clairvoyant import-from-photos --person "Alice" "Bob"` | Import specific persons |
| `clairvoyant list-faces` | List enrolled faces |

## Architecture

```
src/
├── cli.py              # CLI entry point (clairvoyant <command>)
├── main.py             # Detection pipeline orchestrator
├── config.py           # .env configuration loader
├── streams/            # HLS/RTSP stream readers
├── detection/          # YOLOv8n person detection
├── recognition/        # InsightFace/ArcFace face recognition + SQLite DB
├── integration/        # MQTT (optional, for Home Assistant)
├── macos/              # macOS-specific components
│   ├── photos_importer.py   # Photos.app face gallery import
│   ├── notifier.py          # Native macOS notifications
│   ├── menubar_app.py       # Menubar status + controls
│   └── web_server.py        # FastAPI dashboard
├── web/                # Web dashboard static files
└── utils/              # Logging, helpers
```

## Performance (MacBook Air M1, 8 GB)

| Component | Resolution | Inference | Load |
|---|---|---|---|
| YOLOv8n person detect | 640×360 | 5-10 ms | ~5% Neural Engine |
| InsightFace face detect | 1920×1080 | 20-40 ms | ~15% Neural Engine |
| ArcFace embedding | 224×224 | 10-20 ms | Rare |
| **Total RAM** | | | **~500-800 MB** |

With 2 cameras active, CPU load stays around 15-25%.

## Configuration Reference

```ini
# Cameras (CAM1, CAM2, ..., CAM9)
CAM1_STREAM=http://192.168.1.100:8888/front-yard/index.m3u8
CAM1_SNAP=https://192.168.1.101/snap.jpeg
CAM1_NAME=front_yard

# MQTT (optional — Home Assistant)
# Leave MQTT_BROKER empty to run without HA
MQTT_BROKER=
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=

# Detection thresholds
PERSON_DETECT_CONFIDENCE=0.5
FACE_DETECT_CONFIDENCE=0.7
FACE_RECOGNITION_THRESHOLD=0.6
FRAME_INTERVAL=5

# Notifications
NOTIFICATION_SOUND_FAMILY=default   # macOS sound for family
NOTIFICATION_SOUND_ALERT=alarm      # macOS sound for strangers
# NOTIFICATION_DND_START=22:00      # Do Not Disturb start (optional)
# NOTIFICATION_DND_END=07:00        # Do Not Disturb end (optional)

# Web dashboard
WEB_UI_PORT=8765
WEB_UI_HOST=127.0.0.1
```

## Known Limitations

- **Photos.app iCloud** — If "Optimize Mac Storage" is enabled, most photos are iCloud-only and cannot be used for face import. Use manual enrollment or download originals to your Mac.
- **Self-signed camera certs** — Snap JPEG endpoints with self-signed certificates work but require `verify=False`.
- **Menubar app** requires `rumps` (macOS-only, included in requirements).

## Privacy & Security

- **100% local inference** — All ML runs on the M1 Neural Engine. No cloud APIs, no images uploaded anywhere.
- **Encrypted camera links** — Use RTSPS between cameras and MediaMTX for encrypted transport.
- **Face embeddings stored locally** — SQLite database in `data/faces.db`, never transmitted.
- **No secrets in the repo** — `.env`, `models/*.onnx`, and `photos/` are all gitignored.
- **Suitable for households with children** — Designed from the ground up with privacy as a hard requirement.

## License

This project is for personal, non-commercial use. ML models from InsightFace are available for non-commercial research purposes only per their [model zoo terms](https://github.com/deepinsight/insightface/blob/master/model_zoo/README.md).
