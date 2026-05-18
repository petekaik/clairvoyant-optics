# BACKLOG

## v5.6.0 — Current (2026-05-19)

- ✅ **Camera Manager (OpenCV HLS)** — `camera_manager.py` korvattu oikealla toteutuksella. Hoitaa HLSStreamReader-instanssit, snapshotit JPEG:nä, monitoroi kameroita 5s välein.
- ✅ **ML Manager (YOLOv8+InsightFace)** — `ml_manager.py` korvattu oikealla toteutuksella. Lazy-load mallit ensimmäisellä pipeline startilla. Taustalataus GitHubista (yolov8n.onnx 6MB, det_10g.onnx 17MB, w600k_r50.onnx 163MB). Latauksen edistyminen raportoitavissa IPC:n kautta.
- ✅ **Model download UI** — Uusi Models-tabi Settingsissa: lataustila (Not Downloaded/Downloading X%/Complete/Error), Download/Download All -napit, detection-asetukset (person_confidence, face_confidence, recognition_threshold, frame_interval, debounce_seconds).
- ✅ **Face enrollment UI** — Uusi Faces-tabi Settingsissa: rekisteröityjen kasvojen lista (name, camera, samples, last_seen), Delete-nappi, Enroll New Face (name entry + Capture -nappi).
- ✅ **IPC handlerit daemonille** — `ml.status`, `ml.download`, `ml.download_all`, `faces.list`, `faces.enroll`, `faces.delete`.
- ✅ **FaceDatabase parannukset** — `get_all_faces()` palauttaa `last_seen`, uusi `delete_face(name)` metodi.
- ✅ **Puuttuvat config-kentät Settings UI:hun** — log_level dropdown, notify_on_family/notify_on_unknown togglet, MQTT-osio (enabled, broker, port, username, password, topic_prefix), Battery-osio (pause_on_battery, pause_when_away, poll_interval).

## vnext

- **Data-säiliöt** — Tietokantapohjainen eventtihistoria (SQLite), detektioiden ja tunnistusten tallennus historian katseluun
- **Web dashboard UI-päivitys** — Real-time stream + detektio overlay, per-kamera testipainikkeet
- **MQTT-integraatio** — Home Assistant -yhteensopivuus, `src/integration/` käyttöönotto (UI-valmis)
- **Telemetry** — Käyttöstatistiikka ja virheenseuranta (opt-in)
- **macOS 15 (Sequoia) optimoinnit** — `WindowServer`-viiveet, `LSUIElement`-käyttäytyminen

## Valmiit (Done)

- ✅ **v5.5.0** — API Server statusindikaattori, Apple HIG -napit, Settings.app ikoni, web_dashboard.py bundlessa
- ✅ **v5.4.0** — Web Dashboard hot reload, ConfigStore.on_change, YAML string representer, Home WiFi UX
- ✅ **v5.3.2** — UAT v5.3.1 4 bugia: Sounds, DND YAML, Home WiFi UX, API Server config
- ✅ **v5.3.1** — Config mapping fix (11 EXTRA bugs: IPC key mapping, section-aware YAML, type coercion)
- ✅ **v5.3.0** — Auto-Update / Error Reporting config persistence fix (telemetry section mapping)
- ✅ **v5.2.0** — LaunchAgent plist automation, API Host/Port persistence fix, Test Notification/Alert buttons, live dark mode thread-safety
- ✅ **v5.1.0** — Service-oriented architecture: IPC-daemon, HIG settings, dark mode, camera persist, Launch at Login, API Host/Port hot reload, home_ssids persistenssi
- ✅ **v2.2.0** — Error reporting to GitHub Issues, auto-DevOps loop
- ✅ **v2.1.0** — DMG packaging, auto-update, web dashboard test buttons
- ✅ **v2.0.0** — macOS Photos.app integration, native notifications, menubar app, web dashboard, Home Assistant MQTT
