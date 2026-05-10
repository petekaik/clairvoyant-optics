"""Automaattinen virheraportointi GitHub Issuesiin — opt-in.

Kaappaa käsittelemättömät poikkeukset ja luo GitHub Issueen
stack tracen, ympäristötiedot ja redacted konfiguraation.

Opt-in: ERROR_REPORTING=true .env-tiedostossa. Oletuksena pois päältä.

Käynnistys:
    from src.macos.error_reporter import install_error_reporter
    install_error_reporter("petekaik/clairvoyant-optics")

Versiokehitysautomaatio:
    GitHub Actions -workflow "Error Issue Analyzer" (`.github/workflows/error-analyzer.yml`)
    analysoi `auto-reported` + `bug` -labeleilla merkityt issuet kerran päivässä.
    Se ryhmittelee virheet tyypin mukaan, tunnistaa toistuvat patternit, ja generoi
    yhteenvedon → luo prio-gh-issuen kehittäjälle. Tämä mahdollistaa jatkuvan
    parantamisen ilman että käyttäjän tarvitsee manuaalisesti raportoida.
"""

import json
import logging
import os
import platform
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Redaktoitavat avainsanat ympäristömuuttujissa
_REDACT_KEYS = {"TOKEN", "KEY", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL"}


class ErrorReporter:
    """Hallinnoi virheraportointia GitHub Issues -APIn kautta."""

    def __init__(
        self,
        repo: str = "petekaik/clairvoyant-optics",
        token: Optional[str] = None,
    ):
        self._repo = repo
        self._token = token or os.getenv("GITHUB_TOKEN") or ""
        self._base_url = f"https://api.github.com/repos/{repo}"
        self._reported_errors: set[str] = set()

    @property
    def enabled(self) -> bool:
        """Onko raportointi sallittu: token + opt-in."""
        if not self._token:
            return False
        # Opt-in guard: ERROR_REPORTING pitää olla eksplisiittisesti true
        val = os.getenv("ERROR_REPORTING", "").strip().lower()
        if val not in ("1", "true", "yes", "on"):
            return False
        return True

    def _redact_value(self, key: str, value: str) -> str:
        key_upper = key.upper()
        for rk in _REDACT_KEYS:
            if rk in key_upper:
                if value and len(value) > 6:
                    return f"{value[:3]}...{value[-3:]}" if len(value) > 10 else "***"
                return "***"
        return value

    def _get_env_safe(self) -> str:
        lines = []
        for key in sorted(os.environ.keys()):
            value = os.environ[key]
            redacted = self._redact_value(key, value)
            lines.append(f"  {key}={redacted}")
        return "\n".join(lines)

    def _get_system_info(self) -> str:
        info = {
            "platform": platform.platform(),
            "python": sys.version,
            "machine": platform.machine(),
            "processor": platform.processor(),
            "release": platform.release(),
            "version": platform.version(),
            "utc_time": datetime.now(timezone.utc).isoformat(),
        }
        return "\n".join(f"  {k}: {v}" for k, v in info.items())

    def _error_hash(self, exc_type: type, exc_value: BaseException, traceback_str: str) -> str:
        import hashlib
        content = f"{exc_type.__name__}:{exc_value}:{traceback_str.split(chr(10))[-3:]}"
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def _search_existing_issue(self, title_prefix: str) -> Optional[int]:
        if not self._token:
            return None
        try:
            import urllib.request

            url = f"{self._base_url}/issues?state=open&labels=bug,auto-reported&per_page=20"
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"token {self._token}",
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "Clairvoyant-Optics-ErrorReporter",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                issues = json.loads(resp.read().decode())
                for issue in issues:
                    if issue.get("title", "").startswith(title_prefix):
                        logger.info(
                            f"Existing issue found: #{issue['number']} — {issue['title']}"
                        )
                        return issue["number"]
        except Exception as e:
            logger.warning(f"Could not search existing issues: {e}")
        return None

    def report_error(
        self,
        exc_type: type,
        exc_value: BaseException,
        exc_tb: object,
        context: str = "",
    ) -> Optional[str]:
        """Raportoi poikkeus GitHub Issueen — vain jos opt-in on päällä.

        Palauttaa issue-URL:n tai None.
        """
        if not self.enabled:
            logger.debug("Error reporting disabled (opt-in required: ERROR_REPORTING=true)")
            return None

        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        error_type = (
            f"{exc_type.__module__}.{exc_type.__qualname__}"
            if hasattr(exc_type, "__qualname__")
            else exc_type.__name__
        )

        error_hash = self._error_hash(exc_type, exc_value, tb_str)
        if error_hash in self._reported_errors:
            logger.info(f"Duplicate error suppressed: {error_hash}")
            return None
        self._reported_errors.add(error_hash)

        title = f"[auto] {error_type}: {str(exc_value)[:100]}"
        body = f"""## Unhandled Exception

**Type:** `{error_type}`
**Message:** {exc_value}
**Time (UTC):** {datetime.now(timezone.utc).isoformat()}

### Stack Trace
```
{tb_str.strip()}
```

### System Info
```
{self._get_system_info()}
```

### Context
{context or "None provided"}

### Environment (redacted)
```
{self._get_env_safe()}
```
"""
        existing = self._search_existing_issue(title)
        if existing is not None:
            return f"https://github.com/{self._repo}/issues/{existing}"

        try:
            import urllib.request

            url = f"{self._base_url}/issues"
            data = json.dumps({
                "title": title,
                "body": body[:65536],
                "labels": ["bug", "auto-reported"],
            }).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Authorization": f"token {self._token}",
                    "Accept": "application/vnd.github.v3+json",
                    "Content-Type": "application/json",
                    "User-Agent": "Clairvoyant-Optics-ErrorReporter",
                },
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                issue = json.loads(resp.read().decode())
                issue_url = issue["html_url"]
                logger.info(f"Error reported: {issue_url}")
                return issue_url

        except Exception as e:
            logger.error(f"Failed to create GitHub Issue: {e}")
            return None


# Globaali instanssi
_error_reporter: Optional[ErrorReporter] = None


def install_error_reporter(repo: str = "petekaik/clairvoyant-optics") -> bool:
    """Asenna globaali virheraportoija excepthookiin.

    Palauttaa True jos raportointi on päällä, False jos ei.
    """
    global _error_reporter
    _error_reporter = ErrorReporter(repo=repo)

    if not _error_reporter.enabled:
        logger.info(
            "Error reporter installed but DISABLED — "
            "set ERROR_REPORTING=true in ~/.hermes/.env to enable"
        )
        return False

    def _excepthook(exc_type, exc_value, exc_tb):
        if _error_reporter:
            _error_reporter.report_error(exc_type, exc_value, exc_tb)
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook
    logger.info(f"Error reporter ENABLED for {repo}")
    return True


def report_managed_error(
    exc: BaseException,
    context: str = "",
    repo: str = "petekaik/clairvoyant-optics",
) -> Optional[str]:
    """Raportoi hallittu poikkeus manuaalisesti (try/except-blokista)."""
    reporter = ErrorReporter(repo=repo)
    if not reporter.enabled:
        return None
    tb = exc.__traceback__
    return reporter.report_error(type(exc), exc, tb, context=context)
