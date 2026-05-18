#!/usr/bin/env python3
"""Unit tests for settings.py config mapping — IPC ↔ daemon ↔ YAML.

Tests the key mapping layer WITHOUT needing a running daemon or GUI.
"""
import sys
import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, PropertyMock

# Ensure src/ is importable
TEST_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TEST_DIR.parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

# Mock tkinter before settings module loads
from unittest.mock import Mock
sys.modules["tkinter"] = Mock()
sys.modules["tkinter.ttk"] = Mock()


class TestKeyMapping(unittest.TestCase):
    """Test _key_to_section and _key_to_ipc_key mappings."""

    @classmethod
    def setUpClass(cls):
        # Import after tkinter is mocked
        from src.desktop import settings as s
        cls.s = s

    def test_key_to_section_general(self):
        cases = {
            "log_level": "general",
            "start_minimized": "general",
            "close_to_menu_bar": "general",
            "launch_at_login": "general",
            "confirm_quit": "general",
        }
        for key, expected in cases.items():
            self.assertEqual(self.s._key_to_section(key), expected, f"{key} → {expected}")

    def test_key_to_section_notifications(self):
        cases = {
            "notifications_enabled": "notifications",
            "notify_on_family": "notifications",
            "notify_on_unknown": "notifications",
            "notification_sound_family": "notifications",
            "notification_sound_alert": "notifications",
            "notification_dnd_start": "notifications",
            "notification_dnd_end": "notifications",
        }
        for key, expected in cases.items():
            self.assertEqual(self.s._key_to_section(key), expected, f"{key} → {expected}")

    def test_key_to_section_web(self):
        cases = {
            "api_host": "web",
            "api_port": "web",
            "api_enabled": "web",
        }
        for key, expected in cases.items():
            self.assertEqual(self.s._key_to_section(key), expected, f"{key} → {expected}")

    def test_key_to_section_telemetry(self):
        cases = {
            "auto_update": "telemetry",
            "error_reporting": "telemetry",
        }
        for key, expected in cases.items():
            self.assertEqual(self.s._key_to_section(key), expected, f"{key} → {expected}")

    def test_key_to_section_battery(self):
        cases = {
            "pause_on_battery": "battery",
            "pause_when_away": "battery",
            "home_ssids": "battery",
        }
        for key, expected in cases.items():
            self.assertEqual(self.s._key_to_section(key), expected, f"{key} → {expected}")

    def test_key_to_ipc_key_notifications(self):
        """Daemon dataclass field names for notifications section."""
        cases = {
            "notifications_enabled": "enabled",
            "notify_on_family": "notify_on_family",
            "notify_on_unknown": "notify_on_unknown",
            "notification_sound_family": "sound_family",
            "notification_sound_alert": "sound_alert",
            "notification_dnd_start": "dnd_start",
            "notification_dnd_end": "dnd_end",
        }
        for key, expected in cases.items():
            self.assertEqual(self.s._key_to_ipc_key(key), expected, f"{key} → {expected}")

    def test_key_to_ipc_key_web(self):
        """web section: api_host → host, api_port → port."""
        cases = {
            "api_host": "host",
            "api_port": "port",
            "api_enabled": "enabled",
        }
        for key, expected in cases.items():
            self.assertEqual(self.s._key_to_ipc_key(key), expected, f"{key} → {expected}")

    def test_key_to_ipc_key_general(self):
        """General keys pass through unchanged."""
        cases = {
            "log_level": "log_level",
            "launch_at_login": "launch_at_login",
            "auto_update": "auto_update",
            "error_reporting": "error_reporting",
            "home_ssids": "home_ssids",
        }
        for key, expected in cases.items():
            self.assertEqual(self.s._key_to_ipc_key(key), expected, f"{key} → {expected}")

    def test_unknown_key_defaults_to_self(self):
        """Unknown key should fall back to identity mapping."""
        self.assertEqual(self.s._key_to_section("nonexistent_key"), "general")
        self.assertEqual(self.s._key_to_ipc_key("nonexistent_key"), "nonexistent_key")


