# Clairvoyant-Optics v5.3 — UAT (User Acceptance Testing)

> Versio: 5.3.0 | DMG: `dist/Clairvoyant-Optics-5.3.0.dmg` | macOS 14+ (Apple Silicon)

---

## 1. Asennus

### 1.1 Lataa ja asenna DMG:stä

```
1. Lataa Clairvoyant-Optics-5.3.0.dmg Releases-sivulta
2. Kaksoisklikkaa DMG → aukeaa Finder-ikkuna
3. Raahaa Clairvoyant-Optics.app → Applications-kansioon
4. Sulje DMG-ikkuna, ejecttaa DMG-levy
```

**Hyväksymiskriteeri:** `.app` kopioituu `/Applications/Clairvoyant-Optics.app`.

### 1.2 Gatekeeper-ohitus (ensimmäinen käynnistys)

```
1. Avaa Finder → Applications
2. KLIKKAA OIKEALLA Clairvoyant-Optics.app → valitse "Open"
3. Klikkaa "Open" varoitusdialogissa
```

**Hyväksymiskriteeri:** Sovellus käynnistyy, silmä-ikoni ilmestyy menu bariin (kellon viereen).

> Tämä tarvitsee tehdä vain kerran. macOS muistaa poikkeuksen.

---

## 2. Perustoiminnallisuus

### TC-01: Menu bar -ikoni ✅ PASS

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Käynnistä sovellus, katso menu baria |
| **Odotettu tulos** | Silmä-ikoni näkyy menu barissa, EI tekstiä "Clairvoyant-Optics" |
| **Tarkistus** | Klikkaa ikonia → menu aukeaa |

### TC-02: Menu-valikko ✅ PASS

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Klikkaa silmä-ikonia menu barissa |
| **Odotettu tulos** | Menu sisältää: `● Idle`, `Cameras`, `▶ Start`, `⏸ Stop`, `Settings…`, `Web Dashboard`, `Quit Clairvoyant-Optics` |
| **Tarkistus** | Kaikki 7 kohtaa näkyvissä, Start/Stop erotettu separatorilla |

### TC-03: Dark mode ✅ PASS

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Avaa Settings. Vaihda macOS System Settings → Appearance → Dark/Light |
| **Odotettu tulos** | Settings-ikkuna noudattaa järjestelmäteemaa käynnistyksessä |
| **Tunnettu rajoitus** | Live dark mode -päivitys tuhoaa widget-tilan rebuildissa; thread-safety korjattu `root.after(0)`-kuviolla |

### TC-04: Settings-välilehdet ✅ PASS

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Klikkaa läpi jokainen välilehti Settings-ikkunassa |
| **Odotettu tulos** | 4 välilehteä: `General`, `Streams`, `Notifications`, `Advanced` |
| **Tarkistus** | Jokainen välilehti näyttää omat asetuksensa, ei tyhjää paneelia. Toolbar-pohjainen macOS HIG -ulkoasu |

### TC-05: Renderöinnin sujuvuus ✅ PASS

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Avaa Settings, klikkaa läpi kaikki tabit |
| **Odotettu tulos** | Entry-kentät ja widgetit renderöityvät välittömästi, ei viivettä |
| **Tarkistus** | Tekstikentät näkyvät heti tab-vaihdon jälkeen, eivät vasta hiiren siirron jälkeen |
| **Korjaus** | `_show_content()` kutsuu `update_idletasks()` + `update()` macOS Sequoian WindowServer-viiveen kiertämiseksi |

### TC-06: Kamerafeedien persistenssi ✅ PASS

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Lisää kamera Streams-tabilla, tallenna. Sulje ja avaa Settings uudelleen |
| **Odotettu tulos** | Kamera näkyy edelleen Streams-tabilla |
| **Korjaus** | Section "streams" → "cameras", daemon-erikoiskäsittelijä CameraConfig-listalle |

### TC-07: Launch at Login ✅ PASS (FIXED v5.2.0)

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | General-tab → "Launch at Login" toggle päälle. Avaa System Settings → General → Login Items |
| **Odotettu tulos** | Clairvoyant-Optics näkyy Login Items -listalla |
| **Korjaus** | `_manage_launch_agent()` luo/poistaa `fi.kaikkonen.clairvoyantd.plist` + `launchctl load/unload` automaattisesti |

