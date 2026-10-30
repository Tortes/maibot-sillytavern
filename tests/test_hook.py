"""Hook payload test without importing the live MaiBot SDK."""
from __future__ import annotations
import importlib
import asyncio
from types import SimpleNamespace
import sys
import types
import unittest

class HookTests(unittest.TestCase):
    def test_preserves_metadata_and_multimodal(self):
        # The production SDK isn't installed for standalone test; stub its decorators.
        mod = types.ModuleType("maibot_sdk")
        class Base: pass
        mod.MaiBotPlugin = Base
        mod.PluginConfigBase = object
        mod.HookHandler = lambda *args, **kwargs: (lambda fn: fn)
        types_mod = types.ModuleType("maibot_sdk.types")
        types_mod.HookMode = types.SimpleNamespace(BLOCKING="blocking")
        types_mod.HookOrder = types.SimpleNamespace(LATE="late")
        sys.modules["maibot_sdk"] = mod
        sys.modules["maibot_sdk.types"] = types_mod
        try:
            from pydantic import BaseModel
            mod.PluginConfigBase = BaseModel
            plugin = importlib.import_module("plugin")
            items = [
                {"item_type": "SystemMessageItem", "meta": {"item_id":"abc", "logical_turn_id":None, "timestamp":"2026-10-30T00:00:00+00:00"}, "parts":[{"type":"text", "text":"base"}]},
                {"item_type": "UserMessageItem", "meta": {"item_id":"def", "logical_turn_id":None, "timestamp":"2026-10-30T00:00:00+00:00"}, "parts":[{"type":"image", "image_base64":"abc", "image_format":"png"}]},
            ]
            result = plugin.append_system_overlay(items, "角色设定")
            self.assertEqual(result[0]["meta"], items[0]["meta"])
            self.assertEqual(result[1], items[1])
            self.assertEqual(len(items[0]["parts"]), 1)  # no mutation of original
            self.assertIsNone(plugin.append_system_overlay(result, "角色设定"))
            obj = plugin.SillyTavernBridgePlugin()
            obj.config = SimpleNamespace(
                plugin=SimpleNamespace(enabled=True),
                max_chars=16000,
                bindings=[SimpleNamespace(
                    enabled=True, session_id="session-01", preset_file="example-st-preset.json",
                    character_file="example-character.json", user_name="群友", char_name=""
                )],
            )
            outgoing = asyncio.run(obj.on_replyer_before_model_request(session_id="session-01", items=items))
            self.assertEqual(outgoing["action"], "continue")
            merged = outgoing["modified_kwargs"]["items"]
            self.assertIn("阿澄", merged[0]["parts"][-1]["text"])
            self.assertEqual(merged[1], items[1])
            self.assertIsNone(asyncio.run(obj.on_replyer_before_model_request(session_id="other", items=items)))
        finally:
            sys.modules.pop("plugin", None)
            sys.modules.pop("maibot_sdk", None)
            sys.modules.pop("maibot_sdk.types", None)

if __name__ == "__main__":
    unittest.main()
