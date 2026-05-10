"""macOS Natiivisovellus — Dock-ikkuna + valikkorivi.

Arkkitehtuuri:
- tkinter: macOS-natiivikäyttöliittymä (Cocoa-pohjainen, tulee Pythonin mukana)
- tkinter.Menu: natiivi valikkorivi (ei rumps-riippuvuutta)
- FastAPI: REST API taustalla, UI pollaa sitä
- Kaikki ajetaan tkinterin mainloopissa pääsäikeessä — ei säieristiriitoja

Käyttökokemus:
- Ikkuna aukeaa heti käynnistyessä — näyttää reaaliaikaisen tilan
- Sulje-painike (×) piilottaa ikkunan, sovellus jää Dockiin
- Valikkoriviltä: kontrollit, päivitykset, asetukset
- Cmd+Q tai Quit-valikosta sulkee koko sovelluksen
"""

import json
import logging
import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk
import time
import urllib.request
import webbrowser
from pathlib import Path

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Apufunktiot
# ═══════════════════════════════════════════════════════════

def _notify(title: str, subtitle: str = "", message: str = ""):
    """Lähetä macOS-ilmoitus (ei riippuvuuksia)."""
    try:
        script = (
            f'display notification "{message}"'
            f' with title "{title}"'
            f' subtitle "{subtitle}"'
        )
        subprocess.run(["osascript", "-e", script], timeout=3, capture_output=True)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
# Tkinter-natiivit ikkunat
# ═══════════════════════════════════════════════════════════

