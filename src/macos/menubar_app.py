"""Clairvoyant-Optics — macOS-natiivisovellus.
Pelkkä tkinter-ikkuna + asetuspaneeli.

Asetukset tallennetaan tiedostoon ~/.clairvoyant-optics/config.yaml
ja niitä voi muokata joko sovelluksen kautta tai suoraan tiedostosta.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk
from pathlib import Path

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

VERSION = "4.0.2"
CONFIG_DIR = Path.home() / ".clairvoyant-optics"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
ENV_FILE = Path.home() / ".hermes" / ".env"

DEFAULTS = {
    "pause_on_battery": False,
    "home_ssids": "",
    "pause_when_away": False,
    "auto_update": False,
    "error_reporting": False,
    "log_level": "INFO",
}


def _load_yaml(path: Path) -> dict:
    if _HAS_YAML and path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_yaml(path: Path, data: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if _HAS_YAML:
        with open(path, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
    else:
        with open(path, "w") as f:
            for k, v in data.items():
                f.write(f"{k}: {v}\n")


def _load_env(path: Path) -> dict:
    """Lue .env-tiedosto dictiksi."""
    result = {}
    if path.exists():
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _save_env(path: Path, updates: dict):
    """Päivitä .env-tiedosto."""
    lines = []
    if path.exists():
        with open(path) as f:
            lines = f.readlines()
    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"\n{key}={value}\n")
    with open(path, "w") as f:
        f.writelines(new_lines)


def load_config() -> dict:
    """Lataa asetukset: config.yaml > .env > defaults."""
    cfg = dict(DEFAULTS)
    # 1. .env-arvot
    env = _load_env(ENV_FILE)
    for k in cfg:
        if k.upper() in env:
            val = env[k.upper()]
            if isinstance(cfg[k], bool):
                cfg[k] = val.lower() in ("true", "1", "yes", "on")
            else:
                cfg[k] = val
    # 2. config.yaml ylikirjoittaa
    yaml_data = _load_yaml(CONFIG_FILE)
    for k in cfg:
        if k in yaml_data:
            cfg[k] = yaml_data[k]
    return cfg


def save_config(cfg: dict):
    """Tallenna asetukset molempiin paikkoihin."""
    # YAML
    _save_yaml(CONFIG_FILE, cfg)
    # .env (vain tunnetut avaimet)
    env_updates = {}
    for k, v in cfg.items():
        if k in ("pause_on_battery", "pause_when_away", "auto_update", "error_reporting"):
            env_updates[k.upper()] = "true" if v else "false"
        elif k == "home_ssids":
            env_updates["HOME_SSIDS"] = v
        elif k == "log_level":
            env_updates["LOG_LEVEL"] = v
    if env_updates:
        _save_env(ENV_FILE, env_updates)


# ═══════════════════════════════════════════════════════════
# SettingsWindow
# ═══════════════════════════════════════════════════════════

class SettingsWindow:
    """Pääikkuna + asetuspaneeli (välilehdet)."""

    def __init__(self):
        self._root = tk.Tk()
        self._root.title("Clairvoyant-Optics")
        self._root.configure(bg="#1c1c1e")
        self._root.geometry("680x520")
        self._root.minsize(520, 400)

        # macOS-tyyli
        try:
            self._root.tk.call(
                "::tk::unsupported::MacWindowStyle", "style",
                self._root._w, "document",
            )
        except Exception:
            pass

        self._root.protocol("WM_DELETE_WINDOW", self._hide)

        # Valikkorivi
        self._setup_menu()

        # Lataa asetukset
        self._cfg = load_config()

        # Pääframe
        main = tk.Frame(self._root, bg="#1c1c1e")
        main.pack(fill="both", expand=True, padx=24, pady=20)

        # Otsikko
        hdr = tk.Frame(main, bg="#1c1c1e")
        hdr.pack(fill="x", pady=(0, 16))

        tk.Label(
            hdr, text="👁 Clairvoyant-Optics",
            font=("SF Pro Display", 20, "bold"),
            fg="#ffffff", bg="#1c1c1e",
        ).pack(side="left")

        tk.Label(
            hdr, text=f"v{VERSION}",
            font=("SF Pro Text", 11),
            fg="#8e8e93", bg="#1c1c1e",
        ).pack(side="right", pady=(6, 0))

        # Välilehdet
        self._notebook = ttk.Notebook(main)
        self._notebook.pack(fill="both", expand=True)

        style = ttk.Style()
        style.configure("TNotebook", background="#1c1c1e", borderwidth=0)
        style.configure("TNotebook.Tab", padding=[16, 8], font=("SF Pro Text", 12))
        style.map("TNotebook.Tab", background=[("selected", "#2c2c2e")])

        self._build_general_tab()
        self._build_power_tab()
        self._build_updates_tab()

        # Tilarivi
        status_frame = tk.Frame(main, bg="#1c1c1e")
        status_frame.pack(fill="x", pady=(12, 0))
        self._status_label = tk.Label(
            status_frame,
            text=f"Asetukset: {CONFIG_FILE}",
            font=("SF Pro Text", 10),
            fg="#636366", bg="#1c1c1e",
        )
        self._status_label.pack(side="left")

        tk.Label(
            status_frame,
            text="Muutokset tallentuvat automaattisesti",
            font=("SF Pro Text", 10),
            fg="#636366", bg="#1c1c1e",
        ).pack(side="right")

    # ── Valikkorivi ─────────────────────────────────────────

    def _setup_menu(self):
        menubar = tk.Menu(self._root)

        app_menu = tk.Menu(menubar, tearoff=0)
        app_menu.add_command(label="About Clairvoyant-Optics", command=self._about)
        app_menu.add_separator()
        app_menu.add_command(label="Quit Clairvoyant-Optics",
                             command=self._quit_app, accelerator="Cmd+Q")
        menubar.add_cascade(label="Clairvoyant-Optics", menu=app_menu)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Reload Configuration", command=self._reload_config)
        file_menu.add_command(label="Open Config File", command=self._open_config_file)
        file_menu.add_command(label="Open Env File", command=self._open_env_file)
        menubar.add_cascade(label="File", menu=file_menu)

        self._root.config(menu=menubar)

    def _about(self):
        tk.messagebox.showinfo(
            "Clairvoyant-Optics",
            f"Clairvoyant-Optics v{VERSION}\n\n"
            "macOS face recognition management\n\n"
            f"Config: {CONFIG_FILE}\n"
            f"Env:    {ENV_FILE}"
        )

    def _reload_config(self):
        self._cfg = load_config()
        self._notebook.destroy()
        self._notebook = ttk.Notebook(self._root)
        self._notebook.pack(fill="both", expand=True)
        self._build_general_tab()
        self._build_power_tab()
        self._build_updates_tab()
        self._status_label.configure(text="Asetukset ladattu uudelleen")

    def _open_config_file(self):
        os.system(f"open '{CONFIG_FILE}' 2>/dev/null || open -a TextEdit '{CONFIG_FILE}'")

    def _open_env_file(self):
        os.system(f"open '{ENV_FILE}' 2>/dev/null || open -a TextEdit '{ENV_FILE}'")

    # ── Välilehdet ──────────────────────────────────────────

    def _build_general_tab(self):
        tab = tk.Frame(self._notebook, bg="#1c1c1e")
        self._notebook.add(tab, text="  General  ")

        row = tk.Frame(tab, bg="#1c1c1e")
        row.pack(fill="x", pady=(12, 8))
        tk.Label(row, text="Log Level",
                 font=("SF Pro Text", 12, "bold"),
                 fg="#ffffff", bg="#1c1c1e").pack(side="left")

        levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        var = tk.StringVar(value=self._cfg.get("log_level", "INFO"))
        opt = tk.OptionMenu(row, var, *levels,
                            command=lambda v: self._set("log_level", v))
        opt.configure(bg="#2c2c2e", fg="#ffffff",
                      activebackground="#3c3c3e", activeforeground="#ffffff",
                      font=("SF Pro Text", 12))
        opt.pack(side="right")

        # Info
        info = tk.Frame(tab, bg="#2c2c2e", highlightbackground="#3c3c3e",
                        highlightthickness=1)
        info.pack(fill="x", pady=(16, 0), ipadx=16, ipady=16)

        tk.Label(info, text="Tietoa",
                 font=("SF Pro Text", 10, "bold"),
                 fg="#8e8e93", bg="#2c2c2e").pack(anchor="w", pady=(0, 8))

        tk.Label(info,
                 text=(
                     "Clairvoyant-Optics hallitsee kasvojentunnistus-putkea.\n"
                     "Asetuksia voi muokata joko tämän sovelluksen kautta\n"
                     "tai suoraan muokkaamalla asetustiedostoa:\n\n"
                     f"  {CONFIG_FILE}\n"
                     f"  {ENV_FILE}"
                 ),
                 font=("SF Pro Text", 11),
                 fg="#8e8e93", bg="#2c2c2e",
                 justify="left").pack(anchor="w")

    def _build_power_tab(self):
        tab = tk.Frame(self._notebook, bg="#1c1c1e")
        self._notebook.add(tab, text="  Battery & WiFi  ")

        # Pause on battery
        self._mk_toggle(tab, "Pause When on Battery",
                        "Pysäytä tunnistus kun Mac on akkuvirralla",
                        "pause_on_battery")

        # Home SSIDs
        row = tk.Frame(tab, bg="#1c1c1e")
        row.pack(fill="x", pady=(20, 4))
        tk.Label(row, text="Home WiFi SSIDs",
                 font=("SF Pro Text", 12, "bold"),
                 fg="#ffffff", bg="#1c1c1e").pack(anchor="w")
        tk.Label(row,
                 text="Pilkuilla eroteltu lista (esim. KotiWiFi, MökkiWiFi)",
                 font=("SF Pro Text", 10),
                 fg="#8e8e93", bg="#1c1c1e").pack(anchor="w", pady=(2, 0))

        entry = tk.Entry(tab, bg="#2c2c2e", fg="#ffffff",
                         insertbackground="#ffffff",
                         font=("SF Pro Text", 13),
                         relief="flat", bd=8)
        entry.insert(0, self._cfg.get("home_ssids", ""))
        entry.pack(fill="x", ipady=4)

        def _save_ssids(e=None):
            self._set("home_ssids", entry.get().strip())
        entry.bind("<FocusOut>", _save_ssids)
        entry.bind("<Return>", _save_ssids)

        # Pause when away
        self._mk_toggle(tab, "Pause When Away from Home",
                        "Pysäytä tunnistus kun ei olla kotiverkossa",
                        "pause_when_away")

    def _build_updates_tab(self):
        tab = tk.Frame(self._notebook, bg="#1c1c1e")
        self._notebook.add(tab, text="  Updates & Errors  ")

        self._mk_toggle(tab, "Auto-Update",
                        "Tarkista päivitykset automaattisesti 6 tunnin välein",
                        "auto_update")

        self._mk_toggle(tab, "Error Reporting",
                        "Lähetä virheraportit automaattisesti GitHub Issuesiin",
                        "error_reporting")

        # Infoteksti
        info = tk.Frame(tab, bg="#2c2c2e", highlightbackground="#3c3c3e",
                        highlightthickness=1)
        info.pack(fill="x", pady=(20, 0), ipadx=16, ipady=16)

        tk.Label(info,
                 text=(
                     "Auto-Update: tarkistaa uudet versiot GitHubista.\n"
                     "Ilmoitus tulee macOS-notifikaationa.\n\n"
                     "Error Reporting: lähettää virheet GitHub Issuesiin\n"
                     "automaattisesti. Ei henkilötietoja."
                 ),
                 font=("SF Pro Text", 11),
                 fg="#8e8e93", bg="#2c2c2e",
                 justify="left").pack(anchor="w")

    def _mk_toggle(self, parent, title: str, desc: str, key: str):
        """Luo toggle-rivi: otsikko + kuvaus + kytkin."""
        row = tk.Frame(parent, bg="#1c1c1e")
        row.pack(fill="x", pady=(16, 0))

        left = tk.Frame(row, bg="#1c1c1e")
        left.pack(side="left", fill="x", expand=True)

        tk.Label(left, text=title,
                 font=("SF Pro Text", 12, "bold"),
                 fg="#ffffff", bg="#1c1c1e").pack(anchor="w")
        tk.Label(left, text=desc,
                 font=("SF Pro Text", 10),
                 fg="#8e8e93", bg="#1c1c1e").pack(anchor="w", pady=(2, 0))

        var = tk.BooleanVar(value=bool(self._cfg.get(key)))
        cb = tk.Checkbutton(
            row, variable=var,
            command=lambda: self._set(key, var.get()),
            bg="#1c1c1e", fg="#ffffff",
            selectcolor="#1c1c1e",
            activebackground="#1c1c1e",
            activeforeground="#ffffff",
            font=("SF Pro Text", 13),
        )
        cb.pack(side="right", padx=(16, 0))

    def _set(self, key: str, value):
        """Aseta arvo ja tallenna."""
        self._cfg[key] = value
        save_config(self._cfg)
        self._status_label.configure(
            text=f"✓ Tallennettu: {key} = {value}"
        )

    # ── Ikkuna ──────────────────────────────────────────────

    def show(self):
        self._root.deiconify()
        self._root.lift()

    def _hide(self):
        self._root.withdraw()

    def close(self):
        try:
            self._root.destroy()
        except Exception:
            pass

    def _quit_app(self):
        self.close()


# ═══════════════════════════════════════════════════════════
# __main__
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            sys.path.insert(0, sys._MEIPASS)

    print(f"Clairvoyant-Optics v{VERSION} starting...")
    window = SettingsWindow()
    window.show()
    window._root.mainloop()
