"""macOS Menubar -sovellus rumps-kirjastolla.

Näyttää putken tilan, pikatoiminnot ja hallintapaneelin linkin.
"""

import logging
import threading

logger = logging.getLogger(__name__)

_HAS_RUMPS = False
try:
    import rumps
    _HAS_RUMPS = True
except ImportError:
    pass


class MenubarApp:
    """Clairvoyant-Optics macOS Menubar -sovellus."""

    def __init__(
        self,
        pipeline=None,
        web_port: int = 8765,
        on_quit: callable = None,
    ):
        self.pipeline = pipeline
        self.web_port = web_port
        self._on_quit = on_quit
        self._app = None

    @property
    def available(self) -> bool:
        return _HAS_RUMPS

    def run(self):
        """Käynnistä menubar-sovellus (blokkaa)."""
        if not _HAS_RUMPS:
            logger.warning("rumps not installed")
            return

        # Build menu items
        status_item = rumps.MenuItem("Status: Idle")

        toggle_item = rumps.MenuItem("▶ Start")

        web_item = rumps.MenuItem(
            f"Open Dashboard (:{self.web_port})",
        )

        quit_item = rumps.MenuItem("Quit")

        class ClairvoyantApp(rumps.App):
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
                if self_._pipeline and self_._pipeline._running:
                    cam_count = len(self_._pipeline.streams)
                    face_count = len(self_._pipeline.face_db.get_all_faces())
                    self_._menu_status.title = f"Status: {cam_count} cameras · {face_count} faces"
                    self_._menu_toggle.title = "⏸ Pause"
                elif self_._pipeline and not self_._pipeline._running:
                    self_._menu_status.title = "Status: Paused"
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
                    t = threading.Thread(target=self_._pipeline.start, daemon=True)
                    t.start()

            def _open_dashboard(self, _):
                import webbrowser
                webbrowser.open(f"http://localhost:{self_._web_port}")

            def _quit(self, _):
                logger.info("Quit from menubar")
                if self_._pipeline and self_._pipeline._running:
                    self_._pipeline.stop()
                if self_._on_quit:
                    self_._on_quit()
                rumps.quit_application()

        toggle_item.set_callback(lambda s: s._toggle(s))
        web_item.set_callback(lambda s: s._open_dashboard(s))
        quit_item.set_callback(lambda s: s._quit(s))

        self._app = ClairvoyantApp(
            "Clairvoyant-Optics",
            [status_item, None, toggle_item, web_item, None, quit_item],
            self.pipeline,
            self.web_port,
            self._on_quit,
        )
        self._app.run()
