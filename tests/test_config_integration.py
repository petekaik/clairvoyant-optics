"""Integration tests for service-level config — YAML serialization, IPC sound, on_change.

Tests the daemon-level behaviour that the previous 24 unit tests didn't cover.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

TEST_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TEST_DIR.parent
sys.path.insert(0, str(PROJECT_DIR / "src"))


class TestConfigStoreYamlFormat(unittest.TestCase):
    """ConfigStore _persist must produce YAML that round-trips correctly."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.config_path = self.tmpdir / "config.yaml"
        # Write minimal config to disk
        self.config_path.write_text("""
general:
  log_level: INFO
notifications:
  dnd_start: '22:00'
  dnd_end: '06:00'
web:
  host: 127.0.0.1
  port: 8765
  enabled: false
battery:
  home_ssids: []
""")

    def tearDown(self):
        import shutil
        shutil.rmtree(str(self.tmpdir), ignore_errors=True)

    def test_dnd_times_are_quoted_in_yaml(self):
        """dnd_start/dnd_end must be quoted to avoid YAML 1.1 sexagesimal parse."""
        # Import after mocking tkinter
        import unittest.mock as mock
        sys.modules["tkinter"] = mock.MagicMock()
        sys.modules["tkinter.ttk"] = mock.MagicMock()
        sys.modules["tkinter.font"] = mock.MagicMock()
        sys.modules["tkinter.filedialog"] = mock.MagicMock()
        sys.modules["tkinter.messagebox"] = mock.MagicMock()
        from src.service.config_store import ConfigStore, NotificationConfig

        store = ConfigStore(self.config_path)

        # Read existing: `dnd_start: '22:00'` → should be string "22:00"
        self.assertEqual(store.config.notifications.dnd_start, "22:00")
        self.assertEqual(store.config.notifications.dnd_end, "06:00")

        # Now set a new DND time
        store.set("notifications", "dnd_start", "23:30")

        # Read back from memory
        self.assertEqual(store.config.notifications.dnd_start, "23:30")

        # Read from file — must have quotes
        raw = self.config_path.read_text()
        self.assertIn("dnd_start: '23:30'", raw,
                       f"Expected quoted dnd_start, got:\n{raw}")

        # Round-trip: reload from disk
        store.reload()
        self.assertEqual(store.config.notifications.dnd_start, "23:30")

    def test_yaml_roundtrip_after_set(self):
        """ConfigStore.set → persist → reload must preserve all values."""
        import unittest.mock as mock
        sys.modules["tkinter"] = mock.MagicMock()
        sys.modules["tkinter.ttk"] = mock.MagicMock()
        sys.modules["tkinter.font"] = mock.MagicMock()
        sys.modules["tkinter.filedialog"] = mock.MagicMock()
        sys.modules["tkinter.messagebox"] = mock.MagicMock()
        from src.service.config_store import ConfigStore

        store = ConfigStore(self.config_path)

        store.set("notifications", "sound_family", "ping")
        store.set("web", "enabled", True)
        store.set("web", "port", 8080)

        store.reload()
        self.assertEqual(store.config.notifications.sound_family, "ping")
        self.assertEqual(store.config.web.enabled, True)
        self.assertEqual(store.config.web.port, 8080)


class TestOnChangeCallbacks(unittest.TestCase):
    """ConfigStore.on_change must fire when set() is called."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.config_path = self.tmpdir / "config.yaml"
        self.config_path.write_text("""
general:
  log_level: INFO
notifications:
  enabled: true
  sound_family: default
web:
  host: 127.0.0.1
  port: 8765
  enabled: false