class StatusWindow:
    """Pääikkuna — sovelluksen reaaliaikainen tila."""

    def __init__(self, api_base: str, toggle_callback=None):
        self._api_base = api_base
        self._toggle_callback = toggle_callback
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
        _, self._power_icon, self._power_label, self._power_wifi, self._power_reason = (
            self._mk_power_card(grid, 0, 1)
        )

        # Cameras-kortti
        _, self._cam_list = self._mk_scroll_card(grid, 1, 0, "CAMERAS")

        # Faces-kortti
        _, self._face_list = self._mk_scroll_card(grid, 1, 1, "FACES ENROLLED")

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
        btn = tk.Button(
            parent, text=text, command=cmd,
            font=("SF Pro Text", 12),
            bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
            relief="flat", bd=0, padx=14, pady=8,
            cursor="pointinghand",
        )
        btn.pack(side="left", padx=(0, 8), pady=(0, 0))
        return btn

    # ── API-fetch ───────────────────────────────────────────

    def _fetch(self, path: str) -> dict | list:
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
                row = tk.Frame(self._cam_list, bg="#1c1c1e")
                row.pack(fill="x", pady=3)
                tk.Label(
                    row, text=cam["name"], font=("SF Pro Text", 12),
                    fg="#ffffff", bg="#1c1c1e",
                ).pack(side="left")
                badge_color = "#30d158" if cam.get("active") else "#ffd60a"
                badge_text = "active" if cam.get("active") else "inactive"
                tk.Label(
                    row, text=badge_text, font=("SF Pro Text", 10, "bold"),
                    fg="#000000",
                    bg=badge_color, padx=8, pady=1,
                ).pack(side="right")

            # Faces
            faces = data.get("faces", [])
            for w in self._face_list.winfo_children():
                w.destroy()
            for f in faces:
                row = tk.Frame(self._face_list, bg="#1c1c1e")
                row.pack(fill="x", pady=3)
                tk.Label(
                    row, text=f["name"], font=("SF Pro Text", 12),
                    fg="#ffffff", bg="#1c1c1e",
                ).pack(side="left")
                tk.Label(
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
        """Käynnistä/pysäytä pipeline — delegoi App:lle."""
        if self._toggle_callback:
            self._toggle_callback()

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
                _notify("Import Complete", f"Imported photos", str(result.get("imported", 0)))
        except Exception as e:
            logger.error(f"Import failed: {e}")
            _notify("Import Failed", str(e), "")

    def _action_check_updates(self):
        """Tarkista päivitykset manuaalisesti."""
        try:
            from src.macos.updater import Updater, get_current_version
            updater = Updater(current_version=get_current_version())
            update = updater.check_for_update()
            if update:
                _notify(
                    "Update Available",
                    f"Clairvoyant-Optics v{update['version']}",
                    "Click to download",
                )
                webbrowser.open(update["url"])
            else:
                _notify("Up to Date", f"v{get_current_version()}", "")
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
# App — pääsovellus
# ═══════════════════════════════════════════════════════════

class App:
    """Clairvoyant-Optics — macOS-natiivisovellus (Dock + valikkorivi)."""

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
        self._window = None
        self._updater = None
        # Valikkorivin toggle-labelit (päivitetään tilan mukaan)
        self._menu_auto_update_idx = None
        self._menu_error_rpt_idx = None
        self._auto_update_menu = None

    def run(self):
        """Käynnistä sovellus — natiivi-ikkuna + valikkorivi."""
        api_base = f"http://127.0.0.1:{self.web_port}"

        # 1. Luo natiivi-ikkuna (tkinter)
        self._window = StatusWindow(api_base, toggle_callback=self._toggle_pipeline)

        # 2. Rakenna natiivi valikkorivi
        self._setup_menu()

        # 3. Näytä ikkuna
        self._window.show()

        # 4. Automaattipäivitys (opt-in)
        if self.config and self.config.auto_update:
            self._start_auto_updater()

        # 5. Tkinter mainloop (blokkaava)
        try:
            self._window._root.mainloop()
        except KeyboardInterrupt:
            pass

        # Siivous
        self._do_quit()

    def _setup_menu(self):
        """Luo macOS-natiivi valikkorivi tkinter.Menu:lla."""
        root = self._window._root
        menubar = tk.Menu(root)

        # ── Sovellusvalikko (näkyy sovelluksen nimellä macOS:ssa) ──
        app_menu = tk.Menu(menubar, tearoff=0)
        app_menu.add_command(label="About Clairvoyant-Optics", command=self._about)
        app_menu.add_separator()
        app_menu.add_command(label=f"Quit Clairvoyant-Optics", command=self._quit_app,
                             accelerator="Cmd+Q")
        # macOS: eka cascade jossa label = app-nimi → Apple-menu
        menubar.add_cascade(label="Clairvoyant-Optics", menu=app_menu)

        # ── Kontrollit ──
        ctrl_menu = tk.Menu(menubar, tearoff=0)
        ctrl_menu.add_command(label="Start/Pause Pipeline", command=self._toggle_pipeline)
        ctrl_menu.add_separator()
        ctrl_menu.add_command(label="Show Window", command=self._window.show)
        ctrl_menu.add_command(label="Open in Browser",
                              command=lambda: webbrowser.open(f"http://localhost:{self.web_port}"))
        menubar.add_cascade(label="Controls", menu=ctrl_menu)

        # ── Päivitykset ──
        self._auto_update_menu = tk.Menu(menubar, tearoff=0)
        self._auto_update_menu.add_command(label="Check for Updates...", command=self._check_updates)
        self._auto_update_menu.add_separator()

        au_label = "Auto-Update: " + ("✅ ON" if self.config and self.config.auto_update else "❌ OFF")
        er_label = "Error Reporting: " + ("✅ ON" if self.config and self.config.error_reporting else "❌ OFF")

        self._auto_update_menu.add_command(label=au_label, command=self._toggle_auto_update)
        self._auto_update_menu.add_command(label=er_label, command=self._toggle_error_reporting)

        # Tallennetaan indeksit label-päivityksiä varten
        self._menu_auto_update_idx = 2  # 0=Check, 1=---, 2=auto-update toggle
        self._menu_error_rpt_idx = 3

        menubar.add_cascade(label="Updates", menu=self._auto_update_menu)

        root.config(menu=menubar)

    def _about(self):
        """Näytä About-info."""
        try:
            from src.version import VERSION
            ver = VERSION
        except Exception:
            ver = "?"
        _notify("Clairvoyant-Optics", f"v{ver}", "macOS face recognition pipeline")

    # ── Pipeline ────────────────────────────────────────────

    def _toggle_pipeline(self):
        """Käynnistä/pysäytä pipeline."""
        if self.pipeline is None:
            return
        if self.pipeline._running:
            logger.info("Stopping pipeline from menu")
            self.pipeline.stop()
            _notify("Pipeline", "Stopped", "")
        else:
            logger.info("Starting pipeline from menu")
            if hasattr(self.pipeline, 'optimizer') and self.pipeline.optimizer:
                self.pipeline.optimizer._manual_override = True
            t = threading.Thread(target=self.pipeline.start, daemon=True)
            t.start()
            _notify("Pipeline", "Starting...", "")

    # ── Päivitykset ─────────────────────────────────────────

    def _check_updates(self):
        """Tarkista päivitykset (valikkoriviltä)."""
        try:
            from src.macos.updater import Updater, get_current_version
            updater = Updater(current_version=get_current_version())
            update = updater.check_for_update()
            if update:
                _notify(
                    "Update Available",
                    f"Clairvoyant-Optics v{update['version']}",
                    "Click to download",
                )
                webbrowser.open(update["url"])
            else:
                _notify("Up to Date", f"v{get_current_version()}", "")
        except Exception as e:
            logger.error(f"Update check failed: {e}")

    def _toggle_auto_update(self):
        """Vaihda auto-update päälle/pois."""
        if not self.config:
            return
        self.config.auto_update = not self.config.auto_update
        self._persist_env("AUTO_UPDATE", "true" if self.config.auto_update else "false")
        new_label = "Auto-Update: " + ("✅ ON" if self.config.auto_update else "❌ OFF")
        self._auto_update_menu.entryconfigure(self._menu_auto_update_idx, label=new_label)
        if self.config.auto_update:
            self._start_auto_updater()
        elif self._updater:
            self._updater.stop_background()
            self._updater = None
        _notify("Settings", new_label, "")

    def _toggle_error_reporting(self):
        """Vaihda error reporting päälle/pois."""
        if not self.config:
            return
        self.config.error_reporting = not self.config.error_reporting
        self._persist_env("ERROR_REPORTING", "true" if self.config.error_reporting else "false")
        new_label = "Error Reporting: " + ("✅ ON" if self.config.error_reporting else "❌ OFF")
        self._auto_update_menu.entryconfigure(self._menu_error_rpt_idx, label=new_label)
        _notify("Settings", new_label, "")

    def _persist_env(self, key: str, value: str):
        """Tallenna asetus ~/.hermes/.env-tiedostoon."""
        env_path = os.path.expanduser("~/.hermes/.env")
        os.environ[key] = value
        try:
            if os.path.exists(env_path):
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

    def _start_auto_updater(self):
        """Käynnistä automaattinen päivitystentarkistus taustalla."""
        try:
            from src.macos.updater import Updater, get_current_version

            def _on_update(update_info: dict):
                try:
                    v = update_info["version"]
                    _notify(
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
            logger.info("Auto-update background checker started")
        except Exception as e:
            logger.error(f"Failed to start auto-updater: {e}")

    def _quit_app(self):
        """Sulje koko sovellus (valikkoriviltä)."""
        self._do_quit()
        try:
            self._window._root.destroy()
        except Exception:
            pass

    def _do_quit(self):
        """Siivoa resurssit."""
        if self._updater:
            self._updater.stop_background()
        if self.pipeline and self.pipeline._running:
            self.pipeline.stop()
        if self._window:
            self._window.close()
        if self._on_quit:
            self._on_quit()


# ═══════════════════════════════════════════════════════════
# __main__ — PyInstaller entry point (suora ajo bundlesta)
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    # Hanki projektin juuri
    if getattr(sys, "frozen", False):
        project_root = Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else Path(sys.executable).parent.parent / "Resources"
    else:
        project_root = Path(__file__).resolve().parent.parent

    # Varmista että src/ on import-polussa
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Versio
    from src.version import VERSION

    # Lataa config
    env_path = Path(os.path.expanduser("~/.hermes/.env"))
    from src.config import load_config
    config = load_config(env_path if env_path.exists() else None)

    # Logitus
    from src.utils import setup_logging
    setup_logging(config.log_level)

    logger.info(f"Clairvoyant-Optics v{VERSION} starting")
    logger.info(f"Project root: {project_root}")

    # Pipeline
    from src.main import DetectionPipeline
    pipeline = DetectionPipeline(config)

    # Web server (FastAPI) taustasäikeeseen
    import uvicorn
    from src.macos.web_server import WebServer

    ws = WebServer(pipeline=pipeline, config=config)
    if ws.available:
        app_fastapi = ws.create_app()
        web_thread = threading.Thread(
            target=uvicorn.run,
            args=(app_fastapi,),
            kwargs={"host": ws.host, "port": ws.port, "log_level": "warning"},
            daemon=True,
        )
        web_thread.start()
        time.sleep(1.5)  # Anna serverin käynnistyä
        logger.info(f"Web server: {ws.url}")
    else:
        logger.error("FastAPI/uvicorn not available — web API disabled")
        ws = None

    # Virheraportoija (opt-in)
    try:
        from src.macos.error_reporter import install_error_reporter
        install_error_reporter()
    except Exception:
        pass

    # macOS-natiivisovellus
    app = App(pipeline=pipeline, config=config, web_port=8765)

    # Käynnistä pipeline taustasäikeeseen
    def _start_pipeline():
        try:
            pipeline.start()
        except Exception as e:
            logger.error(f"Pipeline start failed: {e}")

    pipeline_thread = threading.Thread(target=_start_pipeline, daemon=True)
    pipeline_thread.start()

    # Käynnistä UI (blokkaava)
    logger.info("Starting tkinter mainloop...")
    app.run()
