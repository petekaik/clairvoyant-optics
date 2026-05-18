# BACKLOG

## v5.4.0 — Current (2026-05-19)

- ✅ **Web Dashboard hot reload** — `web_dashboard.py main()` lukee nyt `config.yaml`:n web.host, web.port, web.enabled. `menu_bar.py` monitoroi web-config-muutoksia poll-loopissa ja restartaa web serverin automaattisesti.
- ✅ **ConfigStore.on_change** — Section-spesifinen callback `set()`-kutsulle (käytetään web-config muutosten monitorointiin).
- ✅ **YAML string representer** — Stringit joissa kaksoispiste kvotoidaan automaattisesti (estää YAML 1.1 sexagesimaaliparsinnan DND-kellonajoilla).
- ✅ **Home WiFi UX** — List-view Add/Delete + Enter binding (kuten kamerafeedeissä).

## v5.5.0 — Tiekartta

- **ML-stubien korvaaminen** — `camera_manager.py`, `ml_manager.py`, `notification_bus.py` stubit korvataan oikeilla toteutuksilla. YOLOv8n/InsightFace-mallien lazy-load DMG:n koon minimoimiseksi.
- **Models download first-run** — Automaattinen ONNX-mallien lataus ensimmäisellä käynnistyksellä (YOLOv8n, InsightFace detection + recognition). Vaatii network access -oikeudet.
- **Face enrollment UI** — GUI-pohjainen kasvojen rekisteröinti Settings-ikkunassa.
- **Web dashboard -testipainikkeet** — Per-kamera "Test Family" ja "Test Alert" -painikkeet web dashboardiin (tuotu v2.1.0:sta).
- **MQTT-integraatio** — Home Assistant -yhteensopivuus, `src/integration/` käyttöönotto.
- **Telemetry** — Käyttöstatistiikka ja virheenseuranta (opt-in).
- **macOS 15 (Sequoia) optimoinnit** — `WindowServer`-viiveet, `LSUIElement`-käyttäytyminen.

## Housekeeping (ongoing)

- ✅ ~~varmista ~/.clairvoyant-optics/config.yaml eheys ja että se vastaa viimeisimmän sovellusversion specsiä~~ (YAML persist + custom representer korjattu)
- ✅ ~~varmista, että sovelluksen ensiasennus & käynnistys luo viimeisimmän specsin mukaisen konfiguraatiotiedoston "sane defaults" arvoilla~~ (DEFAULT_CONFIG_YAML ajantasalla)

## Valmiit (Done)

- ✅ **v5.4.0** — Web Dashboard hot reload, ConfigStore.on_change, YAML string representer, Home WiFi UX
- ✅ **v5.3.2** — UAT v5.3.1 4 bugia: Sounds, DND YAML, Home WiFi UX, API Server config
- ✅ **v5.3.1** — Config mapping fix (11 EXTRA bugs: IPC key mapping, section-aware YAML, type coercion)
- ✅ **v5.3.0** — Auto-Update / Error Reporting config persistence fix (telemetry section mapping)
- ✅ **v5.2.0** — LaunchAgent plist automation, API Host/Port persistence fix, Test Notification/Alert buttons, live dark mode thread-safety
- ✅ **v5.1.0** — Service-oriented architecture: IPC-daemon, HIG settings, dark mode, camera persist, Launch at Login, API Host/Port hot reload, home_ssids persistenssi
- ✅ **v2.2.0** — Error reporting to GitHub Issues, auto-DevOps loop
- ✅ **v2.1.0** — DMG packaging, auto-update, web dashboard test buttons
- ✅ **v2.0.0** — macOS Photos.app integration, native notifications, menubar app, web dashboard, Home Assistant MQTT
