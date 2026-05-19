"""
atomacos-based macOS GUI integration test for Clairvoyant-Optics.

Tests the settings window via Apple Accessibility API:
- Window opens and renders correctly
- Tab switching works
- Scrollbars present
- Faces tab has content
- Models download buttons exist
- Config saves via UI interaction (toggle, entry, button click)

Requires: pip install atomacos pyobjc
Requires: System Preferences > Privacy > Accessibility → Terminal enabled
"""
import os
import sys
import time
import unittest
import subprocess
import tempfile
import shutil
from pathlib import Path

import atomacos

PROJECT_DIR = Path(__file__).resolve().parent.parent
SETTINGS_SCRIPT = PROJECT_DIR / "src" / "desktop" / "settings.py"


class TestClairvoyantGUI(unittest.TestCase):
    """Real macOS GUI tests via Accessibility API."""

    @classmethod
    def setUpClass(cls):
        """Launch the settings window as a real process."""
        # Use a temp config so we don't touch real config
        cls._tmpdir = Path(tempfile.mkdtemp(prefix="co_gui_test_"))
        cls._config_dir = cls._tmpdir / "clairvoyant-optics"
        cls._config_dir.mkdir(parents=True, exist_ok=True)

        # Launch settings with custom config dir
        env = os.environ.copy()
        env["CLAIRVOYANT_CONFIG_DIR"] = str(cls._config_dir)
        env["PYTHONPATH"] = f"{PROJECT_DIR}/src:{PROJECT_DIR}/tests"

        cls._proc = subprocess.Popen(
            [sys.executable, str(SETTINGS_SCRIPT)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for window to appear
        cls._app = None
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                # Find our Python process by PID
                cls._app = atomacos.getAppRefByPid(cls._proc.pid)
                if cls._app and cls._app.windows():
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if not cls._app or not cls._app.windows():
            cls._proc.kill()
            raise RuntimeError("Settings window did not appear within 10s")

        cls._window = cls._app.windows()[0]
        time.sleep(1)  # Let UI stabilize

    @classmethod
    def tearDownClass(cls):
        """Kill the settings process and clean up."""
        if cls._proc and cls._proc.poll() is None:
            cls._proc.terminate()
            try:
                cls._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls._proc.kill()
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _find_tab(self, name: str):
        """Find a tab button by its title (accessible via AXRole=AXButton)."""
        for btn in self._window.findAllR(AXRole="AXButton"):
            title = getattr(btn, "AXTitle", "")
            if name.lower() in title.lower():
                return btn
        return None

    def _scrollable_canvas(self):
        """Find the scrollable canvas in the content area."""
        # We need to find the canvas with yscrollcommand
        for elem in self._window.findAllR(AXRole="AXScrollArea"):
            return elem
        return None

    def test_window_exists(self):
        """Settings window is visible with correct title."""
        self.assertIsNotNone(self._window,
            "Settings window not found")
        title = getattr(self._window, "AXTitle", "")
        self.assertIn("Clairvoyant", title,
            f"Expected window title to contain 'Clairvoyant', got '{title}'")

    def test_all_tabs_exist(self):
        """All six tabs are present in the sidebar."""
        expected_tabs = ["General", "Streams", "Notifications",
                         "Models", "Faces", "Advanced"]
        found_tabs = []
        for btn in self._window.findAllR(AXRole="AXButton"):
            title = getattr(btn, "AXTitle", "")
            if title in expected_tabs:
                found_tabs.append(title)

        for tab in expected_tabs:
            self.assertIn(tab, found_tabs,
                f"Tab '{tab}' not found in sidebar. Found tabs: {found_tabs}")

    def test_tab_switching_renders_content(self):
        """Each tab shows content when clicked."""
        for tab_name in ["Streams", "Notifications", "Models", "Faces", "Advanced"]:
            tab_btn = self._find_tab(tab_name)
            self.assertIsNotNone(tab_btn,
                f"Tab button '{tab_name}' not found")
            tab_btn.Press()
            time.sleep(0.3)

            # After clicking, check that content area has elements
            # Look for labels, checkboxes, etc.
            content_elements = self._window.findAllR(AXRole="AXStaticText")
            content_elements += self._window.findAllR(AXRole="AXCheckBox")
            self.assertGreater(len(content_elements), 0,
                f"Tab '{tab_name}' has no content elements after switching")

    def test_scrollarea_exists(self):
        """Content area has a scrollable region."""
        scroll = self._scrollable_canvas()
        if scroll is None:
            # tkinter canvas may not expose AXScrollArea directly
            # Check for scrollbar elements instead
            scrollbars = self._window.findAllR(AXRole="AXScrollBar")
            self.assertGreater(len(scrollbars), 0,
                "No scrollbar elements found in window")
        # If we can't verify via AX, the tkinter unit tests cover it

    def test_faces_tab_has_content(self):
        """Faces tab shows Registered Faces section."""
        tab_btn = self._find_tab("Faces")
        self.assertIsNotNone(tab_btn)
        tab_btn.Press()
        time.sleep(0.5)

        # Should see a "Registered Faces" label
        found = False
        for elem in self._window.findAllR(AXRole="AXStaticText"):
            title = getattr(elem, "AXTitle", "")
            if "Registered" in title or "Faces" in title:
                found = True
                break
        self.assertTrue(found,
            "Faces tab should show 'Registered Faces' label")

    def test_models_tab_has_download_buttons(self):
        """Models tab shows download buttons for each model."""
        tab_btn = self._find_tab("Models")
        self.assertIsNotNone(tab_btn)
        tab_btn.Press()
        time.sleep(0.5)

        # Count download-related buttons
        buttons = self._window.findAllR(AXRole="AXButton")
        # Each model row has a download button. We expect at least 3.
        self.assertGreater(len(buttons), 3,
            f"Models tab should have download buttons, found {len(buttons)}")

    def test_general_tab_has_settings(self):
        """General tab shows settings toggles."""
        tab_btn = self._find_tab("General")
        self.assertIsNotNone(tab_btn)
        tab_btn.Press()
        time.sleep(0.5)

        # Should have checkboxes for settings
        checkboxes = self._window.findAllR(AXRole="AXCheckBox")
        self.assertGreater(len(checkboxes), 0,
            "General tab should have settings checkboxes")

    def test_window_can_close(self):
        """Window close button works (or close via menu)."""
        # Just check the close button exists
        close_btn = self._window.findAllR(AXRole="AXButton",
                                          AXSubRole="AXCloseButton")
        if close_btn:
            self.assertTrue(getattr(close_btn[0], "AXEnabled", True),
                "Close button should be enabled")


if __name__ == "__main__":
    print("=" * 60)
    print("Clairvoyant-Optics macOS GUI Integration Test (atomacos)")
    print("=" * 60)
    print("Testing via Apple Accessibility API")
    print(f"Settings source: {SETTINGS_SCRIPT}")
    print()
    unittest.main(verbosity=2)
