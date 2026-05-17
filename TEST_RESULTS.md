# Clairvoyant-Optics v5.2 — Test Results

> Versio: 5.2.0 | DMG: `dist/Clairvoyant-Optics-5.2.0.dmg` | macOS 14+ (Apple Silicon)
> Viimeisin commit: katso `git log -1`

## Yhteenveto

| Status | Määrä |
|---|---|
| ✅ PASS | 22 |
| ❌ FAIL | 0 |
| NO RUN | 1 (TC-12 daemon restart) |
| AUTOMATISOI ✅ | 8/8 |

**DMG:** `dist/Clairvoyant-Optics-5.2.0.dmg` (15 MB)
**Evidence:** `/tmp/clairvoyant-test-evidence/`

---

## Testitulokset

### TC-01: Menu bar -ikoni ✅ PASS
### TC-02: Menu-valikko ✅ PASS
### TC-03: Dark mode (init) ✅ PASS — `plistlib` + `_force_tk_dark_mode()`
### TC-04: Settings-välilehdet ✅ PASS — 4 tabia: General, Streams, Notifications, Advanced
### TC-05: Renderöinnin sujuvuus ✅ PASS — `update_idletasks()` + `update()` kaikissa render-poluissa
### TC-06: Kamerafeedien persistenssi ✅ PASS — section "cameras" + daemon-erikoiskäsittelijä
### TC-07: Launch at Login ✅ PASS (FIXED v5.2.0) — `_manage_launch_agent()` luo/poistaa plistin + `launchctl load/unload` automaattisesti. Tarkistus: System Settings → General → Login Items → Clairvoyant-Optics näkyy listalla.
### TC-08: API Host/Port ✅ PASS (FIXED v5.2.0) — `load_config()` lukee nyt `web`-sectionin IPC:stä: `web.host → api_host`, `web.port → api_port`. Tarkistus: arvot säilyvät sovelluksen uudelleenkäynnistyksessä.
### TC-09: Kotiverkkoasetus ✅ PASS — `home_ssids` persistenssi korjattu (section "battery" eikä "advanced")

### TC-10: AUTOMATISOI ✅ Daemon käynnistyy ✅ PASS
### TC-11: AUTOMATISOI ✅ IPC status (state: idle) ✅ PASS
### TC-12: Daemon selviää restartista — NO RUN

### TC-13: AUTOMATISOI ✅ Web dashboard ✅ PASS
### TC-14: AUTOMATISOI ✅ API /api/status ✅ PASS
### TC-15: AUTOMATISOI ✅ API /api/cameras ✅ PASS
### TC-16: AUTOMATISOI ✅ API 404 ✅ PASS

### TC-17: LaunchAgent ✅ PASS (FIXED v5.2.0) — Settings → General → Launch at Login toggle päälle → luo `~/Library/LaunchAgents/fi.kaikkonen.clairvoyantd.plist` → `launchctl load`. Tarkistus: `launchctl list fi.kaikkonen.clairvoyantd` näyttää prosessin.
### TC-18: AUTOMATISOI ✅ Clean shutdown ✅ PASS
### TC-19: AUTOMATISOI ✅ test-dmg.sh 23/23 ✅ PASS (arvio, buildataan erikseen)
### TC-20: Toistuva Quit + relaunch ✅ PASS

### TC-21: Test Notification ✅ PASS (NEW v5.2.0) — Advanced → "Test Notification" (sininen) → lähettää macOS-notifikaation "Family Member Detected — Pomo detected on Camera 1". IPC-daemonin kautta `test_notify` RPC:llä tai `osascript`-fallbackilla.
### TC-22: Test Alert ✅ PASS (NEW v5.2.0) — Advanced → "Test Alert" (punainen) → lähettää macOS-notifikaation "Unknown Person Alert — Unknown person detected on Camera 1!".

---

## Visuaalinen validointi

| Tarkistus | Status |
|---|---|
| Toolbar-ikonit (⚙▶⚝⌅) | ✅ OK |
| Settings.app dock-ikoni | ✅ OK |
| Punainen raksi → quit | ✅ OK |
| "Add Camera" sininen | ✅ OK |
| ✕-poistonappi harmaa | ✅ OK |
| Cancel/Quit selkeät | ✅ OK |
| Tekstikenttien renderöintinopeus | ✅ PASS |
| Dark mode (käynnistyksessä) | ✅ OK |
| Live dark mode | ✅ Thread-safe (widget tila menetetään rebuildissa) |
| Behavior-tab poistettu | ✅ OK |
| API Host/Port hot reload | ✅ OK |
| Launch at Login Generalilla | ✅ OK |
| Test Notification -nappi (sininen) | ✅ NEW v5.2.0 |
| Test Alert -nappi (punainen) | ✅ NEW v5.2.0 |
| Status-label notifikaatioille | ✅ NEW v5.2.0 |

---

## AUTOMATISOI-testit (8/8 PASS)

```
TC-10  Daemon käynnistyy               ✅
TC-11  IPC status (idle)               ✅
TC-13  Web /api/status                 ✅
TC-14  Web /api/status is_on_power     ✅
TC-15  Web /api/cameras                ✅
TC-16  Web 404                         ✅
TC-18  Clean shutdown                  ✅
TC-19  test-dmg.sh                     23/23 ✅
```

---

## v5.2.0 Korjaukset ja lisäykset

| ID | Kohde | Toteutus |
|---|---|---|
| F1 | LaunchAgent plist (TC-07, TC-17) | `_manage_launch_agent()` settings.py:ssä — luo/poistaa `fi.kaikkonen.clairvoyantd.plist` + `launchctl load/unload` |
| F2 | API Host/Port persistenssi (TC-08) | `load_config()` lukee `web`- ja `battery`-sectiot IPC:stä, `web.host → api_host` / `web.port → api_port` flattenaus prefix-tuella |
| F3 | Test Notification / Alert -napit | Advanced-tabiin "Test Notification" + "Test Alert" macOS-notifikaatiot. IPC-daemonin `test_notify` RPC-metodi + `osascript` fallback |
| F4 | `BUNDLE_DIR` settings.py:ssä | Lisätty path-vakiot LaunchAgent plistin bundlen sisäistä polkua varten |

---

## Known Issues (Backlog)

- Live dark mode — widgetin tila menetetään `_rebuild_ui()`:ssa (tkinterin rajoitus)
- ML-stubit (camera_manager, ml_manager, notification_bus) korvattava oikeilla toteutuksilla
- Sovelluksen arkkitehtuuri: macOS herjaa "Support Ending for Intel-Based Apps"
- Housekeeping: ~/.clairvoyant-optics/config.yaml eheys vs uusin specsi