### TC-08: API Host/Port — hot reload ✅ PASS (FIXED v5.2.0)

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | General-tab → API Server -osio. Kirjoita uusi Host tai Port |
| **Odotettu tulos onnistuessa** | ✅ `127.0.0.1:8765 — saved` (vihreä, ilmestyy 800ms viiveellä) |
| **Odotettu tulos epäonnistuessa** | ❌ (punainen virheviesti: port varattu, virheellinen arvo jne.) |
| **Korjaus** | `load_config()` lukee nyt `web`-sectionin IPC:stä: `web.host → api_host`, `web.port → api_port` |

### TC-09: Kotiverkkoasetus ✅ PASS

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Advanced → Home WiFi → SSIDs. Aseta verkko. Käynnistä sovellus uudelleen |
| **Odotettu tulos** | Asetus säilyy `~/.clairvoyant-optics/config.yaml` -tiedostossa daemonin `battery.home_ssids`-kentässä |
| **Korjaus** | `_key_to_section` mappasi `home_ssids → "advanced"`, daemon odotti `"battery"` → korjattu |

---

## 3. Daemon (clairvoyantd)

### TC-10: AUTOMATISOI ✅ Daemon käynnistyy ✅ PASS

### TC-11: AUTOMATISOI ✅ IPC status -kysely ✅ PASS (state: idle)

Tarkistus: `echo '{"method":"status","params":{},"id":1}' | nc -U ~/.clairvoyant-optics/ipc.sock`

### TC-12: Daemon selviää menu barin uudelleenkäynnistyksestä — NO RUN (manuaalinen)

---

## 4. Web Dashboard

### TC-13: AUTOMATISOI ✅ Selainkäyttöliittymä avautuu ✅ PASS

### TC-14: AUTOMATISOI ✅ API — status ✅ PASS

### TC-15: AUTOMATISOI ✅ API — cameras ✅ PASS

### TC-16: AUTOMATISOI ✅ API — 404 ✅ PASS

---

## 5. LaunchAgent

### TC-17: Daemon käynnistyy loginin yhteydessä — ✅ PASS (FIXED v5.2.0)

```
Settings → General → Launch at Login toggle päälle →
  → luo ~/Library/LaunchAgents/fi.kaikkonen.clairvoyantd.plist
  → launchctl load
```

---

## 6. Sammutus

### TC-18: AUTOMATISOI ✅ Clean shutdown ✅ PASS

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Valitse menu barista `Quit Clairvoyant-Optics` |
| **Odotettu tulos** | Sovellus sammuu. Menu bar -ikoni katoaa. |
| **Tarkistus A** | `pgrep -fl menu_bar` → ei tulosta |
| **Tarkistus B** | Daemon ja web dashboard siivottu |

---

## 7. Regressio (ei saa rikkoutua)

### TC-19: AUTOMATISOI ✅ test-dmg.sh 23/23 ✅ PASS

### TC-20: Toistuva Quit + relaunch ✅ PASS

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Quit → käynnistä → Quit → käynnistä (3 kertaa) |
| **Odotettu tulos** | Joka kerta sovellus käynnistyy normaalisti, ikoni ilmestyy |
| **Tarkistus** | IPC-yhteys muodostuu joka kerta, ei jää zombie-prosesseja |

---

## 8. Uudet ominaisuudet (v5.2.0)

### TC-21: Test Notification ✅ PASS

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Advanced → Test Notifications → "Test Notification" (sininen) |
| **Odotettu tulos** | macOS-notifikaatio "Family Member Detected — 👤 Pomo detected on Camera 1" |
| **Tarkistus** | Status-label näyttää "✅ Notification sent" |

### TC-22: Test Alert ✅ PASS

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Advanced → Test Notifications → "Test Alert" (punainen) |
| **Odotettu tulos** | macOS-notifikaatio "⚠ Unknown Person Alert — Unknown person detected on Camera 1!" |
| **Tarkistus** | Status-label näyttää "✅ Notification sent" |

---

## 9. Uudet ominaisuudet (v5.3.0)

