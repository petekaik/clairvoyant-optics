"""macOS Menubar + Dashboard -sovellus — näkyy Dockissa ja menubarissa.

Arkkitehtuuri:
- pywebview: natiivi ikkuna web-dashboardille (näkyy Dockissa)
- rumps: menubar-kuvake ja kontrollit
- LSUIElement=false: Dock-ikoni näkyvissä, käyttäjä löytää sovelluksen
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

    def __init__(self_, title, menu, pipeline, web_port, on_quit):
        super().__init__(title, menu=menu, quit_button=None)
        self_._menu_status = menu[0]
        self_._menu_toggle = menu[2]
        self_._pipeline = pipeline
        self_._web_port = web_port
        self_._on_quit = on_quit

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

    def _toggle(self, _):
        if self_._pipeline is None:
            return
        if self_._pipeline._running:
            self_._pipeline.stop()
        else:
            self_._pipeline.optimizer._manual_override = True
            t = threading.Thread(target=self_._pipeline.start, daemon=True)
            t.start()

    def _open_dashboard(self, _):
        webbrowser.open(f"http://localhost:{self_._web_port}")

    def _check_updates(self, _):
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

    def _quit(self, _):
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
        web_port: int = 8765,
        on_quit: callable = None,
    ):
        self.pipeline = pipeline
        self.web_port = web_port
        self._on_quit = on_quit
        self._menubar = None
        self._webview_window = None

    @property
    def menubar_available(self) -> bool:
        return _HAS_RUMPS

    @property
    def webview_available(self) -> bool:
        return _HAS_WEBVIEW

    def run(self):
        """Käynnistä sovellus — webview-ikkuna + menubar."""
        dashboard_url = f"http://localhost:{self.web_port}"

        # 1. Käynnistä menubar taustalla
        if _HAS_RUMPS:
            self._start_menubar()

        # 2. Avaa webview-ikkuna (blokkaava kutsu — pysyy auki)
        if _HAS_WEBVIEW:
            logger.info(f"Opening dashboard window: {dashboard_url}")
            # webview.create_window blokkaa kunnes ikkuna suljetaan
            webview.create_window(
                "Clairvoyant-Optics",
                dashboard_url,
                width=1100,
                height=750,
                min_size=(800, 500),
                resizable=True,
            )
        else:
            # Fallback: avaa selaimeen
            logger.warning("pywebview not installed — opening in browser")
            webbrowser.open(dashboard_url)
            input("Press Enter to exit...\n")

        # Siivous
        if self._menubar is None:
            self._do_quit()

    def _start_menubar(self):
        """Käynnistä menubar erillisessä säikeessä."""
        status_item = rumps.MenuItem("Status: Idle")
        toggle_item = rumps.MenuItem("▶ Start")
        web_item = rumps.MenuItem(f"Dashboard (:{self.web_port})")
        update_item = rumps.MenuItem("Check for Updates...")
        quit_item = rumps.MenuItem("Quit")

        menu = [status_item, None, toggle_item, web_item, update_item, None, quit_item]

        self._menubar = _MenubarController(
            "Clairvoyant-Optics",
            menu,
            self.pipeline,
            self.web_port,
            self._on_quit,
        )

        toggle_item.set_callback(lambda s: s._toggle(s))
        web_item.set_callback(lambda s: s._open_dashboard(s))
        update_item.set_callback(lambda s: s._check_updates(s))
        quit_item.set_callback(lambda s: s._quit(s))

        t = threading.Thread(target=self._menubar.run, daemon=True)
        t.start()

    def _do_quit(self):
        if self.pipeline and self.pipeline._running:
            self.pipeline.stop()
        if self._on_quit:
            self._on_quit()
