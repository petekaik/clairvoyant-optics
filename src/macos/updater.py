"""Automaattinen sovelluspäivitys GitHub Releasesin kautta.

Tarkistaa GitHub Releases API:sta uusimman version, vertaa asennettuun,
ja tarvittaessa lataa + asentaa uuden version. Opt-in: AUTO_UPDATE=true.

Arkkitehtuuri:
- Manuaalinen: "Check for Updates..." menubarissa → ilmoittaa jos uutta on
- Automaattinen: taustasäie tarkistaa 6h välein, ilmoittaa notificationilla
- Asennus: käynnistää ulkoisen skriptin joka korvaa .app:n (ei voi korvata
  itseään ajon aikana), tai käyttäjälle pelkkä notifikaatio + latauslinkki
"""

import json
import logging
import os
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class Updater:
    """Sovelluksen automaattipäivitys GitHub Releases -lähteestä."""

    def __init__(
        self,
        owner: str = "petekaik",
        repo: str = "clairvoyant-optics",
        current_version: str = "0.0.0",
        channel: str = "stable",
        on_update_available: Optional[Callable] = None,
    ):
        self.owner = owner
        self.repo = repo
        self.current_version = current_version
        self.channel = channel
        self._api_base = f"https://api.github.com/repos/{owner}/{repo}"
        self._on_update_available = on_update_available
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def check_for_update(self) -> Optional[dict]:
        """Tarkista onko uudempaa versiota saatavilla.

        Returns:
            {version, url, body, published_at} tai None jos ajantasalla.
        """
        try:
            latest = self._get_latest_release()
            if latest is None:
                return None

            latest_version = latest["tag_name"].lstrip("v")
            if self._is_newer(latest_version, self.current_version):
                logger.info(f"Update available: {self.current_version} → {latest_version}")
                return {
                    "version": latest_version,
                    "url": latest["html_url"],
                    "body": latest.get("body", ""),
                    "published_at": latest.get("published_at", ""),
                    "assets": [
                        {"name": a["name"], "url": a["browser_download_url"], "size": a["size"]}
                        for a in latest.get("assets", [])
                    ],
                }

            logger.debug(f"Up to date: {self.current_version}")
            return None

        except Exception as e:
            logger.error(f"Update check failed: {e}")
            return None

    def download_update(self, asset_url: str) -> Optional[Path]:
        """Lataa päivityspaketti."""
        try:
            tmppath = Path(tempfile.gettempdir()) / "clairvoyant-update.dmg"
            logger.info(f"Downloading update from {asset_url}...")
            urllib.request.urlretrieve(asset_url, str(tmppath))
            logger.info(f"Downloaded: {tmppath.stat().st_size / 1e6:.1f} MB")
            return tmppath
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None

    def install_update(self, dmg_path: Path) -> bool:
        """Asenna päivitys korvaamalla .app Applicationsissa.

        HUOM: Ei voi korvata itseään ajon aikana. Tämä metodi olettaa
        että sovellus ajetaan ulkoisesta skriptistä.
        """
        import subprocess

        try:
            result = subprocess.run(
                ["hdiutil", "attach", str(dmg_path), "-nobrowse", "-readonly"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                logger.error(f"Mount failed: {result.stderr}")
                return False

            mount_line = [l for l in result.stdout.split("\n") if "/Volumes/" in l]
            if not mount_line:
                logger.error("Could not find mount point")
                return False

            mount_point = mount_line[-1].split()[-1]
            logger.info(f"Mounted at: {mount_point}")

            app_path = list(Path(mount_point).glob("*.app"))
            if not app_path:
                logger.error("No .app found in DMG")
                subprocess.run(["hdiutil", "detach", mount_point], capture_output=True)
                return False

            dest = Path("/Applications") / app_path[0].name
            if dest.exists():
                subprocess.run(["rm", "-rf", str(dest)], check=True)

            subprocess.run(
                ["cp", "-R", str(app_path[0]), str(dest)],
                check=True, timeout=60,
            )
            logger.info(f"Installed to: {dest}")
            subprocess.run(["hdiutil", "detach", mount_point], capture_output=True)
            return True

        except Exception as e:
            logger.error(f"Install failed: {e}")
            return False

    # ── Taustapäivityksen elinkaari ─────────────────────────────

    def start_background(self, interval_hours: float = 6.0):
        """Käynnistä automaattinen taustatarkistus.

        Args:
            interval_hours: Kuinka usein tarkistetaan (oletus 6h).
        """
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._background_loop,
            args=(interval_hours,),
            daemon=True,
        )
        self._thread.start()
        logger.info(f"Auto-update background checker started (every {interval_hours}h)")

    def stop_background(self):
        """Pysäytä taustatarkistus."""
        self._running = False
        logger.info("Auto-update background checker stopped")

    def _background_loop(self, interval_hours: float):
        """Taustasilmukka: nuku → tarkista → toista."""
        # Ensimmäinen tarkistus 2 min kuluttua (antaa sovelluksen käynnistyä)
        time.sleep(120)

        while self._running:
            try:
                update = self.check_for_update()
                if update and self._on_update_available:
                    self._on_update_available(update)
            except Exception as e:
                logger.error(f"Background update check error: {e}")

            # Nuku interval_hours, mutta herää 60s välein
            # jotta _running-tarkistus reagoi nopeasti
            for _ in range(int(interval_hours * 60)):
                if not self._running:
                    return
                time.sleep(60)

    # ── Apumetodit ──────────────────────────────────────────────

    def _get_latest_release(self) -> Optional[dict]:
        """Hae uusin release GitHub API:sta."""
        url = f"{self._api_base}/releases/latest"
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Clairvoyant-Optics-Updater/1.0",
        })

        # Lisää token jos saatavilla (nostaa rate-limitin 60 → 5000/h)
        token = os.getenv("GITHUB_TOKEN", "")
        if token:
            req.add_header("Authorization", f"token {token}")

        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    @staticmethod
    def _is_newer(latest: str, current: str) -> bool:
        """Vertaa semver-versioita: onko latest > current."""
        try:
            def parse(v):
                parts = v.split(".")
                return [int(p) if p.isdigit() else 0 for p in parts[:3]]
            return parse(latest) > parse(current)
        except Exception:
            return latest != current


def get_current_version() -> str:
    """Lue asennettu versio."""
    try:
        from src.version import VERSION
        return VERSION
    except ImportError:
        return "0.0.0"