class TestSettingsKeyToDaemon(unittest.TestCase):
    """Test _settings_key_to_daemon type coercion."""

    @classmethod
    def setUpClass(cls):
        from src.desktop import settings as s
        cls.s = s

    def test_home_ssids_string_to_list(self):
        """UI stores comma-separated, daemon expects list[str]."""
        section, ipc_key, value = self.s._settings_key_to_daemon("home_ssids", "wifi1, wifi2")
        self.assertEqual(section, "battery")
        self.assertEqual(ipc_key, "home_ssids")
        self.assertEqual(value, ["wifi1", "wifi2"])

    def test_home_ssids_empty_string_to_empty_list(self):
        section, ipc_key, value = self.s._settings_key_to_daemon("home_ssids", "")
        self.assertEqual(value, [])

    def test_port_string_to_int(self):
        section, ipc_key, value = self.s._settings_key_to_daemon("api_port", "8765")
        self.assertEqual(section, "web")
        self.assertEqual(ipc_key, "port")
        self.assertEqual(value, 8765)

    def test_notification_bool_passthrough(self):
        """Boolean values for notification toggles pass through unchanged."""
        section, ipc_key, value = self.s._settings_key_to_daemon("notify_on_family", True)
        self.assertEqual(section, "notifications")
        self.assertEqual(ipc_key, "notify_on_family")
        self.assertEqual(value, True)

    def test_notification_string_passthrough(self):
        section, ipc_key, value = self.s._settings_key_to_daemon("notification_sound_family", "ping")
        self.assertEqual(section, "notifications")
        self.assertEqual(ipc_key, "sound_family")
        self.assertEqual(value, "ping")

    def test_dnd_string_passthrough(self):
        section, ipc_key, value = self.s._settings_key_to_daemon("notification_dnd_start", "22:00")
        self.assertEqual(section, "notifications")
        self.assertEqual(ipc_key, "dnd_start")
        self.assertEqual(value, "22:00")


class TestDaemonToSettingsValue(unittest.TestCase):
    """Test _daemon_to_settings_value reverse transform."""

    @classmethod
    def setUpClass(cls):
        from src.desktop import settings as s
        cls.s = s

    def test_home_ssids_list_to_string(self):
        """Daemon returns list[str], UI needs comma-separated string."""
        result = self.s._daemon_to_settings_value("battery", "home_ssids", ["wifi1", "wifi2"])
        self.assertEqual(result, "wifi1, wifi2")

    def test_home_ssids_empty_list_to_empty_string(self):
        result = self.s._daemon_to_settings_value("battery", "home_ssids", [])
        self.assertEqual(result, "")

    def test_regular_value_passthrough(self):
        """Non-special values pass through unchanged."""
        result = self.s._daemon_to_settings_value("notifications", "notify_on_family", True)
        self.assertEqual(result, True)
        result = self.s._daemon_to_settings_value("web", "host", "127.0.0.1")
        self.assertEqual(result, "127.0.0.1")


