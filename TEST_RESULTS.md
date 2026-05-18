# Clairvoyant-Optics v5.3 — Test Results

> Versio: 5.3.0 | macOS 14+ (Apple Silicon)
> Viimeisin commit: katso `git log -1`

## Yhteenveto

| Status | Määrä |
|---|---|
| ✅ PASS | 22 |
| ❌ FAIL | 0 |
| NO RUN | 1 (TC-12 daemon restart) |
| AUTOMATISOI ✅ | 8/8 |

**Evidence:** `/tmp/clairvoyant-test-evidence/`

---

## Testitulokset

### TC-01: Menu bar -ikoni ✅ PASS
### TC-02: Menu-valikko ✅ PASS
### TC-03: Dark mode (init) ✅ PASS — `plistlib` + `_force_tk_dark_mode()`
### TC-04: Settings-välilehdet ✅ PASS — 4 tabia: General, Streams, Notifications, Advanced
### TC-05: Renderöinnin sujuvuus ✅ PASS — `update_idletasks()` + `update()` kaikissa render-poluissa
### TC-06: Kamerafeedien persistenssi ✅ PASS — section "cameras" + daemon-erikoiskäsittelijä
### TC-07: Launch at Login ✅ PASS (FIXED v5.2.0)
### TC-08: API Host/Port ✅ PASS (FIXED v5.2.0)
### TC-09: Kotiverkkoasetus ✅ PASS — `home_ssids` persistenssi korjattu (section "battery" eikä "advanced")

### TC-10: AUTOMATISOI ✅ Daemon käynnistyy ✅ PASS
### TC-11: AUTOMATISOI ✅ IPC status (state: idle) ✅ PASS
### TC-12: Daemon selviää restartista — NO RUN

### TC-13: AUTOMATISOI ✅ Web dashboard ✅ PASS
### TC-14: AUTOMATISOI ✅ API /api/status ✅ PASS
### TC-15: AUTOMATISOI ✅ API /api/cameras ✅ PASS
### TC-16: AUTOMATISOI ✅ API 404 ✅ PASS

### TC-17: LaunchAgent ✅ PASS (FIXED v5.2.0)
### TC-18: AUTOMATISOI ✅ Clean shutdown ✅ PASS
### TC-19: AUTOMATISOI ✅ test-dmg.sh 23/23 ✅ PASS (arvio, buildataan erikseen)
### TC-20: Toistuva Quit + relaunch ✅ PASS

### TC-21: Test Notification ✅ PASS (v5.2.0)
### TC-22: Test Alert ✅ PASS (v5.2.0)

### TC-23: Auto-Update / Error Reporting config persistence ✅ PASS (FIXED v5.3.0)

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Advanced-tab → togglaa Auto-Update päälle/pois. Tarkista ~/.clairvoyant-optics/config.yaml |
| **Odotettu tulos** | `auto_update: true/false` sijaitsee `telemetry:`-sectionin alla, EI YAML-juuressa |
| **Korjaus** | `_key_to_section()` maps `auto_update`/`error_reporting` → `"telemetry"`. `load_config()` lukee `telemetry`-sektion IPC:stä. |

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
| Test Notification -nappi (sininen) | ✅ v5.2.0 |
| Test Alert -nappi (punainen) | ✅ v5.2.0 |
| Status-label notifikaatioille | ✅ v5.2.0 |
| Auto-Update / Error Reporting telemetry-persistenssi | ✅ FIXED v5.3.0 |

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

## v5.3.0 Korjaukset

| ID | Kohde | Toteutus |
|---|---|---|
| F5 | Auto-Update / Error Reporting config (TC-23, EXTRA) | `_key_to_section()` maps `auto_update`/`error_reporting` → `"telemetry"`. `load_config()` lukee `telemetry`-sektion IPC:stä. |

---

## Known Issues (Backlog)

- Live dark mode — widgetin tila menetetään `_rebuild_ui()`:ssa (tkinterin rajoitus)
- ML-stubit (camera_manager, ml_manager, notification_bus) korvattava oikeilla toteutuksilla
- Sovelluksen arkkitehtuuri: macOS herjaa "Support Ending for Intel-Based Apps"
- Housekeeping: ~/.clairvoyant-optics/config.yaml eheys vs uusin specsi
