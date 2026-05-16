# Clairvoyant-Optics v5.1 — UAT (User Acceptance Testing)

> Versio: 5.1.0 | DMG: `dist/Clairvoyant-Optics-5.1.0.dmg` | macOS 14+ (Apple Silicon)

---

## 1. Asennus

### 1.1 Lataa ja asenna DMG:stä

```
1. Lataa Clairvoyant-Optics-5.1.0.dmg Releases-sivulta
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

### TC-01: Menu bar -ikoni

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Käynnistä sovellus, katso menu baria |
| **Odotettu tulos** | Silmä-ikoni näkyy menu barissa, EI tekstiä "Clairvoyant-Optics" |
| **Tarkistus** | Klikkaa ikonia → menu aukeaa |

### TC-02: Menu-valikko

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Klikkaa silmä-ikonia menu barissa |
| **Odotettu tulos** | Menu sisältää: `● Idle`, `Cameras`, `▶ Start`, `⏸ Stop`, `Settings…`, `Web Dashboard`, `Quit Clairvoyant-Optics` |
| **Tarkistus** | Kaikki 7 kohtaa näkyvissä, Start/Stop erotettu separatorilla |

### TC-03: Settings-ikkuna (Settings.app wrapper)

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Valitse menu barista `Settings…` (tai ⌘S) |
| **Odotettu tulos** | Settings-ikkuna aukeaa. Ikkunassa on toolbar-välilehdet vasemmalla |
| **Tarkistus A** | Ikkunan yläreunassa on macOS-liikennevalot (punainen/keltainen/vihreä) |
| **Tarkistus B** | Ikkuna on dark mode -teemalla (tai vaalea, macOS-järjestelmäasetuksen mukaan) |
| **Tarkistus C** | Fontit ovat macOS SF -tyyppisiä (ei Times New Roman / Courier) |

### TC-04: Settings-välilehdet

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Klikkaa läpi jokainen välilehti Settings-ikkunassa |
| **Odotettu tulos** | Välilehdet: `General`, `Cameras`, `Detection`, `Models`, `Notifications`, `Battery`, `Web`, `MQTT`, `Telemetry` |
| **Tarkistus** | Jokainen välilehti näyttää omat asetuksensa, ei tyhjää paneelia |

### TC-05: Asetuksen muutos + persistointi

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Vaihda `General` → `Log Level` arvoon `DEBUG`. Sulje Settings-ikkuna. |
| **Odotettu tulos** | `~/.clairvoyant-optics/config.yaml` sisältää `log_level: DEBUG` |
| **Tarkistus** | `grep log_level ~/.clairvoyant-optics/config.yaml` näyttää `DEBUG` |

### TC-06: Asetukset säilyvät uudelleenkäynnistyksessä

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Tapa sovellus (Quit), käynnistä uudelleen, avaa Settings |
| **Odotettu tulos** | `Log Level` on edelleen `DEBUG` |
| **Tarkistus** | Settings-ikkuna näyttää aiemmin asetetun arvon |

---

## 3. Daemon (clairvoyantd)

### TC-07: Daemon käynnistyy automaattisesti

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Käynnistä sovellus, odota 10 sekuntia |
| **Odotettu tulos** | Menu barin status muuttuu `✕ Disconnected` → `○ Idle` |
| **Tarkistus** | `ls -la ~/.clairvoyant-optics/ipc.sock` → socketti on olemassa |

### TC-08: IPC status -kysely

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Terminal: `echo '{"method":"status","params":{},"id":1}' \| nc -U ~/.clairvoyant-optics/ipc.sock` |
| **Odotettu tulos** | JSON-vastaus: `"state": "idle"`, `"is_on_power": true`, `"uptime_seconds": >0` |
| **Tarkistus** | Ei `"error"`-kenttää vastauksessa |

### TC-09: Daemon selviää menu barin uudelleenkäynnistyksestä

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Quit menu barista, käynnistä uudelleen, odota 10s |
| **Odotettu tulos** | Status palaa `○ Idle`, ei `✕ Disconnected` |
| **Tarkistus** | IPC-socketti toimii edelleen |

---

## 4. Web Dashboard

### TC-10: Selainkäyttöliittymä avautuu

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Valitse menu barista `Web Dashboard` |
| **Odotettu tulos** | Selain aukeaa osoitteeseen `http://127.0.0.1:8765` |
| **Tarkistus A** | Sivulla on otsikko "Clairvoyant-Optics Dashboard" |
| **Tarkistus B** | Sivu on dark mode -teemalla (tumma tausta, vaalea teksti) |

