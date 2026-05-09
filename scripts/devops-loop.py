#!/usr/bin/env python3
"""Auto-DevOps-silmukka — monitoroi, versionoi, testaa ja päivittää sovellusta.

Tätä ajetaan Hermes cron -jobina säännöllisesti.
"""
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("devops")


def main():
    """Pääsilmukka — tarkista repo, CI-status ja mahdolliset päivitystarpeet."""
    import os
    import subprocess
    from datetime import datetime, timezone

    PROJECT_DIR = Path(__file__).resolve().parent.parent

    logger.info(f"DevOps loop starting — project: {PROJECT_DIR}")

    # 1. Varmista työhakemisto
    if not (PROJECT_DIR / ".git").exists():
        logger.error(f"Not a git repository: {PROJECT_DIR}")
        return 1

    os.chdir(PROJECT_DIR)

    # 2. Git fetch (hiljaa)
    try:
        subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True,
            timeout=30,
            check=True,
        )
        logger.info("Git fetch completed")
    except Exception as e:
        logger.warning(f"Git fetch failed (network?): {e}")

    # 3. Onko paikallisia committeja joita ei ole pushattu?
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD", "^origin/master"],
            capture_output=True, text=True, timeout=10,
        )
        unpushed = int(result.stdout.strip() or "0")
        if unpushed > 0:
            logger.warning(f"Found {unpushed} unpushed commits — pushing...")
            subprocess.run(
                ["git", "push", "origin", "master"],
                capture_output=True, timeout=60,
                check=True,
            )
            logger.info("Pushed successfully")
    except Exception as e:
        logger.error(f"Push handling failed: {e}")

    # 4. Hae nykyinen versio
    sys.path.insert(0, str(PROJECT_DIR))
    from src.version import VERSION
    logger.info(f"Current version: {VERSION}")

    # 5. Tarkista CI-status GitHubista (jos token löytyy)
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        # Yritä lukea .hermes/.env
        env_file = Path.home() / ".hermes" / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("GITHUB_TOKEN="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val and not val.startswith("#"):
                        token = val
                        break

    if token:
        try:
            import json, urllib.request
            url = (
                "https://api.github.com/repos/petekaik/clairvoyant-optics"
                "/commits/master/status"
            )
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "Clairvoyant-Optics-DevOps",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                ci_state = data.get("state", "unknown")
                logger.info(f"CI status: {ci_state}")

                if ci_state in ("failure", "error"):
                    logger.warning(f"CI state is {ci_state}!")
                    # Tarkista avoimet issue-labelit
                    issues_url = (
                        "https://api.github.com/repos/petekaik/clairvoyant-optics"
                        "/issues?state=open&labels=ci-failure,build-fix&per_page=5"
                    )
                    req2 = urllib.request.Request(
                        issues_url,
                        headers={
                            "Authorization": f"token {token}",
                            "Accept": "application/vnd.github.v3+json",
                            "User-Agent": "Clairvoyant-Optics-DevOps",
                        },
                    )
                    with urllib.request.urlopen(req2, timeout=10) as resp2:
                        issues = json.loads(resp2.read().decode())
                        open_count = len(issues)
                        if open_count == 0:
                            logger.warning(
                                "No open ci-failure issues — "
                                "consider creating one or triggering fix"
                            )
        except Exception as e:
            logger.error(f"CI status check failed: {e}")
    else:
        logger.info("No GITHUB_TOKEN — skipping CI status check")

    logger.info("DevOps loop completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
