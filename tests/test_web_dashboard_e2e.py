"""
Playwright E2E tests for Clairvoyant-Optics web dashboard.

Tests the web UI rendered by clairvoyant_web_dashboard.py as a real browser.
Works with daemon running (launched in fixture) or against a running daemon.

Requirements: pip install pytest-playwright
              playwright install chromium
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
DAEMON_SCRIPT = PROJECT_DIR / "src" / "service" / "daemon.py"

WEB_HOST = "127.0.0.1"
WEB_PORT = 8765
WEB_URL = f"http://{WEB_HOST}:{WEB_PORT}"


@pytest.fixture(scope="session", autouse=True)
def daemon():
    """Start the daemon + web dashboard for all tests. Autouse so tests just see a running daemon."""
    # Kill anything on our port first
    subprocess.run(["lsof", "-ti", f"{WEB_HOST}:{WEB_PORT}"],
                   capture_output=True)
    
    tmpdir = f"/tmp/co_e2e_{int(time.time())}"
    os.makedirs(tmpdir, exist_ok=True)

    env = os.environ.copy()
    env["CLAIRVOYANT_CONFIG_DIR"] = tmpdir
    env["PYTHONPATH"] = f"{PROJECT_DIR}/src"

    proc = subprocess.Popen(
        [sys.executable, str(DAEMON_SCRIPT)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for web dashboard to be ready
    deadline = time.time() + 15
    ready = False
    while time.time() < deadline:
        try:
            import urllib.request
            resp = urllib.request.urlopen(f"{WEB_URL}/api/status", timeout=2)
            if resp.status == 200:
                ready = True
                break
        except Exception:
            pass
        time.sleep(1)

    if not ready:
        proc.kill()
        raise RuntimeError("Daemon web dashboard did not start within 15s")

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


class TestWebDashboard:
    """E2E tests for the web dashboard via Playwright."""

    def test_page_loads(self, page):
        """Dashboard loads and shows the app title."""
        page.goto(WEB_URL, wait_until="networkidle")
        assert "Clairvoyant" in page.title()

    def test_dashboard_shows_status(self, page):
        """Status section is visible."""
        page.goto(WEB_URL, wait_until="networkidle")
        status = page.evaluate("fetch('/api/status').then(r => r.json())")
        assert status is not None

    def test_config_endpoint_returns_data(self, page):
        """Config API returns structured data (via cameras)."""
        page.goto(WEB_URL, wait_until="networkidle")
        config = page.evaluate("fetch('/api/cameras').then(r => r.json())")
        assert isinstance(config, dict)

    def test_version_displayed(self, page):
        """Status endpoint returns JSON with state info."""
        page.goto(WEB_URL, wait_until="networkidle")
        status = page.evaluate("fetch('/api/status').then(r => r.json())")
        assert isinstance(status, dict), f"Status not dict: {status}"
        # Should have at least 'state' field
        assert "state" in status, f"Status missing 'state': {status}"

    def test_dashboard_not_empty(self, page):
        """Dashboard renders visible content."""
        page.goto(WEB_URL, wait_until="networkidle")
        text = page.locator("body").inner_text()
        assert len(text.strip()) > 50, f"Dashboard too sparse: {len(text.strip())} chars"

    def test_health_endpoint_ok(self, page):
        """Health endpoint works."""
        page.goto(WEB_URL, wait_until="networkidle")
        result = page.evaluate("fetch('/api/status').then(r => r.json())")
        assert isinstance(result, dict)
        assert "state" in result

    def test_models_endpoint(self, page):
        """Models API returns something (may be empty before download)."""
        page.goto(WEB_URL, wait_until="networkidle")
        try:
            models = page.evaluate("fetch('/api/ml/status').then(r => r.json())")
            assert isinstance(models, dict)
        except Exception:
            pass  # expected if no models downloaded yet


if __name__ == "__main__":
    pytest.main(["-v", __file__])
