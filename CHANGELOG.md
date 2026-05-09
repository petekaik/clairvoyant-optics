# Changelog

All notable changes to Clairvoyant-Optics.

## [2.1.0] — 2026-05-10

### Added
- **Test buttons in web dashboard** — per-camera "Test Family" and "Test Alert" buttons that fire real macOS notifications with a live camera snapshot.
- **`.dmg` packaging pipeline** — `setup.py` (py2app), `scripts/build-dmg.sh`, and GitHub Actions CI (`.github/workflows/build.yml`). Every push builds a self-contained `.app` bundle and `.dmg` installer.
- **Auto-update system** — `src/macos/updater.py` checks GitHub Releases, downloads and installs new versions. "Check for Updates..." menu item in the menubar.
- **Version tracking** — `src/version.py` as single source of truth for version across build, update, and release tooling.

### Fixed
- Menubar app now includes "Check for Updates..." item with full callback wiring (was added to declaration but missing from menu list and callback registration in v2.0.0).

## [2.0.0] — 2026-05-10

### Added
- **macOS Photos.app integration** — import face galleries directly from Photos.app via `osxphotos`. Zero manual photo copying. All 10 persons detected on first test.
- **Native macOS notifications** — `MacNotifier` using `macos-notifications` (pure Python). Family members get a subtle notification, strangers trigger an alert sound. DND window support.
- **Menubar application** — `rumps`-based status bar app with live pipeline status, pause/resume toggle, and dashboard link.
- **Web dashboard** — FastAPI server at `localhost:8765` with REST API for status, cameras, enrolled faces, detection history, and live snapshots.
- **Full CLI** — `clairvoyant start|enroll|import-from-photos|list-faces|serve` commands via `src/cli.py`.
- **Optional Home Assistant** — MQTT integration remains but is now optional. Pipeline runs fully standalone when no `MQTT_BROKER` is configured.
- **`pyproject.toml`** — package metadata and `clairvoyant` entry point for `pip install -e .`.

### Changed
- Pipeline output: MQTT-first → notification-first. MQTT only activates when `MQTT_BROKER` is set in `.env`.
- Configuration: added `NOTIFICATION_SOUND_*`, `NOTIFICATION_DND_*`, `WEB_UI_*` env vars.
- `.gitignore`: added `data/` for runtime SQLite database.

### Known Limitations
- Photos.app iCloud optimization (`ismissing=True`) blocks face import for most users. Manual enrollment or downloading originals required.
- Snap JPEG endpoints with self-signed certs require `verify=False`.

## [1.0.0] — 2026-05-08

### Added
- Initial release: HLS stream ingestion, YOLOv8n person detection, InsightFace/ArcFace face recognition, MQTT→Home Assistant integration.
- Model download script (`download_models.py`) with SourceForge fallback.
- Docker support for containerized deployment.
- Face enrollment from local photo directories.
