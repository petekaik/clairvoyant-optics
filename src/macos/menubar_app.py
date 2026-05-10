"""macOS Menubar + Dashboard -sovellus — näkyy Dockissa ja menubarissa.

Arkkitehtuuri:
- pywebview: natiivi ikkuna web-dashboardille (näkyy Dockissa)
- rumps: menubar-kuvake ja kontrollit
- LSUIElement=false: Dock-ikoni näkyvissä, käyttäjä löytää sovelluksen
- Updater: automaattinen taustatarkistus (opt-in: AUTO_UPDATE=true)
"""

import logging
import threading
import webbrowser

logger = logging.getLogger(__name__)

_HAS_RUMPS = False
try:
    import rumps
    _HAS_RUMPS = True
except ImportError:
    pass

_HAS_WEBVIEW = False
try:
    import webview
    _HAS_WEBVIEW = True
except ImportError:
    pass


class _MenubarController(rumps.App if _HAS_RUMPS else object):
    """Rumps-menubar-sovellus — pikakontrollit."""

    def __init__(self_, title, menu, pipeline, web_port, on_quit, config):
        super().__init__(title, menu=menu, quit_button=None)
        self_._menu_status = menu[0]
        self_._menu_toggle = menu[2]
        self_._menu_auto_update = menu[7]  # index Auto-Update riviä
        self_._menu_error_rpt = menu[9]   # index Error Reporting riviä
        self_._pipeline = pipeline
        self_._web_port = web_port
        self_._on_quit = on_quit
        self_._config = config
        self_._last_update_notified: str = ""  # vältä spam-notifikaatioita

    @rumps.timer(5)
    def _update_title(self_, _):
        if self_._pipeline and self_._pipeline._running:
            self_.title = "👁"
        else:
            self_.title = "⏸"

    @rumps.timer(3)
    def _update_status(self_, _):
        opt = self_._pipeline.optimizer if self_._pipeline else None
        if self_._pipeline and self_._pipeline._running:
            cam_count = len(self_._pipeline.streams)
            face_count = len(self_._pipeline.face_db.get_all_faces())
            extra = ""
            if opt:
                bat = opt._last_battery_pct
                ssid = opt._last_ssid
                parts = []
                if bat is not None:
                    parts.append(f"{'🔌' if opt.is_on_power else '🔋'} {bat}%")
                if ssid:
                    parts.append(f"📶 {ssid}")
                if parts:
                    extra = " · " + " ".join(parts)
            self_._menu_status.title = f"Status: {cam_count} cameras · {face_count} faces{extra}"
            self_._menu_toggle.title = "⏸ Pause"
        elif self_._pipeline and not self_._pipeline._running:
            reason = ""
            if opt and opt.suspended_reason:
                reason = f" ({opt.suspended_reason})"
            self_._menu_status.title = f"Status: Paused{reason}"
            self_._menu_toggle.title = "▶ Start"
        else:
            self_._menu_status.title = "Status: Idle"
            self_._menu_toggle.title = "▶ Start"

        # Päivitä opt-in/out -valikoiden tekstit
        if self_._config:
            self_._menu_auto_update.title = (
                "Auto-Update: ✅ ON" if self_._config.auto_update
                else "Auto-Update: ❌ OFF"
            )
            self_._menu_error_rpt.title = (
                "Error Reporting: ✅ ON" if self_._config.error_reporting
                else "Error Reporting: ❌ OFF"
            )

    def _toggle(self_, _):
        if self_._pipeline is None:
            return
        if self_._pipeline._running:
            self_._pipeline.stop()
        else:
            self_._pipeline.optimizer._manual_override = True
            t = threading.Thread(target=self_._pipeline.start, daemon=True)
            t.start()

    def _open_dashboard(self_, _):
        webbrowser.open(f"http://localhost:{self_._web_port}")

    def _check_updates(self_, _):
        try:
            from src.macos.updater import Updater, get_current_version
            updater = Updater(current_version=get_current_version())
            update = updater.check_for_update()
            if update:
                rumps.notification(
                    "Update Available",
                    f"Clairvoyant-Optics v{update['version']}",
                    "Click to download",
                )
                webbrowser.open(update["url"])
            else:
                rumps.notification("Up to Date", f"v{get_current_version()}", "")
        except Exception as e:
            logger.error(f"Update check failed: {e}")

    def _toggle_auto_update(self_, _):
        """Käännä AUTO_UPDATE päälle/pois + päivitä .env."""
        if not self_._config:
            return
        self_._config.auto_update = not self_._config.auto_update
        self_._persist_env("AUTO_UPDATE", "true" if self_._config.auto_update else "false")
        status = "✅ ON" if self_._config.auto_update else "❌ OFF"
        rumps.notification("Settings", f"Auto-Update: {status}", "")

        # Käynnistä/pysäytä taustatarkistus
        if hasattr(self_, "_updater"):
            if self_._config.auto_update:
                self_._updater.start_background()
            else:
                self_._updater.stop_background()

    def _toggle_error_reporting(self_, _):
        """Käännä ERROR_REPORTING päälle/pois + päivitä .env."""
        if not self_._config:
            return
        self_._config.error_reporting = not self_._config.error_reporting
        self_._persist_env("ERROR_REPORTING", "true" if self_._config.error_reporting else "false")
        status = "✅ ON" if self_._config.error_reporting else "❌ OFF"
        rumps.notification("Settings", f"Error Reporting: {status}", "")

    def _persist_env(self_, key: str, value: str):
        """Kirjoita avain=arvo .env-tiedostoon (päivitä tai lisää)."""
        import os as _os
        env_path = _os.path.expanduser("~/.hermes/.env")

        # Päivitä prosessin ympäristö heti
        _os.environ[key] = value

        try:
            if _os.path.exists(env_path):
                with open(env_path) as f:
                    lines = f.readlines()
            else:
                lines = []

            found = False
            for i, line in enumerate(lines):
                if line.strip().startswith(f"{key}="):
                    lines[i] = f"{key}={value}\n"
                    found = True
                    break

            if not found:
                lines.append(f"\n{key}={value}\n")

            with open(env_path, "w") as f:
                f.writelines(lines)

            logger.info(f"Persisted {key}={value} to {env_path}")
        except Exception as e:
            logger.error(f"Failed to persist {key}: {e}")

    def _quit(self_, _):
        logger.info("Quit from menubar")
        if self_._pipeline and self_._pipeline._running:
            self_._pipeline.stop()
        if self_._on_quit:
            self_._on_quit()
        rumps.quit_application()


