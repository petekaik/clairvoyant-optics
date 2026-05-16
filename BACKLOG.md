# BACKLOG

## v5.1.0 — Known Issues

- **Live dark mode update** — Settings-ikkuna ei päivity automaattisesti kun macOS-teema vaihtuu. `NSDistributedNotificationCenter` observer + `AppleInterfaceThemeChangedNotification` kuuntelee vaihtoa, mutta thread-safety ei ole täysin ratkaistu. `root.after(0)` -kierto toimii osittain, mutta koko ikkunan re-renderöinti vaatii `_rebuild_ui()`-kutsun, joka tuhoaa widget-tilan. Matala prioriteetti — käyttäjä näkee oikean teeman aina käynnistyksen yhteydessä `plistlib`-detektion kautta.
- **`home_ssids` nollautuu uudelleenasennuksessa** — `config.yaml` on sovelluksen datakansiossa (`~/.clairvoyant-optics/`), joka ei säily jos käyttäjä poistaa ja asentaa sovelluksen uudelleen. Vaatii joko erillisen pysyvän tallennuspaikan tai varoituksen ennen poistoa.
- **API hot reload** — Host/Port-kentät vaativat manuaalisen "Apply & Test" -klikkauksen. `trace_add("write")` hot-reload toimisi, mutta portin saatavuuden tarkistus jokaisella näppäinpainalluksella olisi raskas. Vaihtoehto: debounce + automaattinen validointi.

## v5.2.0 — Suunnitellut

- **Test notification trigger** — Advanced-tabiin "Test Notification" ja "Test Alert" -painikkeet työpöytänotifikaatioiden testaamiseksi ilman oikeaa kameraa. Vaatii `notification_bus.py`-stubin korvaamisen oikealla toteutuksella.
- **ML-stubien korvaaminen** — `camera_manager.py`, `ml_manager.py`, `notification_bus.py` stubit korvataan oikeilla toteutuksilla. YOLOv8n/InsightFace-mallien lazy-load DMG:n koon minimoimiseksi.
- **Models download first-run** — Automaattinen ONNX-mallien lataus ensimmäisellä käynnistyksellä (YOLOv8n, InsightFace detection + recognition). Vaatii network access -oikeudet.
- **Face enrollment UI** — GUI-pohjainen kasvojen rekisteröinti Settings-ikkunassa.

## v5.3.0 — Tiekartta

- **Web dashboard -testipainikkeet** — Per-kamera "Test Family" ja "Test Alert" -painikkeet web dashboardiin (tuotu v2.1.0:sta).
- **MQTT-integraatio** — Home Assistant -yhteensopivuus, `src/integration/` käyttöönotto.
- **Telemetry** — Käyttöstatistiikka ja virheenseuranta (opt-in).
- **macOS 15 (Sequoia) optimoinnit** — `WindowServer`-viiveet, `LSUIElement`-käyttäytyminen.

## Valmiit (Done)

- ✅ **v5.1.0** — Service-oriented architecture: IPC-daemon, HIG settings, dark mode, camera persist, Launch at Login, API Host/Port
- ✅ **v2.2.0** — Error reporting to GitHub Issues, auto-DevOps loop
- ✅ **v2.1.0** — DMG packaging, auto-update, web dashboard test buttons
- ✅ **v2.0.0** — macOS Photos.app integration, native notifications, menubar app, web dashboard, Home Assistant MQTT