""")
        import unittest.mock as mock
        sys.modules["tkinter"] = mock.MagicMock()
        sys.modules["tkinter.ttk"] = mock.MagicMock()
        sys.modules["tkinter.font"] = mock.MagicMock()
        sys.modules["tkinter.filedialog"] = mock.MagicMock()
        sys.modules["tkinter.messagebox"] = mock.MagicMock()
        from src.service.config_store import ConfigStore
        self.store = ConfigStore(self.config_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(str(self.tmpdir), ignore_errors=True)

    def test_on_change_web_host_fires_callback(self):
        """Setting web.host must trigger on_change('web') callback."""
        calls = []

        def cb(section, key, value):
            calls.append((section, key, value))

        self.store.on_change("web", cb)
        self.store.set("web", "host", "0.0.0.0")

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], ("web", "host", "0.0.0.0"))

    def test_on_change_notifications_does_not_fire_web(self):
        """Setting a notification should NOT trigger web callbacks."""
        calls = []

        def cb(section, key, value):
            calls.append((section, key, value))

        self.store.on_change("web", cb)
        self.store.set("notifications", "sound_family", "ping")

        self.assertEqual(len(calls), 0, "Web callback should not fire for notifications")

    def test_on_change_multiple_sections(self):
        """Multiple independent section callbacks must work."""
        web_calls = []
        notif_calls = []

        def web_cb(s, k, v):
            web_calls.append((s, k, v))

        def notif_cb(s, k, v):
            notif_calls.append((s, k, v))

        self.store.on_change("web", web_cb)
        self.store.on_change("notifications", notif_cb)

        self.store.set("web", "port", 9999)
        self.store.set("notifications", "sound_alert", "alarm")

        self.assertEqual(len(web_calls), 1)
        self.assertEqual(len(notif_calls), 1)
        self.assertEqual(web_calls[0][2], 9999)
        self.assertEqual(notif_calls[0][2], "alarm")

    def test_on_change_multiple_callbacks_same_section(self):
        """Multiple callbacks for same section must all fire."""
        calls = []

        def cb1(s, k, v):
            calls.append(f"cb1:{k}={v}")

        def cb2(s, k, v):
            calls.append(f"cb2:{k}={v}")

        self.store.on_change("web", cb1)
        self.store.on_change("web", cb2)
        self.store.set("web", "enabled", True)

        self.assertEqual(len(calls), 2)
        self.assertIn("cb1:enabled=True", calls)
        self.assertIn("cb2:enabled=True", calls)


class TestDaemonTestNotifySound(unittest.TestCase):
    """Daemon.test_notify must read configured sound from config."""

    def test_notify_uses_configured_sound(self):
        """When sound_family='ping', test_notify should use 'ping' not hardcoded 'default'."""
        import unittest.mock as mock
        sys.modules["tkinter"] = mock.MagicMock()
        sys.modules["tkinter.ttk"] = mock.MagicMock()
        sys.modules["tkinter.font"] = mock.MagicMock()
        sys.modules["tkinter.filedialog"] = mock.MagicMock()
        sys.modules["tkinter.messagebox"] = mock.MagicMock()
        from src.service.config_store import ConfigStore, NotificationConfig, Config

        # Mock config with a custom sound
        mock_config = MagicMock(spec=Config)
        mock_notifications = MagicMock(spec=NotificationConfig)
        mock_notifications.sound_family = "ping"
        mock_notifications.sound_alert = "alarm"
        mock_config.notifications = mock_notifications

        mock_store = MagicMock(spec=ConfigStore)
        mock_store.config = mock_config

        # Now test the actual test_notify handler
        from src.service.daemon import _build_ipc_methods
        mock_orch = MagicMock()
        methods = _build_ipc_methods(mock_store, mock_orch)

        # Patch subprocess.run to verify the osascript command
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = methods["test_notify"]({
                "title": "Test",
                "subtitle": "",
                "message": "Test notification",
                "sound_key": "sound_family",
            })

            self.assertTrue(result.get("ok"), f"test_notify failed: {result}")

            # Verify the osascript script contains "ping" not "default"
            call_args = mock_run.call_args
            script = call_args[0][0][-1]  # Last arg to osascript
            self.assertIn('sound name "ping"', script,
                          f"Expected 'ping' sound in osascript, got: {script}")
            self.assertNotIn('sound name "default"', script,
                             "Should not use hardcoded 'default' sound")

    def test_notify_sound_alert_uses_sound_alert(self):
        """Test Alert button must use sound_alert from config."""
        import unittest.mock as mock
        sys.modules["tkinter"] = mock.MagicMock()
        sys.modules["tkinter.ttk"] = mock.MagicMock()
        sys.modules["tkinter.font"] = mock.MagicMock()
        sys.modules["tkinter.filedialog"] = mock.MagicMock()
        sys.modules["tkinter.messagebox"] = mock.MagicMock()
        from src.service.config_store import ConfigStore, NotificationConfig, Config

        mock_config = MagicMock(spec=Config)
        mock_notifications = MagicMock(spec=NotificationConfig)
        mock_notifications.sound_family = "default"
        mock_notifications.sound_alert = "alarm"
        mock_config.notifications = mock_notifications

        mock_store = MagicMock(spec=ConfigStore)
        mock_store.config = mock_config

        from src.service.daemon import _build_ipc_methods
        mock_orch = MagicMock()
        methods = _build_ipc_methods(mock_store, mock_orch)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = methods["test_notify"]({
                "title": "Alert!",
                "message": "Unknown person!",
                "sound_key": "sound_alert",
            })

            self.assertTrue(result.get("ok"))
            script = mock_run.call_args[0][0][-1]
            self.assertIn('sound name "alarm"', script)

    def test_notify_fallback_default_sound(self):
        """If notification config is None, should fallback to 'default'."""
        import unittest.mock as mock
        sys.modules["tkinter"] = mock.MagicMock()
        sys.modules["tkinter.ttk"] = mock.MagicMock()
        sys.modules["tkinter.font"] = mock.MagicMock()
        sys.modules["tkinter.filedialog"] = mock.MagicMock()
        sys.modules["tkinter.messagebox"] = mock.MagicMock()
        from src.service.config_store import Config, NotificationConfig

        mock_config = MagicMock(spec=Config)
        mock_config.notifications = None  # Simulate missing section

        mock_store = MagicMock()
        mock_store.config = mock_config

        from src.service.daemon import _build_ipc_methods
        mock_orch = MagicMock()
        methods = _build_ipc_methods(mock_store, mock_orch)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = methods["test_notify"]({
                "title": "Test",
                "message": "ping",
                "sound_key": "sound_family",
            })
            self.assertTrue(result.get("ok"))
            script = mock_run.call_args[0][0][-1]
            self.assertIn('sound name "default"', script,
                          "Fallback should use 'default' when no notification config")


if __name__ == "__main__":
    unittest.main()
