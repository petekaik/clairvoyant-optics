# Clairvoyant-Optics v5.1

**Your digital eye for macOS.** Menu bar app that monitors surveillance cameras, recognizes family members, and sends native notifications — all running 100% locally on Apple Silicon.

```
Cameras ──→ clairvoyantd (daemon) ──→ macOS Notifications
                 │    IPC socket
                 ├── menu_bar.py (rumps, menu bar icon)
                 ├── settings.py (Apple HIG toolbar window)
                 └── web_dashboard.py (http://127.0.0.1:8765)
```

## Architecture (v5 — service-oriented)

v5 splits the monolith into a three-layer IPC architecture:

| Layer | Process | Role |
|---|---|---|
| **Service** | `clairvoyantd` (daemon) | ML pipeline, camera I/O, config store, IPC server |
| **Desktop** | `menu_bar.py` (rumps) | Menu bar icon, quick start/stop, IPC client |
| **Desktop** | `settings.py` (tkinter) | Apple HIG settings window, launched via `Settings.app` wrapper |
| **Desktop** | `web_dashboard.py` (stdlib) | HTTP dashboard at `http://127.0.0.1:8765`, IPC client |

Communication: Unix domain socket at `~/.clairvoyant-optics/ipc.sock`, newline-delimited JSON.

The daemon auto-starts when the menu bar app launches. A LaunchAgent plist is provided for boot-time daemon startup.

## Quick Start

### DMG Installer (recommended — no Python needed)

