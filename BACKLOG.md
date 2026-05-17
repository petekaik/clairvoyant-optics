# BACKLOG

## v5.2.0 — Current (2026-05-17)

- ✅ **LaunchAgent plist management** — Launch at Login toggle luo/poistaa plistin automaattisesti + `launchctl load/unload` (korjaa TC-07, TC-17)
- ✅ **API Host/Port persistence** — `load_config()` lukee `web`-sectionin IPC:stä: `host→api_host`, `port→api_port` (korjaa TC-08)
- ✅ **Test Notification/Alert buttons** — Advanced-tabiin "Test Notification" (sininen) ja "Test Alert" (punainen) -painikkeet. Lähettää oikean macOS-notifikaation IPC-daemonin kautta (`test_notify` RPC) tai `osascript`-fallbackilla
- ✅ **Live dark mode thread-safety** — `NSDistributedNotificationCenter` → `root.after(0, _do_theme_changed)` toteutus jo koodissa; widget-tila menetetään rebuildissa (tkinterin rajoitus, ei ratkaistavissa)

## v5.1.5 Mac Power
- Sovelluksen arkkitehtuurin korjaukset (Intel vs. MacOS M-series)
- MLX ja Neural Accelerators hyödyntäminen koneoppimisen malleissa (acceleration, power efficiency)

## Housekeeping task
- varmista ~/.clairvoyant-optics/config.yaml eheys ja että se vastaa viimeisimmän sovellusversion specsiä
- varmista, että sovelluksen ensiasennus & käynnistys luo viimeisimmän specsin mukaisen konfiguraatiotiedoston "sane defaults" arvoilla (lokaalin deviympäristön IP osoitteet ja salaisuudet eivät saa vuotaa)

## v5.3.0 — Tiekartta

- **ML-stubien korvaaminen** — `camera_manager.py`, `ml_manager.py`, `notification_bus.py` stubit korvataan oikeilla toteutuksilla. YOLOv8n/InsightFace-mallien lazy-load DMG:n koon minimoimiseksi.
- **Models download first-run** — Automaattinen ONNX-mallien lataus ensimmäisellä käynnistyksellä (YOLOv8n, InsightFace detection + recognition). Vaatii network access -oikeudet.
- **Face enrollment UI** — GUI-pohjainen kasvojen rekisteröinti Settings-ikkunassa.
- **Web dashboard -testipainikkeet** — Per-kamera "Test Family" ja "Test Alert" -painikkeet web dashboardiin (tuotu v2.1.0:sta).
- **MQTT-integraatio** — Home Assistant -yhteensopivuus, `src/integration/` käyttöönotto.
- **Telemetry** — Käyttöstatistiikka ja virheenseuranta (opt-in).
- **macOS 15 (Sequoia) optimoinnit** — `WindowServer`-viiveet, `LSUIElement`-käyttäytyminen.

## Valmiit (Done)

- ✅ **v5.2.0** — LaunchAgent plist automation, API Host/Port persistence fix, Test Notification/Alert buttons, live dark mode thread-safety
- ✅ **v5.1.0** — Service-oriented architecture: IPC-daemon, HIG settings, dark mode, camera persist, Launch at Login, API Host/Port hot reload, home_ssids persistenssi
- ✅ **v2.2.0** — Error reporting to GitHub Issues, auto-DevOps loop
- ✅ **v2.1.0** — DMG packaging, auto-update, web dashboard test buttons
- ✅ **v2.0.0** — macOS Photos.app integration, native notifications, menubar app, web dashboard, Home Assistant MQTT
