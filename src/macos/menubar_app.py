"""macOS Menubar + natiivi ikkuna — näkyy Dockissa ja menubarissa.

Arkkitehtuuri:
- rumps: menubar-kuvake ja kontrollit
- tkinter: macOS-natiivikäyttöliittymä (Cocoa-pohjainen, tulee Pythonin mukana)
- FastAPI: REST API taustalla, data haetaan fetch-pyynnöillä
- LSUIElement ei vaadita — tkinter-ikkunat näkyvät Dockissa automaattisesti

Käyttökokemus:
- Ikkuna aukeaa heti käynnistyessä — näyttää reaaliaikaisen tilan
- Sulje-painike (×) piilottaa ikkunan, sovellus jää menubariin
- "Show Window" menubarissa palauttaa ikkunan näkyviin
- "Quit" sulkee koko sovelluksen
"""

import json
import logging
import threading
import tkinter as tk
from tkinter import ttk
import time
import urllib.request
import webbrowser

logger = logging.getLogger(__name__)

_HAS_RUMPS = False
try:
    import rumps
    _HAS_RUMPS = True
except ImportError:
    pass


# ═══════════════════════════════════════════════════════════
# Tkinter-natiivit ikkunat
# ═══════════════════════════════════════════════════════════

class StatusWindow:
    """Pääikkuna — sovelluksen reaaliaikainen tila."""

    def __init__(self, api_base: str, on_close_callback=None):
        import tkinter as tk
        from tkinter import ttk

        self._api_base = api_base
        self._on_close_callback = on_close_callback
        self._running = False

        self._root = tk.Tk()
        self._root.title("Clairvoyant-Optics")
        self._root.configure(bg="#000000")
        self._root.geometry("900x620")
        self._root.minsize(700, 480)

        # macOS-tyylinen ikkuna
        try:
            self._root.tk.call(
                "::tk::unsupported::MacWindowStyle", "style",
                self._root._w, "document",
            )
        except Exception:
            pass

        # Estä ikkunan tuhoaminen (× = piilota)
        self._root.protocol("WM_DELETE_WINDOW", self._hide)

        # Pääframe
        main = tk.Frame(self._root, bg="#000000")
        main.pack(fill="both", expand=True, padx=28, pady=24)

        # Otsikko
        title_frame = tk.Frame(main, bg="#000000")
        title_frame.pack(fill="x", pady=(0, 20))

        tk.Label(
            title_frame, text="👁 Clairvoyant-Optics",
            font=("SF Pro Display", 22, "bold"),
            fg="#ffffff", bg="#000000",
        ).pack(side="left")

        self._version_label = tk.Label(
            title_frame,
            font=("SF Pro Text", 11),
            fg="#8e8e93", bg="#000000",
        )
        self._version_label.pack(side="right", pady=(10, 0))

        # Korttigrid (2×3)
        grid = tk.Frame(main, bg="#000000")
        grid.pack(fill="both", expand=True)

        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(0, weight=1)
        grid.rowconfigure(1, weight=1)
        grid.rowconfigure(2, weight=1)

        # Status-kortti
        self._state_value = self._mk_card(grid, 0, 0, "STATUS", "—", subtitle="Loading...")

        # Power & Network -kortti
        power_card, self._power_icon, self._power_label, self._power_wifi, self._power_reason = (
            self._mk_power_card(grid, 0, 1)
        )

        # Cameras-kortti
        cam_card, self._cam_list = self._mk_scroll_card(grid, 1, 0, "CAMERAS")

        # Faces-kortti
        face_card, self._face_list = self._mk_scroll_card(grid, 1, 1, "FACES ENROLLED")

        # Telemetry-kortti
        self._telemetry_frame, self._tele_auto, self._tele_error = self._mk_card_two_lines(
            grid, 2, 0, "TELEMETRY & UPDATES",
            "Auto-Update: —", "Error Reporting: —",
        )
        tk.Label(
            self._telemetry_frame,
            text="Errors labeled 'auto-reported' are analyzed daily\nby GitHub Actions workflow → prioritized fixes.",
            font=("SF Pro Text", 9),
            fg="#636366", bg="#1c1c1e", justify="left",
        ).pack(anchor="w", pady=(12, 0))

        # Actions-kortti
        actions_card = self._mk_card_frame(grid, 2, 1, "ACTIONS")
        btn_frame = tk.Frame(actions_card, bg="#1c1c1e")
        btn_frame.pack(fill="x")

        self._mk_btn(btn_frame, "▶ Start Pipeline", self._action_toggle, bg="#30d158", fg="#000000")
        self._mk_btn(btn_frame, "📷 Import from Photos", self._action_import_photos, bg="#0071e3")
        self._mk_btn(btn_frame, "🔄 Check Updates", self._action_check_updates, bg="#0071e3")

        # Päivityssilmukka
        self._root.after(0, self._poll_loop)
        logger.info("StatusWindow created")

    # ── Card builders ───────────────────────────────────────

    def _mk_card(self, parent, row, col, title, value, subtitle=""):
        """Luo tilastokortin: otsikko + iso arvo + alaotsikko."""
        frame = self._mk_card_frame(parent, row, col, title)
        val = tk.Label(
            frame, text=value,
            font=("SF Pro Display", 32, "bold"),
            fg="#ffffff", bg="#1c1c1e",
        )
        val.pack(anchor="w")

        sub = tk.Label(
            frame, text=subtitle,
            font=("SF Pro Text", 12),
            fg="#8e8e93", bg="#1c1c1e",
        )
        sub.pack(anchor="w", pady=(4, 0))
        return val, sub

    def _mk_power_card(self, parent, row, col):
        """Luo Power & Network -kortin ikonilla ja wifi-tiedoilla."""
        frame = self._mk_card_frame(parent, row, col, "POWER & NETWORK")
        icon = tk.Label(
            frame, text="—",
            font=("SF Pro Display", 32),
            fg="#ffffff", bg="#1c1c1e",
        )
        icon.pack(anchor="w")

        label = tk.Label(
            frame, text="Checking...",
            font=("SF Pro Text", 12),
            fg="#8e8e93", bg="#1c1c1e",
        )
        label.pack(anchor="w", pady=(4, 0))

        wifi = tk.Label(
            frame, text="",
            font=("SF Pro Text", 12),
            fg="#8e8e93", bg="#1c1c1e",
        )
        wifi.pack(anchor="w", pady=(8, 0))

        reason = tk.Label(
            frame, text="",
            font=("SF Pro Text", 11, "bold"),
            fg="#ffd60a", bg="#1c1c1e",
        )
        reason.pack(anchor="w", pady=(4, 0))

        return frame, icon, label, wifi, reason

    def _mk_scroll_card(self, parent, row, col, title):
        """Luo scrollattavan listakortin."""
        import tkinter as tk

        frame = self._mk_card_frame(parent, row, col, title)

        canvas = tk.Canvas(frame, bg="#1c1c1e", highlightthickness=0, height=120)
        scrollbar = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)

        list_frame = tk.Frame(canvas, bg="#1c1c1e")
        list_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        return frame, list_frame

    def _mk_card_two_lines(self, parent, row, col, title, line1, line2):
        """Luo kortin jossa kaksi riviä tekstiä."""
        frame = self._mk_card_frame(parent, row, col, title)

        l1 = tk.Label(
            frame, text=line1,
            font=("SF Pro Text", 12, "bold"),
            fg="#8e8e93", bg="#1c1c1e",
        )
        l1.pack(anchor="w")

        l2 = tk.Label(
            frame, text=line2,
            font=("SF Pro Text", 12, "bold"),
            fg="#8e8e93", bg="#1c1c1e",
        )
        l2.pack(anchor="w", pady=(8, 0))
        return frame, l1, l2

    def _mk_card_frame(self, parent, row, col, title):
        """Luo kortin taustakehyksen."""
        import tkinter as tk

        frame = tk.Frame(parent, bg="#1c1c1e", highlightbackground="#2c2c2e",
                         highlightthickness=1)
        frame.grid(row=row, column=col, sticky="nsew", padx=6, pady=6, ipadx=16, ipady=16)

        tk.Label(
            frame, text=title,
            font=("SF Pro Text", 10, "bold"),
            fg="#8e8e93", bg="#1c1c1e",
        ).pack(anchor="w", pady=(0, 12))

        return frame

    def _mk_btn(self, parent, text, cmd, bg="#0071e3", fg="#ffffff"):
        """Luo macOS-tyylinen nappi."""
        import tkinter as tk

        btn = tk.Button(
            parent, text=text, command=cmd,
            font=("SF Pro Text", 12),
            bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
            relief="flat", bd=0, padx=14, pady=8,
            cursor="pointinghand",
        )
        btn.pack(side="left", padx=(0, 8), pady=(0, 0))

        def on_enter(e):
            btn.configure(brightness=0.9) if False else None
        def on_leave(e):
            pass

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        return btn

    # ── API-fetch ───────────────────────────────────────────

    def _fetch(self, path: str) -> dict | list:
        """Hae dataa API:lta."""
        try:
            url = f"{self._api_base}{path}"
            req = urllib.request.Request(url, headers={"User-Agent": "Clairvoyant-Optics-UI"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return {}

    # ── Polling-silmukka ────────────────────────────────────

    def _poll_loop(self):
        if not self._running:
            return

        try:
            data = self._fetch("/api/status")
            if not data:
                self._root.after(2000, self._poll_loop)
                return

            # Status
            state_val, _ = self._state_value
            state_val.configure(text=str(data.get("state", "—")).title())

            # Power & Network
            opt = data.get("optimizer")
            if opt:
                if opt.get("is_on_power"):
                    self._power_icon.configure(text="🔌")
                    self._power_label.configure(
                        text=f"AC Power"
                        + (f" · Battery {opt['battery_pct']}%" if opt.get("battery_pct") is not None else "")
                    )
                else:
                    self._power_icon.configure(text="🔋")
                    self._power_label.configure(
                        text=f"Battery {opt.get('battery_pct', '?')}%"
                    )
                ssid = opt.get("ssid") or "Unknown WiFi"
                wifi_text = f"📶 {ssid}"
                if not opt.get("is_home_wifi"):
                    wifi_text += " ⚠ Not home"
                self._power_wifi.configure(text=wifi_text)

                reason = opt.get("suspended_reason")
                self._power_reason.configure(
                    text=f"⏸ Suspended: {reason}" if reason else ""
                )
            else:
                self._power_icon.configure(text="🔌")
                self._power_label.configure(text="Optimizer disabled")
                self._power_wifi.configure(text="")
                self._power_reason.configure(text="")

            # Cameras
            cameras = data.get("cameras", [])
            for w in self._cam_list.winfo_children():
                w.destroy()
            for cam in cameras:
                row = __import__("tkinter").Frame(self._cam_list, bg="#1c1c1e")
                row.pack(fill="x", pady=3)
                __import__("tkinter").Label(
                    row, text=cam["name"], font=("SF Pro Text", 12),
                    fg="#ffffff", bg="#1c1c1e",
                ).pack(side="left")
                badge_color = "#30d158" if cam.get("active") else "#ffd60a"
                badge_text = "active" if cam.get("active") else "inactive"
                __import__("tkinter").Label(
                    row, text=badge_text, font=("SF Pro Text", 10, "bold"),
                    fg="#000000" if cam.get("active") else "#000000",
                    bg=badge_color, padx=8, pady=1,
                ).pack(side="right")

            # Faces
            faces = data.get("faces", [])
            for w in self._face_list.winfo_children():
                w.destroy()
            for f in faces:
                row = __import__("tkinter").Frame(self._face_list, bg="#1c1c1e")
                row.pack(fill="x", pady=3)
                __import__("tkinter").Label(
                    row, text=f["name"], font=("SF Pro Text", 12),
                    fg="#ffffff", bg="#1c1c1e",
                ).pack(side="left")
                __import__("tkinter").Label(
                    row, text=f"{f.get('samples', 0)} samples",
                    font=("SF Pro Text", 12), fg="#8e8e93", bg="#1c1c1e",
                ).pack(side="right")

            # Telemetry
            try:
                tele = self._fetch("/api/telemetry")
                self._tele_auto.configure(
                    text="Auto-Update: "
                    + ("✅ ON — checks every 6h" if tele.get("auto_update") else "❌ OFF")
                )
                self._tele_error.configure(
                    text="Error Reporting: "
                    + ("✅ ON" if tele.get("error_reporting") else "❌ OFF")
                )
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"Poll error: {e}")

        self._root.after(2000, self._poll_loop)

    # ── Toiminnot ───────────────────────────────────────────

    def _action_toggle(self):
        """Käynnistä/pysäytä pipeline."""
        try:
            data = self._fetch("/api/status")
            state = data.get("state", "")
            if state == "running":
                # Pysäytä — hae snapshot ennen stopia
                self._fetch("/api/status")  # keep-alive
                logger.info("Stop requested from UI")
            else:
                logger.info("Start requested from UI")
        except Exception as e:
            logger.error(f"Toggle failed: {e}")

    def _action_import_photos(self):
        """Tuo kasvokuvia Photos.app:sta."""
        try:
            url = f"{self._api_base}/api/photos/import"
            req = urllib.request.Request(
                url, method="POST",
                data=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Clairvoyant-Optics-UI",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                logger.info(f"Import result: {result}")
        except Exception as e:
            logger.error(f"Import failed: {e}")

    def _action_check_updates(self):
        """Tarkista päivitykset manuaalisesti."""
        try:
            from src.macos.updater import Updater, get_current_version
            updater = Updater(current_version=get_current_version())
            update = updater.check_for_update()
            if update:
                if _HAS_RUMPS:
                    rumps.notification(
                        "Update Available",
                        f"Clairvoyant-Optics v{update['version']}",
                        "Click to download",
                    )
                webbrowser.open(update["url"])
            else:
                if _HAS_RUMPS:
                    rumps.notification("Up to Date", f"v{get_current_version()}", "")
        except Exception as e:
            logger.error(f"Update check failed: {e}")

    # ── Ikkunan elinkaari ──────────────────────────────────

    def show(self):
        """Näytä ikkuna ja aloita pollaus."""
        self._running = True
        self._root.after(100, self._poll_loop)
        self._root.deiconify()
        self._root.lift()

    def _hide(self):
        """Piilota ikkuna (ei sulje sovellusta)."""
        self._root.withdraw()

    def close(self):
        """Sulje ikkuna pysyvästi."""
        self._running = False
        try:
            self._root.destroy()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════
# Rumps Menubar Controller
# ═══════════════════════════════════════════════════════════

class _MenubarController(rumps.App if _HAS_RUMPS else object):
    """Rumps-menubar-sovellus — pikakontrollit."""

    def __init__(self_, title, menu, pipeline, web_port, on_quit, config, window):
        super().__init__(title, menu=menu, quit_button=None)
        self_._menu_status = menu[0]
        self_._menu_toggle = menu[2]
        self_._menu_show = menu[3]
        self_._menu_auto_update = menu[7]
        self_._menu_error_rpt = menu[9]
        self_._pipeline = pipeline
        self_._web_port = web_port
        self_._on_quit = on_quit
        self_._config = config
        self_._window = window
        self_._last_update_notified: str = ""

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

    def _show_window(self_, _):
        self_._window.show()

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
        if not self_._config:
            return
        self_._config.auto_update = not self_._config.auto_update
        self_._persist_env("AUTO_UPDATE", "true" if self_._config.auto_update else "false")
        status = "✅ ON" if self_._config.auto_update else "❌ OFF"
        rumps.notification("Settings", f"Auto-Update: {status}", "")

    def _toggle_error_reporting(self_, _):
        if not self_._config:
            return
        self_._config.error_reporting = not self_._config.error_reporting
        self_._persist_env("ERROR_REPORTING", "true" if self_._config.error_reporting else "false")
        status = "✅ ON" if self_._config.error_reporting else "❌ OFF"
        rumps.notification("Settings", f"Error Reporting: {status}", "")

    def _persist_env(self_, key: str, value: str):
        import os as _os
        env_path = _os.path.expanduser("~/.hermes/.env")
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
        if self_._window:
            self_._window.close()
        if self_._on_quit:
            self_._on_quit()
        rumps.quit_application()


# ═══════════════════════════════════════════════════════════
# App — pääsovellus
# ═══════════════════════════════════════════════════════════

class App:
    """Clairvoyant-Optics — macOS-natiivisovellus (Dock + Menubar)."""

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
        self._window = None
        self._updater = None

    @property
    def menubar_available(self) -> bool:
        return _HAS_RUMPS

    def run(self):
        """Käynnistä sovellus — natiivi-ikkuna + menubar."""
        api_base = f"http://127.0.0.1:{self.web_port}"

        # 1. Luo natiivi-ikkuna (tkinter)
        self._window = StatusWindow(api_base)

        # 2. Käynnistä menubar taustalla
        if _HAS_RUMPS:
            self._start_menubar()

        # 3. Näytä ikkuna heti
        self._window.show()

        # 4. Automaattipäivitys jos opt-in
        if self.config and self.config.auto_update:
            self._start_auto_updater()

        # 5. Tkinter mainloop (blokkaava)
        try:
            self._window._root.mainloop()
        except KeyboardInterrupt:
            pass

        # Siivous
        self._do_quit()

    def _start_auto_updater(self):
        try:
            from src.macos.updater import Updater, get_current_version

            def _on_update(update_info: dict):
                try:
                    v = update_info["version"]
                    if self._menubar:
                        if getattr(self._menubar, "_last_update_notified", "") == v:
                            return
                        self._menubar._last_update_notified = v
                    if _HAS_RUMPS:
                        rumps.notification("Update Available", f"Clairvoyant-Optics v{v}", "Click to download")
                    webbrowser.open(update_info["url"])
                except Exception as e:
                    logger.error(f"Update notification failed: {e}")

            self._updater = Updater(
                current_version=get_current_version(),
                on_update_available=_on_update,
            )
            self._updater.start_background()
            logger.info("Auto-update background checker started")
        except Exception as e:
            logger.error(f"Failed to start auto-updater: {e}")

    def _start_menubar(self):
        status_item = rumps.MenuItem("Status: Idle")
        toggle_item = rumps.MenuItem("▶ Start")
        show_item = rumps.MenuItem("Show Window")
        web_item = rumps.MenuItem(f"Open Dashboard (:{self.web_port})")
        update_item = rumps.MenuItem("Check for Updates...")
        quit_item = rumps.MenuItem("Quit")
        auto_update_item = rumps.MenuItem("Auto-Update: ❌ OFF")
        error_rpt_item = rumps.MenuItem("Error Reporting: ❌ OFF")

        menu = [
            status_item, None,          # 0: status, 1: ---
            toggle_item,                # 2: toggle
            show_item,                  # 3: show window
            web_item,                   # 4: open browser
            update_item,                # 5: check updates
            None,                       # 6: ---
            auto_update_item,           # 7: auto-update toggle
            None,                       # 8: ---
            error_rpt_item,             # 9: error reporting toggle
            None,                       # 10: ---
            quit_item,                  # 11: quit
        ]

        self._menubar = _MenubarController(
            "Clairvoyant-Optics",
            menu,
            self.pipeline,
            self.web_port,
            self._on_quit,
            self.config,
            self._window,
        )

        toggle_item.set_callback(lambda s: s._toggle(s))
        show_item.set_callback(lambda s: s._show_window(s))
        web_item.set_callback(lambda s: s._open_dashboard(s))
        update_item.set_callback(lambda s: s._check_updates(s))
        auto_update_item.set_callback(lambda s: s._toggle_auto_update(s))
        error_rpt_item.set_callback(lambda s: s._toggle_error_reporting(s))
        quit_item.set_callback(lambda s: s._quit(s))

        t = threading.Thread(target=self._menubar.run, daemon=True)
        t.start()

    def _do_quit(self):
        if self._updater:
            self._updater.stop_background()
        if self.pipeline and self.pipeline._running:
            self.pipeline.stop()
        if self._window:
            self._window.close()
        if self._on_quit:
            self._on_quit()
