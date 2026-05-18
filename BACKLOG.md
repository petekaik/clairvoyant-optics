# BACKLOG

## v5.3.0 — Current (2026-05-18)

- ✅ **Auto-Update / Error Reporting config persistence** — `auto_update`/`error_reporting` toggles map to `telemetry` section instead of `advanced`. `_key_to_section()` + `load_config()` molemmat korjattu (korjaa TEST_RESULTS.md EXTRA-bugi)

## v5.2.5 Mac Power
- Sovelluksen arkkitehtuurin korjaukset (Intel vs. MacOS M-series)
- MLX ja Neural Accelerators hyödyntäminen koneoppimisen malleissa (acceleration, power efficiency)

## Housekeeping task
- varmista ~/.clairvoyant-optics/config.yaml eheys ja että se vastaa viimeisimmän sovellusversion specsiä
- varmista, että sovelluksen ensiasennus & käynnistys luo viimeisimmän specsin mukaisen konfiguraatiotiedoston "sane defaults" arvoilla (lokaalin deviympäristön IP osoitteet ja salaisuudet eivät saa vuotaa)

## v5.4.0 — Tiekartta

- **ML-stubien korvaaminen** — `camera_manager.py`, `ml_manager.py`, `notification_bus.py` stubit korvataan oikeilla toteutuksilla. YOLOv8n/InsightFace-mallien lazy-load DMG:n koon minimoimiseksi.
- **Models download first-run** — Automaattinen ONNX-mallien lataus ensimmäisellä käynnistyksellä (YOLOv8n, InsightFace detection + recognition). Vaatii network access -oikeudet.
- **Face enrollment UI** — GUI-pohjainen kasvojen rekisteröinti Settings-ikkunassa.
- **Web dashboard -testipainikkeet** — Per-kamera "Test Family" ja "Test Alert" -painikkeet web dashboardiin (tuotu v2.1.0:sta).
- **MQTT-integraatio** — Home Assistant -yhteensopivuus, `src/integration/` käyttöönotto.
- **Telemetry** — Käyttöstatistiikka ja virheenseuranta (opt-in).
- **macOS 15 (Sequoia) optimoinnit** — `WindowServer`-viiveet, `LSUIElement`-käyttäytyminen.

## Valmiit (Done)

- ✅ **v5.3.0** — Auto-Update / Error Reporting config persistence fix (telemetry section mapping)
- ✅ **v5.2.0** — LaunchAgent plist automation, API Host/Port persistence fix, Test Notification/Alert buttons, live dark mode thread-safety
- ✅ **v5.1.0** — Service-oriented architecture: IPC-daemon, HIG settings, dark mode, camera persist, Launch at Login, API Host/Port hot reload, home_ssids persistenssi
- ✅ **v2.2.0** — Error reporting to GitHub Issues, auto-DevOps loop
- ✅ **v2.1.0** — DMG packaging, auto-update, web dashboard test buttons
- ✅ **v2.0.0** — macOS Photos.app integration, native notifications, menubar app, web dashboard, Home Assistant MQTT
