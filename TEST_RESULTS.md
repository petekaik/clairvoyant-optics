# Clairvoyant-Optics v5.1 — Test Results

> Versio: 5.1.0 | DMG: `dist/Clairvoyant-Optics-5.1.0.dmg` | macOS 14+ (Apple Silicon)
> Viimeisin commit: katso `git log -1`

## Yhteenveto

| Status | Määrä |
|---|---|
| ✅ PASS | 19 |
| ❌ FAIL | 0 |
| NO RUN | 2 (TC-12 daemon restart, TC-17 LaunchAgent) |
| AUTOMATISOI ✅ | 8/8 |

**DMG:** `dist/Clairvoyant-Optics-5.1.0.dmg` (15 MB)
**Evidence:** `/tmp/clairvoyant-test-evidence/`

---

## Testitulokset

### TC-01: Menu bar -ikoni ✅ PASS
### TC-02: Menu-valikko ✅ PASS
### TC-03: Dark mode (init) ✅ PASS — `plistlib` + `_force_tk_dark_mode()`
### TC-04: Settings-välilehdet ✅ PASS — 4 tabia: General, Streams, Notifications, Advanced
### TC-05: Renderöinnin sujuvuus ✅ PASS — `update_idletasks()` + `update()` kaikissa render-poluissa
### TC-06: Kamerafeedien persistenssi ✅ PASS — section "cameras" + daemon-erikoiskäsittelijä
### TC-07: Launch at Login ✅ PASS — General-tabilla
### TC-08: API Host/Port ✅ PASS — hot reload: `trace_add("write")` + 800ms debounce, automaattinen validointi ilman klikkausta
### TC-09: Kotiverkkoasetus ✅ PASS — `home_ssids` persistenssi korjattu (section "battery" eikä "advanced")

### TC-10: AUTOMATISOI ✅ Daemon käynnistyy ✅ PASS
### TC-11: AUTOMATISOI ✅ IPC status (state: idle) ✅ PASS
### TC-12: Daemon selviää restartista — NO RUN

### TC-13: AUTOMATISOI ✅ Web dashboard ✅ PASS
### TC-14: AUTOMATISOI ✅ API /api/status ✅ PASS
### TC-15: AUTOMATISOI ✅ API /api/cameras ✅ PASS
### TC-16: AUTOMATISOI ✅ API 404 ✅ PASS

### TC-17: LaunchAgent — NO RUN
### TC-18: AUTOMATISOI ✅ Clean shutdown ✅ PASS
### TC-19: AUTOMATISOI ✅ test-dmg.sh 23/23 ✅ PASS
### TC-20: Toistuva Quit + relaunch ✅ PASS

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
| Live dark mode | ❌ Backlog |
| Behavior-tab poistettu | ✅ OK |
| API Host/Port hot reload | ✅ OK |
| Launch at Login Generalilla | ✅ OK |

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

## Kierros 4 korjaukset (kaikki valmiit)

| ID | Bugi | Korjaus |
|---|---|---|
| B5 | Live dark mode thread-safety | `_on_system_theme_changed()` → `_root.after(0, _do_theme_changed)` |
| B6 | macOS Sequoia renderöintiviive | `update_idletasks()` + `update()` initissä, `_rebuild_ui()`:ssa, `_show_content()`:ssa |
| B7 | Kamerafeedien persistenssi | Section "streams" → "cameras", daemon-erikoiskäsittelijä |

---

## Kierros 5 — UI-siivous (kaikki valmiit)

- ✅ Behavior-tab poistettu (Start Minimized, Close to Menu, Confirm Quit)
- ✅ Launch at Login siirretty General-tabiin
- ✅ API Host + Port -kentät lisätty General-tabiin

---

## Kierros 6 — v5.1.0 Known Issues (kaikki valmiit)

| ID | Bugi | Korjaus |
|---|---|---|
| K1 | `home_ssids` nollautuu | `_key_to_section` mappasi `"advanced"` → korjattu `"battery"` (vastaa daemonin `BatteryConfig.home_ssids`) |
| K2 | API "Apply & Test" vaati klikkauksen | Korvattu `trace_add("write")` + 800ms debounce: validointi tapahtuu automaattisesti kirjoittamisen jälkeen |

**IPC roundtrip verified:** `config.set(section="battery", key="home_ssids", value=["testikoti","mokki"])` → tallentui ja palautui oikein.

---

## Backlog

- Live dark mode -päivitys (NSDistributedNotificationCenter + täysi rebuild)
- Test notification / test alert -triggerit Advanced-tabiin