class App:
    """Clairvoyant-Optics — macOS-sovellus (Dock + Menubar)."""

    def __init__(
        self,
        pipeline=None,
        config=None,
        web_port: int = 8765,
        on_quit: callable = None,
    ):
        self.pipeline = pipeline
        self.config = config
        self.web_port = web_port
        self._on_quit = on_quit
        self._menubar = None
        self._webview_window = None
        self._updater = None

    @property
    def menubar_available(self) -> bool:
        return _HAS_RUMPS

    @property
    def webview_available(self) -> bool:
        return _HAS_WEBVIEW

    def run(self):
        """Käynnistä sovellus — webview-ikkuna + menubar + opt-in taustapäivitys."""
        dashboard_url = f"http://localhost:{self.web_port}"

        # Käynnistä automaattipäivitys jos opt-in
        if self.config and self.config.auto_update:
            self._start_auto_updater()

        # 1. Käynnistä menubar taustalla
        if _HAS_RUMPS:
            self._start_menubar()

        # 2. Avaa webview-ikkuna (blokkaava kutsu — pysyy auki)
        if _HAS_WEBVIEW:
            logger.info(f"Opening dashboard window: {dashboard_url}")
            webview.create_window(
                "Clairvoyant-Optics",
                dashboard_url,
                width=1100,
                height=750,
                min_size=(800, 500),
                resizable=True,
            )
        else:
            logger.warning("pywebview not installed — opening in browser")
            webbrowser.open(dashboard_url)
            input("Press Enter to exit...\n")

        # Siivous
        if self._menubar is None:
            self._do_quit()

    def _start_auto_updater(self):
        """Käynnistä Updaterin taustatarkistus (blokkiutumaton)."""
        try:
            from src.macos.updater import Updater, get_current_version

            def _on_update(update_info: dict):
                """Callback: uusi versio löytyi → macOS-notifikaatio."""
                try:
                    v = update_info["version"]
                    # Vältä spam: älä ilmoita samasta versiosta kahdesti
                    if self._menubar and hasattr(self._menubar, "_last_update_notified"):
                        if self._menubar._last_update_notified == v:
                            return
                        self._menubar._last_update_notified = v

                    if _HAS_RUMPS:
                        rumps.notification(
                            "Update Available",
                            f"Clairvoyant-Optics v{v}",
                            "Click to download",
                        )
                    webbrowser.open(update_info["url"])
                except Exception as e:
                    logger.error(f"Update notification failed: {e}")

            self._updater = Updater(
                current_version=get_current_version(),
                on_update_available=_on_update,
            )
            self._updater.start_background()

            # Välitä menubarille viittaus jotta toggle toimii
            if self._menubar:
                self._menubar._updater = self._updater

            logger.info("Auto-update background checker started")
        except Exception as e:
            logger.error(f"Failed to start auto-updater: {e}")

    def _start_menubar(self):
        """Käynnistä menubar erillisessä säikeessä."""
        status_item = rumps.MenuItem("Status: Idle")
        toggle_item = rumps.MenuItem("▶ Start")
        web_item = rumps.MenuItem(f"Dashboard (:{self.web_port})")
        update_item = rumps.MenuItem("Check for Updates...")
        quit_item = rumps.MenuItem("Quit")

        # Opt-in/out togglet
        auto_update_item = rumps.MenuItem("Auto-Update: ❌ OFF")
        error_rpt_item = rumps.MenuItem("Error Reporting: ❌ OFF")

        menu = [
            status_item, None,          # 0: status, 1: ---
            toggle_item,                # 2: toggle
            web_item,                   # 3: dashboard
            update_item,                # 4: check updates
            None,                       # 5: ---
            auto_update_item,           # 6: auto-update toggle
            None,                       # 7: ---
            error_rpt_item,             # 8: error reporting toggle
            None,                       # 9: ---
            quit_item,                  # 10: quit
        ]

        self._menubar = _MenubarController(
            "Clairvoyant-Optics",
            menu,
            self.pipeline,
            self.web_port,
            self._on_quit,
            self.config,
        )

        toggle_item.set_callback(lambda s: s._toggle(s))
        web_item.set_callback(lambda s: s._open_dashboard(s))
        update_item.set_callback(lambda s: s._check_updates(s))
        auto_update_item.set_callback(lambda s: s._toggle_auto_update(s))
        error_rpt_item.set_callback(lambda s: s._toggle_error_reporting(s))
        quit_item.set_callback(lambda s: s._quit(s))

        t = threading.Thread(target=self._menubar.run, daemon=True)
        t.start()

    def _do_quit(self):
        # Pysäytä updater
        if self._updater:
            self._updater.stop_background()
        if self.pipeline and self.pipeline._running:
            self.pipeline.stop()
        if self._on_quit:
            self._on_quit()
