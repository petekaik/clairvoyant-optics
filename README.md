# Clairvoyant-Optics

**Privacy-first face recognition for home surveillance cameras.** Runs entirely on-device — no images, video, or personal data ever leave your local network.

## Overview

Clairvoyant-Optics identifies family members from surveillance camera feeds using a local ML pipeline optimized for Apple Silicon (M1+). It reads HLS video streams from MediaMTX, performs person detection on low-resolution frames, and triggers high-resolution face recognition only when a person is present — keeping resource usage minimal without sacrificing accuracy.

```
MediaMTX HLS (640×360) ──→ YOLOv8n Person Detect ──→ InsightFace Face Recognition ──→ MQTT ──→ Home Assistant
       low-res stream            ONNX, 5-10ms               Snap JPEG 1080p, 20-40ms       paho-mqtt
```

### Why HLS + Snap JPEG instead of direct RTSP?

- **HLS low-res stream**: continuous person detection at 640×360 using only 9% of the pixels of 1080p — fast and lightweight on the M1 Neural Engine
- **Snap JPEG 1080p**: fetched on-demand only when a person is detected — provides full-resolution frames for accurate face recognition
- **RTSPS between cameras and MediaMTX**: encrypted transport (SRTP), keeping the camera feed secure even on the wire

## Requirements

| Component | Details |
|---|---|
| **Hardware** | MacBook Air M1 (or any Apple Silicon Mac) with 8+ GB RAM |
| **Python** | 3.11+ |
| **Streaming** | MediaMTX serving HLS + RTSPS streams from UniFi cameras |
| **Smart Home** | Home Assistant with MQTT broker (Mosquitto) |
| **Cameras** | Any RTSP-capable camera; tested with UniFi G3 |

## Installation

### 1. Clone and set up

```bash
git clone git@github.com:petekaik/clairvoyant-optics.git
cd Clairvoyant-Optics
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your actual values (see configuration table below)
```

### 3. Download ML models

```bash
python download_models.py
```

This downloads and exports:
- **YOLOv8n** (12 MB ONNX) — person detection via Ultralytics
- **InsightFace buffalo_l** — face detection (det_10g.onnx, 16 MB) + face recognition (w600k_r50.onnx, 166 MB)

All models are stored in `models/` (gitignored).

### 4. Enroll family members

Create a folder for each family member with 5–10 photos showing their face from different angles and lighting conditions:

```bash
mkdir -p photos/alice
# Copy photos to photos/alice/

# Enroll
python -m src.main --enroll "Alice" photos/alice/

# List registered faces
python -m src.main --list-faces
```

**The `photos/` directory is gitignored — family photos are never committed to the repository.**

### 5. Run the pipeline

```bash
python -m src.main
```

The pipeline runs continuously, detecting persons from HLS streams and recognizing faces from snap JPEG images. Results are published to Home Assistant via MQTT.

## Configuration Reference

Edit `.env` after copying from `.env.example`:

### Cameras

```ini
# Camera 1 (front yard)
CAM1_STREAM=http://192.168.1.100:8888/front-yard/index.m3u8
CAM1_SNAP=https://192.168.1.101/snap.jpeg
CAM1_NAME=front_yard

# Camera 2 (backyard)
CAM2_STREAM=http://192.168.1.100:8888/backyard/index.m3u8
CAM2_SNAP=https://192.168.1.102/snap.jpeg
CAM2_NAME=backyard

# Add CAM3, CAM4, ... for additional cameras
```

| Variable | Description | Example |
|---|---|---|
| `CAM*_STREAM` | HLS stream URL from MediaMTX | `http://192.168.1.100:8888/front-yard/index.m3u8` |
| `CAM*_SNAP` | Snap JPEG URL from the camera (1080p preferred) | `https://192.168.1.101/snap.jpeg` |
| `CAM*_NAME` | Friendly name for logging and MQTT topics | `front_yard` |

### MQTT (Home Assistant)

```ini
MQTT_BROKER=192.168.1.100
MQTT_PORT=1883
MQTT_USERNAME=hass
MQTT_PASSWORD=your_password_here
MQTT_TOPIC_PREFIX=clairvoyant
```

### Detection thresholds

```ini
PERSON_DETECT_CONFIDENCE=0.5    # YOLOv8n person class confidence
FACE_DETECT_CONFIDENCE=0.7      # InsightFace detection confidence
FACE_RECOGNITION_THRESHOLD=0.6  # Cosine similarity threshold for matching
FRAME_INTERVAL=5                # Process every Nth HLS frame
LOG_LEVEL=INFO                  # DEBUG, INFO, WARNING, ERROR
```

## MQTT Topics

The pipeline publishes to these topics under the configured prefix (default `clairvoyant`):

| Topic | Payload | When |
|---|---|---|
| `clairvoyant/status` | `online` / `offline` | Connection state (LWT) |
| `clairvoyant/{camera}/person` | `{"name", "camera", "confidence", "timestamp"}` | Family member recognized |
| `clairvoyant/{camera}/unknown` | `{"camera", "timestamp", "bbox"}` | Unknown person detected |
| `clairvoyant/{camera}/person_gone` | `{"name", "camera", "timestamp"}` | Person left the frame |

### Example Home Assistant sensor

```yaml
mqtt:
  sensor:
    - name: "Front Yard Person"
      state_topic: "clairvoyant/front_yard/person"
      value_template: "{{ value_json.name }}"
      json_attributes_topic: "clairvoyant/front_yard/person"
```

## Architecture

```
src/
├── main.py              # Pipeline orchestrator: stream → detect → snap → recognize → MQTT
├── config.py            # .env loader, typed dataclass configuration
├── streams/
│   └── hls_reader.py    # Background HLS stream reader with auto-reconnect
├── detection/
│   └── person_detector.py  # YOLOv8n ONNX/CoreML — person class filtering
├── recognition/
│   └── face_recognizer.py  # InsightFace + ArcFace face recognition, SQLite embedding DB
├── integration/
│   └── mqtt_notifier.py # paho-mqtt — person/unknown/person_gone events
└── utils/
    └── logging.py       # Structured logging setup
```

## Docker

For containerized deployment:

```bash
docker compose -f docker/docker-compose.yml up -d
```

Note: Docker images must be built locally on Apple Silicon — pre-built x86_64 images won't run on M1.

## Privacy & Security

- **100% local inference** — all ML runs on the M1 Neural Engine; no cloud APIs, no images uploaded anywhere
- **Encrypted camera links** — RTSPS between cameras and MediaMTX uses SRTP encryption
- **Face embeddings stored locally** — SQLite database in `data/faces.db`, never transmitted
- **No secrets in the repo** — `.env`, `models/*.onnx`, and `photos/` are all gitignored
- **Suitable for households with children** — designed from the ground up with privacy as a hard requirement

## Performance (MacBook Air M1, 8 GB)

| Component | Resolution | Inference Time | Freq | Load |
|---|---|---|---|---|
| YOLOv8n person-detect | 640×360 | ~5–10 ms | 2–3 fps | Minimal |
| InsightFace face-detect | 1920×1080 | ~20–40 ms | On person detected | Rare |
| ArcFace embedding | 224×224 | ~10–20 ms | On person detected | Rare |
| **Total RAM** | | | | **~500–800 MB** |

With two cameras active, CPU load stays around 15–25%.

## License

This project is for personal, non-commercial use. ML models from InsightFace are available for non-commercial research purposes only per their [model zoo terms](https://github.com/deepinsight/insightface/blob/master/model_zoo/README.md).
