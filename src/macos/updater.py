"""Automaattinen sovelluspäivitys GitHub Releasesin kautta.

Tarkistaa GitHub Releases API:sta uusimman version, vertaa asennettuun,
ja tarvittaessa lataa + asentaa uuden version.
"""

import json
import logging
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class Updater:
    """Sovelluksen automaattipäivitys GitHub Releases -lähteestä."""

    def __init__(
        self,
        owner: str = "petekaik",
        repo: str = "clairvoyant-optics",
        current_version: str = "0.0.0",
        channel: str = "stable",
    ):
        self.owner = owner
        self.repo = repo
        self.current_version = current_version
        self.channel = channel
        self._api_base = f"https://api.github.com/repos/{owner}/{repo}"

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
        """Lataa päivityspaketti.

        Args:
            asset_url: GitHub release assetin lataus-URL

        Returns:
            Polku ladattuun tiedostoon tai None.
        """
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
        """Asenna päivitys.

        Avaa .dmg:n ja korvaa sovelluksen Applications-kansiossa.

        Args:
            dmg_path: Polku ladattuun .dmg-tiedostoon

        Returns:
            True jos onnistui.
        """
        import subprocess

        try:
            # Mount DMG
            result = subprocess.run(
                ["hdiutil", "attach", str(dmg_path), "-nobrowse", "-readonly"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                logger.error(f"Mount failed: {result.stderr}")
                return False

            # Parse mount point from output
            # /dev/disk4  Apple_HFS  /Volumes/Clairvoyant-Optics
            mount_line = [l for l in result.stdout.split("\n") if "/Volumes/" in l]
            if not mount_line:
                logger.error("Could not find mount point")
                return False

            mount_point = mount_line[-1].split()[-1]
            logger.info(f"Mounted at: {mount_point}")

            # Find .app in mounted volume
            app_path = list(Path(mount_point).glob("*.app"))
            if not app_path:
                logger.error("No .app found in DMG")
                subprocess.run(["hdiutil", "detach", mount_point], capture_output=True)
                return False

            # Copy to Applications
            dest = Path("/Applications") / app_path[0].name
            if dest.exists():
                logger.info(f"Removing old version: {dest}")
                subprocess.run(["rm", "-rf", str(dest)], check=True)

            subprocess.run(
                ["cp", "-R", str(app_path[0]), str(dest)],
                check=True, timeout=60,
            )
            logger.info(f"Installed to: {dest}")

            # Unmount
            subprocess.run(["hdiutil", "detach", mount_point], capture_output=True)

            return True

        except Exception as e:
            logger.error(f"Install failed: {e}")
            return False

    def _get_latest_release(self) -> Optional[dict]:
        """Hae uusin release GitHub API:sta."""
        url = f"{self._api_base}/releases/latest"
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Clairvoyant-Optics-Updater/1.0",
        })

        with urllib.request.urlopen(req, timeout=10) as resp:
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
            # Fallback: string compare
            return latest != current


def get_current_version() -> str:
    """Lue asennettu versio."""
    try:
        from src.version import VERSION
        return VERSION
    except ImportError:
        return "0.0.0"
