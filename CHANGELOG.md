# Changelog

All notable changes to Clairvoyant-Optics.

## [5.1.0] — 2026-05-15

### Architecture (v5 — service-oriented)

- **IPC-based three-layer architecture** — daemon (clairvoyantd), desktop (menu bar + settings + web dashboard), service stubs (camera_manager, ml_manager, notification_bus)
- Unix domain socket communication at `~/.clairvoyant-optics/ipc.sock`
- Config store with YAML persistence + SIGHUP reload
- State machine orchestrator (idle → starting → running → stopping)

### Added

- **Apple HIG settings window** — toolbar-based tab layout (macOS System Settings style), SF fonts, full dark mode support
- **`_mac_button()` helper** — tk.Label-based buttons that respect macOS dark mode (tk.Button ignores `bg` on macOS)
- **`_force_tk_dark_mode()`** — `::tk::unsupported::MacWindowStyle appearance dark` for correct Tk dark rendering
- **Dark mode detection** — `plistlib` reads `.GlobalProperties.plist` directly (Strategy 0)
- **API Host/Port configuration** — General tab: Host + Port Entry fields with 800ms debounce hot reload, automatic socket bind validation with green/red status feedback
- **Launch at Login toggle** — General tab, persisted via IPC
- **Settings.app wrapper** — standalone `.app` bundle that launches settings window, visible in Dock
- **Settings window hotkeys** — ⌘S (Settings), ⌘, (Settings), ⌘Q (Quit)

### Fixed

- **macOS Sequoia render delay (B6)** — `update_idletasks()` + `update()` across all three render paths (`__init__`, `_rebuild_ui()`, `_show_content()`) to force immediate paint through WindowServer
- **Thread-safe dark mode (B5)** — `NSDistributedNotificationCenter` observer runs in background thread → `self._root.after(0, _do_theme_changed)` for Tk thread-safety
- **Camera persistence (B7)** — section name mismatch (`"streams"` vs `"cameras"`), daemon special-case handler for `list[CameraConfig]` data
- **Settings red close button** — `_on_close()` always calls `_quit()`, never `withdraw()`
- **tk.Button contrast** in dark mode → replaced with `_mac_button()` throughout

- **`home_ssids` section mapping** — `_key_to_section()` mapped `home_ssids` to `"advanced"` but daemon expects `"battery"` → fixed to `"battery"` (matches `BatteryConfig`), verified IPC roundtrip
- **API hot reload** — "Apply & Test" button replaced with `trace_add("write")` + 800ms debounce, validation fires automatically on keystroke

### Changed

- **Settings tabs reduced to 4** — General, Streams, Notifications, Advanced (Behavior tab removed: Start Minimized, Close to Menu, Confirm Quit removed)
- **Launch at Login moved** from Behavior → General tab
- **`NSRequiresAquaSystemAppearance=False`** in Info.plist for native window chrome dark mode

### Known Issues (Backlog)

- Live dark mode update (no-restart theme switch) — thread-safety partial fix, full fix deferred

## [2.2.0] — 2026-05-10

### Added
- **Error reporting to GitHub Issues** — `src/macos/error_reporter.py`: catches unhandled exceptions, deduplicates them, and auto-creates GitHub Issues with stack trace, system info, and redacted environment variables. Install with `install_error_reporter()` in main entry point.
- **Auto-DevOps loop** — `scripts/devops-loop.py`: scheduled via Hermes cron, monitors GitHub CI status, detects unpushed commits, and reports on build health. Foundation for autonomous CI/CD self-healing.

### Fixed
- **Build pipeline** — `pyproject.toml` had wrong backend (`setuptools.backends._legacy:_Backend` → `setuptools.build_meta`), causing `pip install -e .` to fail and CI to crash with exit code 2.
- **CI workflow** — removed `brew install create-dmg` dependency (unreliable on GitHub Actions runners), switched to built-in `hdiutil`. Added `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true` to resolve Node.js 20 deprecation warnings.
- **`setup.py`** — removed `sqlite3` from packages list (stdlib, not a pip package); fixed iconfile handling for absent `icon.icns`.

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
