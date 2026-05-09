# BACKLOG

## In Progress

- **Auto-DevOps-silmukka:** Versioiva agentti + Hermes cron -job, joka pollaa GitHub-repon avoimia vikoja, validoi ne ja käynnistää automaattiset korjaukset. Täysi Continuous Development/Testing/Monitoring -silmukka asennettujen sovellusten ja GitHubin välillä.

## Done (v2.2.0)

- ✅ **Virheraportointi → GitHub Issues** — `src/macos/error_reporter.py`: kaappaa käsittelemättömät poikkeukset ja luo automaattisesti GitHub Issue -lipun stack tracella, järjestelmätiedoilla ja redaktoiduilla ympäristömuuttujilla. Sisältää deduplikoinnin (`auto-reported` + `bug` -labelit).

## Done (v2.1.0)

- ✅ **Testipainikkeet hallintakäyttöliittymässä** — "Test Family" ja "Test Alert" -painikkeet per kamera, lähettävät live snapin ja oikean notifikaation.
- ✅ **.dmg-paketointi** — `setup.py` (py2app) + `scripts/build-dmg.sh` + GitHub Actions workflow (`.github/workflows/build.yml`). Buildaa `.app`-bundlen ja `.dmg`-asentajan jokaisesta commitista.
- ✅ **Automaattipäivitys** — `src/macos/updater.py` tarkistaa GitHub Releasesin ja lataa/asentaa uuden version. "Check for Updates..." menubarissa.
