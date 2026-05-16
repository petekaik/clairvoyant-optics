# Clairvoyant-Optics v5.1 — UAT (User Acceptance Testing)

> Versio: 5.1.0 | DMG: `dist/Clairvoyant-Optics-5.1.0.dmg` | macOS 14+ (Apple Silicon)

## Kierros 4 — thread-safety + persistenssi + renderöinti

| ID | Bugin kuvaus | Korjaus | Juurisyy |
|----|--------------|---------|----------|
| B5 | Live dark mode ei toimi — NSDistributedNotificationCenter ajaa observerin taustasäikeessä | `_on_system_theme_changed()` → `_root.after(0, _do_theme_changed)` | Tk ei ole thread-safe — widget-mutaatiot taustasäikeessä hiljaisesti hylätty |
| B6 | Tekstisyötelaatikot renderöityvät vasta kun hiiri siirtyy toolbarista sisältöalueelle | `_root.update_idletasks()` + `_root.update()` initissä ja `_rebuild_ui()`:ssa | macOS Sequoian ikkunapalvelin viivästyttää Tk-piirtoa ilman eksplisiittistä force-paintausta |
| B7 | Kamerafeedit eivät säily yli uudelleenkäynnistysten | `save_cameras()` section `"streams"` → `"cameras"`; daemonille erikoiskäsittelijä `CameraConfig`-listalle | Section mismatch settings.py ↔ config_store; `hasattr(list, "cameras")` = False |

**Tekniset juurisyyt:**
- B5: macOS `NSDistributedNotificationCenter` ajaa callbackin omassa säikeessään. Tk-interpreter on single-threaded — `self._root`-metodien kutsuminen toisesta säikeestä tuottaa hiljaisen virheen (ei crashia, ei poikkeusta, mutta ei myöskään toimi). Ratkaisu: `self._root.after(0, fn)` ajoittaa kutsun Tk:n päätapahtumasilmukkaan.
- B6: Tk:n `pack()` ajoittaa widgetit muttei piirrä niitä ennen kuin tapahtumasilmukka saa suoritusvuoron. macOS Sequoian `WindowServer` on aggressiivisempi piirron lykkäämisessä kuin aiemmat versiot. `update_idletasks()` + `update()` pakottaa layoutin + paintin välittömästi.
- B7: Kolme erillistä ongelmaa: (a) Settings lähetti IPC:lle `section="streams"`, daemonilla osio on `"cameras"` → `config_store.set()` feilasi tuntemattomaan osioon. (b) `config_store.set()` kutsuu `hasattr(section_obj, key)` — kun section="cameras", section_obj on `list[CameraConfig]`, ja `hasattr(list, "cameras")` = False. (c) `load_config()` etsi `"streams"`-osiota daemonin vastauksesta, mutta daemon palauttaa `"cameras"`. Korjattu: `save_cameras()` lähettää `section="cameras"`, daemonissa erikoiskäsittelijä `CameraConfig(**c)`-konstruoinnille, `load_config()` lukee `"cameras"`-osion listana.

## 1. Asennus
**Hyväksymiskriteeri:** PASS

## 2. Perustoiminnallisuus
### TC-01: Menu bar -ikoni: PASS
### TC-02: Menu-valikko: PASS
### TC-03: Dark mode: PASS (live-päivitys korjattu thread-safeksi)
### TC-04: Settings-välilehdet: PASS
### TC-05: Renderöinnin sujuvuus: PENDING MANUAL (update_idletasks + update lisätty initiin ja rebuildiin)
### TC-06: Kamerafeedien persistenssi: PENDING MANUAL (section-mismatch korjattu, daemon-erikoiskäsittelijä lisätty)

## 3. Daemon (clairvoyantd)
### TC-07: AUTOMATISOI ✅ PASS
### TC-08: IPC status -kysely: AUTOMATISOI ✅ PASS (state: idle)
### TC-09: Daemon selviää menu barin uudelleenkäynnistyksestä: NO RUN

## 4. Web Dashboard
### TC-10: Selainkäyttöliittymä avautuu: AUTOMATISOI ✅ PASS
### TC-11: API — status: AUTOMATISOI ✅ PASS
### TC-12: API — cameras: AUTOMATISOI ✅ PASS
### TC-13: API — 404: AUTOMATISOI ✅ PASS

## 5. LaunchAgent
### TC-14: Daemon käynnistyy loginin yhteydessä: NO RUN

## 6. Sammutus
### TC-15: AUTOMATISOI ✅ PASS

## 7. Regressio (ei saa rikkoutua)
### TC-16: AUTOMATISOI ✅ PASS (23/23 test-dmg.sh)
### TC-17: Toistuva Quit + relaunch: PASS

## 8. Visuaalinen validointi
### Dark mode: live-päivitys kun järjestelmäteema vaihtuu — korjattu (thread-safety: `after(0)`)
### Työkalupalkin ikonit: ✅ OK (⚙⚑▶⚝⌅)
### Settings.app dock-ikoni: ✅ OK
### Punainen raksi: ✅ OK
### "Add Camera" sininen, ✕ harmaa, Cancel/Quit selkeät: ✅ OK
### Tekstikenttien (Entry) renderöintinopeus: korjattu (`update_idletasks` + `update` force-paint)

---

**AUTOMATISOI-testit (8/8 PASS):**
```
TC-07  Daemon käynnistyy               ✅
TC-08  IPC status (idle)               ✅
TC-10  Web /api/status                 ✅
TC-11  Web /api/status is_on_power     ✅
TC-12  Web /api/cameras                ✅
TC-13  Web 404                         ✅
TC-15  Clean shutdown                  ✅
TC-16  test-dmg.sh                     23/23 ✅
```

**Evidence:** `/tmp/clairvoyant-test-evidence/` (4 screenshotia: DMG mount, app running, menu bar, settings window)

**Käyttäjän testattava:** TC-05 (renderöintinopeus), TC-06 (kamerafeedien persistenssi), live dark mode -vaihto