### TC-11: API — status

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Terminal: `curl -s http://127.0.0.1:8765/api/status` |
| **Odotettu tulos** | JSON: `"state": "idle"`, `"is_on_power": true` |
| **Tarkistus** | HTTP 200, validi JSON |

### TC-12: API — cameras

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Terminal: `curl -s http://127.0.0.1:8765/api/cameras` |
| **Odotettu tulos** | JSON: `"cameras": []` (tyhjä lista, koska ei kameroita konfiguroitu) |
| **Tarkistus** | HTTP 200, validi JSON |

### TC-13: API — 404

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Terminal: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/api/nonexistent` |
| **Odotettu tulos** | HTTP 404 |
| **Tarkistus** | Ei kaada palvelinta |

---

## 5. LaunchAgent

### TC-14: Daemon käynnistyy loginin yhteydessä

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | `cp assets/fi.kaikkonen.clairvoyantd.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/fi.kaikkonen.clairvoyantd.plist` |
| **Odotettu tulos** | Daemon-prosessi käynnistyy (pgrep näyttää sen) |
| **Tarkistus A** | `pgrep -fl daemon.py` → löytyy |
| **Tarkistus B** | IPC-socketti luotu |
| **Siivous** | `launchctl unload ~/Library/LaunchAgents/fi.kaikkonen.clairvoyantd.plist && rm ~/Library/LaunchAgents/fi.kaikkonen.clairvoyantd.plist` |

---

## 6. Sammutus

### TC-15: Clean shutdown

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Valitse menu barista `Quit Clairvoyant-Optics` |
| **Odotettu tulos** | Sovellus sammuu. Menu bar -ikoni katoaa. |
| **Tarkistus A** | `pgrep -fl menu_bar` → ei tulosta |
| **Tarkistus B** | `pgrep -fl daemon` → daemon-prosessia ei enää ole (tai se on erillinen LaunchAgent-prosessi) |
| **Tarkistus C** | `pgrep -fl web_dashboard` → ei tulosta |

---

## 7. Regressio (ei saa rikkoutua)

### TC-16: Sovellus ei kaadu 60 sekunnissa

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Käynnistä sovellus, odota 60s |
| **Odotettu tulos** | Sovellus edelleen käynnissä, menu bar -ikoni näkyvissä |
| **Tarkistus** | `kill -0 $(pgrep -f menu_bar.py)` → onnistuu |

### TC-17: Toistuva Quit + relaunch

| Kohde | Kuvaus |
|---|---|
| **Toimenpide** | Quit → käynnistä → Quit → käynnistä (3 kertaa) |
| **Odotettu tulos** | Joka kerta sovellus käynnistyy normaalisti, ikoni ilmestyy |
| **Tarkistus** | IPC-yhteys muodostuu joka kerta, ei jää zombie-prosesseja |

---

## 8. Visuaalinen validointi

Vertaile Settings-ikkunaa näihin HIG-referensseihin:

- macOS System Settings (cmd+space → "System Settings") — toolbar-välilehdet vasemmalla
- macOS HIG: [Toolbars](https://developer.apple.com/design/human-interface-guidelines/toolbars)
- Dark mode: taustaväri ~`#1e1e20`, kortit ~`#2c2c2e`, teksti ~`#f5f5f7`

**Nopea silmämääräinen tarkistus:**

```
1. Avaa Settings-ikkuna
2. Aseta ikkuna vierekkäin macOS System Settings -ikkunan kanssa
3. Tarkista:
   [ ] Välilehtipaneeli vasemmalla (ei ylhäällä tabbar)
   [ ] Liikennevalot ikkunan vasemmassa yläkulmassa
   [ ] Tumma tausta (jos dark mode päällä)
   [ ] Ei Windows-tyylistä reunusta tai otsikkopalkkia
   [ ] Fontti on sama kuin System Settingsissä
```

---

## Yhteenveto

| Testi | Tyyppi | Automaatio |
|---|---|---|
| TC-01 … TC-02 | Menu bar | test-dmg.sh Phase 5 |
| TC-03 … TC-06 | Settings | test-dmg.sh Phase 6 |
| TC-07 … TC-09 | Daemon IPC | ci-smoke-test.sh |
| TC-10 … TC-13 | Web dashboard | curl (manuaalinen) |
| TC-14 | LaunchAgent | launchctl (manuaalinen) |
| TC-15 | Shutdown | test-dmg.sh Phase 7 |
| TC-16 … TC-17 | Regressio | test-dmg.sh Phase 4 |

**Automaattinen ajo:** `bash scripts/test-dmg.sh dist/Clairvoyant-Optics-5.1.0.dmg` kattaa TC:t 01–06, 15–17.

**Manuaalisesti suoritettavat:** TC-10–13 (curl), TC-14 (LaunchAgent), visuaalinen validointi.
