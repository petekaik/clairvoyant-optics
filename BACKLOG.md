# BACKLOG

## v5.5.0 — Current (2026-05-19)

- ✅ **API Server statusindikaattori** — HTTP heartbeat-tarkistus (`GET /api/status`). Näyttää "● Running" tai "○ Stopped". Päivittyy automaattisesti napin painalluksen ja host/port-muutoksen jälkeen.
- ✅ **Start/Stop/Restart -nappien Apple HIG -palpute** — Hover highlight, active flash (blue flash 200ms), disabled state harmaana. Custom tk.Frame-pohjaiset napit.
- ✅ **API Server -hallinta daemonissa** — `web_status`, `web_start`, `web_stop`, `web_restart` IPC handlerit daemonissa. Menu_bar ei enää hallitse web serveriä.
- ✅ **Settings.app dockissa silmäikoni** — `CFBundleIconFile` + `icon.icns` kopio Settings.appin Resourcesiin.
- ✅ **web_dashboard.py bundlessa** — Kopioidaan release.yml:ssä Resourcesiin (puuttui → DMG:stä ei käynnistynyt).

## vnext

- **Data-säiliöt** — Tietokantapohjainen eventtihistoria (SQLite), detektioiden ja tunnistusten tallennus
- **Face enrollment GUI** — Kasvojen rekisteröinti Settings-ikkunassa (kamera feed + capture + name)
- **ML-stubit → oikeat mallit** — YOLOv8n/InsightFace lazy-load
- **MQTT-integraatio** — Home Assistant -yhteensopivuus, `src/integration/` käyttöönotto
- **Web dashboard UI-päivitys** — Real-time stream + detektio overlay, per-kamera testipainikkeet
- **Telemetry** — Käyttöstatistiikka ja virheenseuranta (opt-in)
- **macOS 15 (Sequoia) optimoinnit** — `WindowServer`-viiveet, `LSUIElement`-käyttäytyminen

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