### TC-23: Auto-Update / Error Reporting config persistence ✅ PASS (FIXED v5.3.0)

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Advanced-tab → togglaa Auto-Update päälle → tarkista `~/.clairvoyant-optics/config.yaml` |
| **Odotettu tulos** | `auto_update: true` sijaitsee `telemetry:`-sectionin alla, EI YAML-tiedoston juuressa |
| **Korjaus** | `_key_to_section()` maps `auto_update`/`error_reporting` → `"telemetry"`. `load_config()` lukee `telemetry`-sektion IPC:stä. |

---

## 10. Visuaalinen validointi

| Tarkistus | Status |
|---|---|
| Työkalupalkin ikonit (⚙▶⚝⌅) | ✅ OK |
| Settings.app dock-ikoni | ✅ OK |
| Punainen raksi → quit | ✅ OK |
| "Add Camera" sininen, ✕ harmaa | ✅ OK |
| Cancel/Quit selkeät | ✅ OK |
| Tekstikenttien renderöintinopeus | ✅ PASS |
| Dark mode (käynnistyksessä) | ✅ OK |
| Live dark mode | ✅ Thread-safe (widget tila menetetään rebuildissa) |
| Test Notification -nappi | ✅ OK |
| Test Alert -nappi | ✅ OK |
| Auto-Update / Error Reporting telemetry-persistenssi | ✅ FIXED v5.3.0 |

Vertaile Settings-ikkunaa macOS System Settingsiin:
- Toolbar-välilehdet vasemmalla (ei ylhäällä tabbar)
- Liikennevalot vasemmassa yläkulmassa
- Tumma tausta dark modessa (tausta ~`#1e1e20`, kortit ~`#2c2c2e`, teksti ~`#f5f5f7`)
- SF-fontit (SF Pro Text, SF Mono)
- Ei Windows-tyylistä reunusta tai otsikkopalkkia

---

## Yhteenveto

| ID | Testi | Status | Tyyppi |
|---|---|---|---|
| TC-01 | Menu bar -ikoni | ✅ PASS | test-dmg.sh Phase 5 |
| TC-02 | Menu-valikko | ✅ PASS | test-dmg.sh Phase 5 |
| TC-03 | Dark mode (init) | ✅ PASS | Manuaalinen |
| TC-04 | Settings-välilehdet (4 tabia) | ✅ PASS | test-dmg.sh Phase 6 |
| TC-05 | Renderöinti sujuvuus | ✅ PASS | Manuaalinen |
| TC-06 | Kamerafeedien persistenssi | ✅ PASS | Manuaalinen |
| TC-07 | Launch at Login | ✅ PASS (FIXED v5.2.0) | Manuaalinen |
| TC-08 | API Host/Port (hot reload) | ✅ PASS (FIXED v5.2.0) | Manuaalinen |
| TC-09 | Kotiverkkoasetus | ✅ PASS | Manuaalinen |
| TC-10 | Daemon käynnistyy | ✅ AUTOMATISOI | ci-smoke-test.sh |
| TC-11 | IPC status | ✅ AUTOMATISOI | ci-smoke-test.sh |
| TC-12 | Daemon restart-selviytyminen | NO RUN | Manuaalinen |
| TC-13 | Web dashboard | ✅ AUTOMATISOI | curl |
| TC-14 | API /api/status | ✅ AUTOMATISOI | curl |
| TC-15 | API /api/cameras | ✅ AUTOMATISOI | curl |
| TC-16 | API 404 | ✅ AUTOMATISOI | curl |
| TC-17 | LaunchAgent | ✅ PASS (FIXED v5.2.0) | Manuaalinen |
| TC-18 | Clean shutdown | ✅ AUTOMATISOI | test-dmg.sh Phase 7 |
| TC-19 | test-dmg.sh 23/23 | ✅ AUTOMATISOI | test-dmg.sh |
| TC-20 | Toistuva Quit + relaunch | ✅ PASS | Manuaalinen |
| TC-21 | Test Notification | ✅ PASS | Manuaalinen |
| TC-22 | Test Alert | ✅ PASS | Manuaalinen |
| TC-23 | Auto-Update / Error Reporting config | ✅ PASS (FIXED v5.3.0) | Manuaalinen |

**AUTOMATISOI-testit (8/8 PASS):**
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

**Evidence:** `/tmp/clairvoyant-test-evidence/`
