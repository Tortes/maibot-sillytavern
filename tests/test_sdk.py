"""Smoke-test the plugin against the published MaiBot SDK."""
from __future__ import annotations
import unittest

from plugin import create_plugin


class MaiBotSdkSmokeTests(unittest.TestCase):
    def test_plugin_config_model_and_schema(self):
        plugin = create_plugin()
        defaults = plugin.get_default_config()
        self.assertFalse(defaults["plugin"]["enabled"])
        self.assertEqual(defaults["bindings"], [])
        plugin.set_plugin_config(defaults)
        self.assertFalse(plugin.config.plugin.enabled)
        schema = plugin.get_webui_config_schema(
            plugin_id="tortes.maibot-sillytavern",
            plugin_name="MaiBot SillyTavern Preset Bridge",
            plugin_version="0.2.0",
            plugin_description="SillyTavern preset bridge",
            plugin_author="Tortes",
        )
        self.assertTrue(schema)


if __name__ == "__main__":
    unittest.main()