1. Download `Clairvoyant-Optics-5.1.0.dmg` from [Releases](https://github.com/petekaik/clairvoyant-optics/releases)
2. Open the DMG and drag `Clairvoyant-Optics.app` to `/Applications`
3. **First launch** — macOS Gatekeeper blocks unsigned apps. Bypass it once:
   - **Right-click** the app in `/Applications` → **Open** → confirm the dialog
   - Or: **System Settings → Privacy & Security** → click **"Open Anyway"**
4. Click the eye icon in the menu bar → **Settings…** to configure cameras

### Why does macOS block it?

Clairvoyant-Optics is an open-source project. It is **ad-hoc signed** (not notarized by Apple). The app runs 100% locally — no data leaves your machine. Right-click → Open adds a permanent exception.

### From Source (developers)

```bash
git clone git@github.com:petekaik/clairvoyant-optics.git
cd clairvoyant-optics
python3 -m venv venv && source venv/bin/activate
pip install -e .
```

## Configuration

All settings live in `~/.clairvoyant-optics/config.yaml`. Use the **Settings…** window (⌘S from menu bar) for GUI configuration, or edit the YAML file directly.

### Settings tabs

| Tab | Content |
|---|---|
| **General** (⚙) | Log Level, Launch at Login, API Server (Host + Port + Apply & Test) |
| **Streams** (▶) | Camera management — add/remove cameras, stream URLs, snap URLs |
| **Notifications** (⚝) | Notification toggles, alert sounds, Do Not Disturb schedule |
| **Advanced** (⌅) | Auto-Update, Error Reporting, Battery/power settings, Home WiFi SSIDs |

The settings window follows [macOS HIG toolbar design](https://developer.apple.com/design/human-interface-guidelines/toolbars) with a left-side tab bar, SF fonts, and full dark mode support.

```yaml
cameras:
  - name: front_yard
    stream_url: http://192.168.1.100:8888/front-yard/index.m3u8
    snap_url: https://192.168.1.101/snap.jpeg

web:
  host: 127.0.0.1
  port: 8765

notifications:
  enabled: true
  notify_on_family: true
  notify_on_unknown: true
  notification_sound_family: default
  notification_sound_alert: alarm
  notification_dnd_start: "22:00"
  notification_dnd_end: "07:00"

advanced:
  auto_update: false
  error_reporting: false
  pause_on_battery: false
  pause_when_away: false
  home_ssids: ""
```

Settings changes are applied instantly via IPC — no restart needed.

## Running

Double-click `Clairvoyant-Optics.app` in `/Applications`. The eye icon appears in the menu bar.

**Menu bar controls:**
- Status indicator (● Running / ○ Idle / ✕ Disconnected)
- ▶ Start / ⏸ Stop pipeline
- **Settings…** (⌘S) — Apple HIG settings window
- **Web Dashboard** — opens `http://127.0.0.1:8765` in browser
- **Quit** (⌘Q) — clean shutdown

### LaunchAgent (daemon at login)

```bash
cp assets/fi.kaikkonen.clairvoyantd.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/fi.kaikkonen.clairvoyantd.plist
```

The daemon starts when you log in. The menu bar app connects to it automatically.

## Web Dashboard

Available at `http://127.0.0.1:8765`:

| Endpoint | Description |
|---|---|
| `GET /` | Dark-mode HTML dashboard with live status |
| `GET /api/status` | JSON: pipeline state, camera health, battery |
| `GET /api/cameras` | JSON: camera list with connection status |

The dashboard is a self-contained stdlib `http.server` — no FastAPI or external dependencies. API host/port configurable in Settings → General → API Server.

## Project Structure

```
src/
├── version.py              # Single source of truth: VERSION
├── desktop/                # GUI layer (bundled into .app Resources)
│   ├── menu_bar.py         # rumps menu bar app, IPC client
│   ├── settings.py         # Apple HIG settings window (tkinter)
│   ├── web_dashboard.py    # stdlib HTTP dashboard, IPC client
│   └── ipc_client.py       # Shared Unix socket IPC client
├── service/                # Daemon layer (clairvoyantd)
│   ├── daemon.py           # Entry point, signal handlers
│   ├── ipc_server.py       # Unix socket IPC server
│   ├── orchestrator.py     # State machine (idle → starting → running → stopping)
│   ├── config_store.py     # YAML config I/O + SIGHUP reload
│   ├── camera_manager.py   # Camera stream management (stub)
│   ├── ml_manager.py       # ONNX/CoreML inference (stub)
│   ├── battery_manager.py  # Power state monitoring
│   └── notification_bus.py # macOS notification dispatch (stub)
├── detection/              # YOLOv8n person detection
├── recognition/            # InsightFace face recognition
├── streams/                # HLS/RTSP stream readers
├── integration/            # MQTT (optional, Home Assistant)
├── macos/                  # Legacy v4.2 components (archived)
│   ├── app.py              # v4 monolith (not used in v5)
│   ├── settings.py         # v4 HIG reference implementation
│   └── web_server.py       # v4 FastAPI server (replaced)
└── utils/                  # Logging, helpers
```

## Build System

| Script | Purpose |
|---|---|
| `python setup.py py2app` | Build `.app` bundle (Python 3.11.8, rumps, tkinter, yaml) |
| `bash scripts/build-dmg.sh` | Full pipeline: py2app → asset copy → @rpath fix → codesign → DMG |
| `bash scripts/test-dmg.sh` | End-to-end GUI validation: DMG integrity, install, stability, osascript menu bar, settings window, clean shutdown |
| `bash scripts/ci-smoke-test.sh` | Headless CI validation: bundle structure, imports, 15s stability |

Build produces `dist/Clairvoyant-Optics-5.1.0.dmg` (~15 MB).

## Testing

### Automated

```bash
bash scripts/test-dmg.sh dist/Clairvoyant-Optics-5.1.0.dmg  # 23 tests, full GUI lifecycle
bash scripts/ci-smoke-test.sh                                 # 19 tests, headless
```

### UAT

Full User Acceptance Testing spec in [UAT.md](UAT.md). 20 test cases, 8 fully automated (AUTOMATISOI ✅).

## Performance (MacBook Air M1, 8 GB)

| Component | Resolution | Inference | Load |
|---|---|---|---|
| YOLOv8n person detect | 640×360 | 5-10 ms | ~5% Neural Engine |
| InsightFace face detect | 1920×1080 | 20-40 ms | ~15% Neural Engine |
| ArcFace embedding | 224×224 | 10-20 ms | Rare |
| **Total RAM** | | | **~500-800 MB** |

## Known Limitations

- **ML models not bundled** — YOLO/InsightFace ONNX models are not included in the DMG (would bloat to 500+ MB). First-run detection downloads them or you place them in `models/`. Stubs currently return idle/no-camera state.
- **Live dark mode** — Settings window requires app restart to pick up theme changes. On backlog for future fix.
- **`home_ssids` resets on reinstall** — Home WiFi SSID list is stored in `config.yaml` inside the app data directory, which is cleared on fresh install.
- **Photos.app iCloud** — "Optimize Mac Storage" breaks face import. Use manual enrollment or download originals.
- **Self-signed camera certs** — Snap JPEG endpoints need `verify=False`.
- **Gatekeeper** — Right-click → Open once to trust permanently.

## Privacy & Security

- **100% local inference** — All ML runs on the M1 Neural Engine. No cloud APIs.
- **Face embeddings stored locally** — Never transmitted.
- **No secrets in the repo** — `.env`, `models/*.onnx`, and `photos/` are gitignored.

## License

Personal, non-commercial use. ML models from InsightFace are available for non-commercial research purposes per their [model zoo terms](https://github.com/deepinsight/insightface/blob/master/model_zoo/README.md).