class TestSaveKeyFallback(unittest.TestCase):
    """Test save_key fallback writes section-aware YAML.

    Mocks IPC to be unreachable so fallback path is tested.
    """

    @classmethod
    def setUpClass(cls):
        from src.desktop import settings as s
        cls.s = s

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config_path = Path(self.tmpdir) / "config.yaml"
        # Override CONFIG_FILE for the fallback
        self._orig_config_file = self.s.CONFIG_FILE
        self.s.CONFIG_FILE = self.config_path

    def tearDown(self):
        self.s.CONFIG_FILE = self._orig_config_file
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch('src.desktop.settings._ipc_call', return_value=None)
    def test_fallback_writes_notification_under_section(self, mock_ipc):
        """Fallback should write notify_on_family under notifications: section."""
        # Pre-populate with a valid section structure
        import yaml
        with open(self.config_path, 'w') as f:
            yaml.dump({"notifications": {"enabled": True}}, f)

        # Call with IPC unreachable
        self.s.save_key("notify_on_family", False)

        # Read back — should be under notifications, NOT root
        with open(self.config_path) as f:
            data = yaml.safe_load(f) or {}

        self.assertIn("notifications", data, "notifications section must exist")
        section = data["notifications"]
        self.assertIn("notify_on_family", section,
                       f"notify_on_family must be under notifications section, got keys: {list(data.keys())}")
        self.assertEqual(section["notify_on_family"], False)

    @patch('src.desktop.settings._ipc_call', return_value=None)
    def test_fallback_writes_dnd_under_notifications(self, mock_ipc):
        """DND keys should land under notifications section."""
        import yaml
        with open(self.config_path, 'w') as f:
            yaml.dump({"notifications": {}}, f)

        self.s.save_key("notification_dnd_start", "22:00")

        with open(self.config_path) as f:
            data = yaml.safe_load(f) or {}
        self.assertEqual(data["notifications"]["dnd_start"], "22:00")

    @patch('src.desktop.settings._ipc_call', return_value=None)
    def test_fallback_writes_telemetry_under_telemetry(self, mock_ipc):
        """auto_update should land under telemetry section."""
        import yaml
        with open(self.config_path, 'w') as f:
            yaml.dump({}, f)

        self.s.save_key("auto_update", True)

        with open(self.config_path) as f:
            data = yaml.safe_load(f) or {}
        self.assertIn("telemetry", data)
        self.assertEqual(data["telemetry"]["auto_update"], True)

    @patch('src.desktop.settings._ipc_call', return_value=None)
    def test_fallback_writes_api_host_under_web(self, mock_ipc):
        """api_host should land under web section, not root."""
        import yaml
        with open(self.config_path, 'w') as f:
            yaml.dump({}, f)

        self.s.save_key("api_host", "0.0.0.0")

        with open(self.config_path) as f:
            data = yaml.safe_load(f) or {}
        self.assertIn("web", data)
        self.assertEqual(data["web"]["host"], "0.0.0.0")

    @patch('src.desktop.settings._ipc_call', return_value=None)
    def test_fallback_writes_home_ssids_as_list_under_battery(self, mock_ipc):
        """home_ssids string → list[str] under battery section."""
        import yaml
        with open(self.config_path, 'w') as f:
            yaml.dump({}, f)

        self.s.save_key("home_ssids", "wifi1, wifi2")

        with open(self.config_path) as f:
            data = yaml.safe_load(f) or {}
        self.assertIn("battery", data)
        self.assertEqual(data["battery"]["home_ssids"], ["wifi1", "wifi2"])


class TestDefaultsConsistency(unittest.TestCase):
    """Verify DEFAULTS covers all keys in the mapping."""

    @classmethod
    def setUpClass(cls):
        from src.desktop import settings as s
        cls.s = s

    def test_all_mapped_keys_have_defaults(self):
        """Every key in _key_to_section should have a DEFAULTS entry."""
        # Get all keys from the section mapping
        section_func = self.s._key_to_section
        # We can introspect by looking at a few known keys — better approach:
        mapping_keys = {
            "log_level", "start_minimized", "close_to_menu_bar",
            "launch_at_login", "confirm_quit",
            "auto_update", "error_reporting",
            "pause_on_battery", "pause_when_away", "home_ssids",
            "api_host", "api_port", "api_enabled",
            "notifications_enabled", "notify_on_family", "notify_on_unknown",
            "notification_sound_family", "notification_sound_alert",
            "notification_dnd_start", "notification_dnd_end",
        }
        defaults_keys = set(self.s.DEFAULTS.keys())
        # Cameras has a special path in load_config
        mapping_keys.discard("cameras")
        # api_host/api_port don't need DEFAULTS entries —
        # they get their defaults from the daemon's WebConfig dataclass.
        # api_enabled has a DEFAULTS entry, so it stays in the comparison.
        mapping_keys.discard("api_host")
        mapping_keys.discard("api_port")

        missing_in_defaults = mapping_keys - defaults_keys
        self.assertSetEqual(
            missing_in_defaults, set(),
            f"Keys in mapping but missing from DEFAULTS: {missing_in_defaults}"
        )

        extra_in_defaults = defaults_keys - mapping_keys - {"cameras"}
        self.assertSetEqual(
            extra_in_defaults, set(),
            f"Keys in DEFAULTS but not in mapping: {extra_in_defaults}"
        )


if __name__ == "__main__":
    unittest.main()
