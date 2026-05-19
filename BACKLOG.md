# BACKLOG

## v5.7.0 — Current (2026-05-19)

- **Data-säiliöt** — Tietokantapohjainen eventtihistoria (SQLite), detektioiden ja tunnistusten tallennus historian katseluun
- **Web dashboard UI-päivitys** — Real-time stream + detektio overlay, per-kamera testipainikkeet
- **MQTT-integraatio** — Home Assistant -yhteensopivuus, `src/integration/` käyttöönotto (UI-valmis)
- **Telemetry** — Käyttöstatistiikka ja virheenseuranta (opt-in)
- **macOS 15 (Sequoia) optimoinnit** — `WindowServer`-viiveet, `LSUIElement`-käyttäytyminen

## Valmiit (Done)

- ✅ **v5.6.1** — Settings-ikkunan hidas avaus (10-15s → ~0.3s) ja tyhjät tabit korjattu. IPC timeout 5→1.5s, PyObjC lazy 2s init window mapped. Canvas width: _content_frame.winfo_width() guard <50→400 (korvaa rikkinäisen winfo_width() Tk 8.6:lla). Nimeäminen: kaikilla ajettavilla komponenteilla `clairvoyant_`-etuliite. macOS GUI-testit atomacos+pyautogui (3/3 PASS). Playwright E2E web dashboardille (7/7 PASS). 17/17 testiä läpi.
- ✅ **v5.6.0** — Camera Manager (OpenCV HLS), ML Manager (YOLOv8+InsightFace), Model download UI, Face enrollment UI, IPC handlerit, FaceDatabase parannukset, puuttuvat config-kentät
- ✅ **v5.5.0** — API Server statusindikaattori, Apple HIG -napit, Settings.app ikoni, clairvoyant_web_dashboard.py bundlessa
- ✅ **v5.4.0** — Web Dashboard hot reload, ConfigStore.on_change, YAML string representer, Home WiFi UX
- ✅ **v5.3.2** — UAT v5.3.1 4 bugia: Sounds, DND YAML, Home WiFi UX, API Server config
- ✅ **v5.3.1** — Config mapping fix (11 EXTRA bugs: IPC key mapping, section-aware YAML, type coercion)
- ✅ **v5.3.0** — Auto-Update / Error Reporting config persistence fix (telemetry section mapping)
- ✅ **v5.2.0** — LaunchAgent plist automation, API Host/Port persistence fix, Test Notification/Alert buttons, live dark mode thread-safety
- ✅ **v5.1.0** — Service-oriented architecture: IPC-daemon, HIG settings, dark mode, camera persist, Launch at Login, API Host/Port hot reload, home_ssids persistenssi
- ✅ **v2.2.0** — Error reporting to GitHub Issues, auto-DevOps loop
- ✅ **v2.1.0** — DMG packaging, auto-update, web dashboard test buttons
- ✅ **v2.0.0** — macOS Photos.app integration, native notifications, menubar app, web dashboard, Home Assistant MQTT
