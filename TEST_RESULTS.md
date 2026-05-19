# Clairvoyant-Optics v5.6.1 — Test Results

> Versio: 5.6.1 | macOS 14+ (Apple Silicon)
> Viimeisin commit: `git log -1`

## Yhteenveto

| Status | Määrä |
|---|---|
| ✅ PASS | 17 |
| ❌ FAIL | 0 |

## Testit

### GUI-yksikkötestit (7/7 PASS)
`PYTHONPATH=src:tests venv/bin/python -m unittest tests.test_gui_integration -v`
- test_window_opens_without_crash
- test_all_tabs_have_content
- test_canvas_window_has_width
- test_scrollbar_exists_and_configured
- test_mousewheel_binding
- test_faces_tab_has_widgets
- test_config_saves

### macOS GUI-testit (3/3 PASS)
`CLAIRVOYANT_CONFIG_DIR=/tmp/co_gui venv/bin/python -m unittest tests.test_gui_macos_combined -v`
- test_window_detected_by_atomacos
- test_window_has_correct_size
- test_tab_click_changes_content (pyautogui screenshot diff)

### Playwright E2E (7/7 PASS)
`venv/bin/python -m pytest tests/test_web_dashboard_e2e.py -v`
- test_dashboard_loads
- test_status_endpoint_returns_data
- test_health_endpoint_ok
- test_cameras_endpoint
- test_dashboard_not_empty
- test_models_endpoint

## v5.6.1 Korjaukset

| ID | Bugi | Juurisyy | Korjaus |
|---|---|---|---|
| F1 | **Settings avautuu hitaasti (10-15s)** | 1) `_ipc_call("config.get")` timeout 5s (daemon offline) 2) `from Foundation import ...` PyObjC-importti blokkaa ~2-3s initissä | 1) IPC timeout 5→1.5s 2) Dark mode observer init lazy: `_root.after(2000, ...)` |
| F2 | **Kaikki tabit tyhjinä** | `canvas.winfo_width()` palauttaa 1 unmapped windowilla Tk 8.6 → `1 or 400` = 1 → itemconfig(width=1) | `_content_frame.winfo_width()` guard: jos <50 → 400 |
| F3 | **Nimeäminen** | Geneeriset tiedostonimet (web_dashboard.py, app.py, settings.py) | Kaikki ajettavat komponentit `clairvoyant_`-etuliitteellä |
| F4 | **CI failure** | release.yml viittasi vanhaan web_dashboard.py-nimeen | Päivitetty → clairvoyant_web_dashboard.py |

## Known Issues (Backlog)

- Live dark mode — widgetin tila menetetään `_rebuild_ui()`:ssa (tkinterin rajoitus)
- atomacos macOS GUI-testit: tabipainikkeiden klikkaus ei toimi Tk 8.6 accessibility-rajoitteen vuoksi (odotetaan Tk 8.7:ää)
- Sovelluksen arkkitehtuuri: macOS herjaa "Support Ending for Intel-Based Apps"
