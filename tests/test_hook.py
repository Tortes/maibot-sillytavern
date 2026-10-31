"""MaiBot hook adapter tests using a small SDK stub."""
from __future__ import annotations
import asyncio
import importlib
import sys
import types
import unittest
from types import SimpleNamespace


class HookTests(unittest.TestCase):
    def test_exact_session_binding_and_structured_items(self):
        from pydantic import BaseModel

        sdk = types.ModuleType("maibot_sdk")
        class BasePlugin:
            pass
        sdk.MaiBotPlugin = BasePlugin
        sdk.PluginConfigBase = BaseModel
        sdk.HookHandler = lambda *args, **kwargs: (lambda fn: fn)
        sdk_types = types.ModuleType("maibot_sdk.types")
        sdk_types.HookMode = SimpleNamespace(BLOCKING="blocking")
        sdk_types.HookOrder = SimpleNamespace(LATE="late")
        sys.modules["maibot_sdk"] = sdk
        sys.modules["maibot_sdk.types"] = sdk_types

        try:
            plugin_module = importlib.import_module("plugin")
            plugin = plugin_module.SillyTavernBridgePlugin()
            plugin.config = SimpleNamespace(
                plugin=SimpleNamespace(enabled=True),
                max_chars=16000,
                bindings=[SimpleNamespace(
                    enabled=True,
                    session_id="session-01",
                    preset_file="example-st-preset.json",
                    character_file="example-character.json",
                    user_name="喵喵",
                    char_name="",
                    character_id="100001",
                    trigger="normal",
                    allow_assistant_prefill=False,
                )],
            )
            items = [
                {
                    "item_type": "SystemMessageItem",
                    "meta": {"item_id": "sys", "logical_turn_id": None, "timestamp": "2026-10-30T00:00:00+00:00"},
                    "parts": [{"type": "text", "text": "MaiBot host system prompt"}],
                },
                {
                    "item_type": "UserMessageItem",
                    "meta": {"item_id": "history", "logical_turn_id": None, "timestamp": "2026-10-30T00:01:00+00:00"},
                    "parts": [{"type": "text", "text": "以前聊过摄影"}],
                },
                {
                    "item_type": "UserMessageItem",
                    "meta": {"item_id": "final", "logical_turn_id": None, "timestamp": "2026-10-31T13:57:00+08:00"},
                    "parts": [{"type": "text", "text": "当前时间：2026-10-31 13:57:00"}],
                },
            ]
            schema_version = 1
            result = asyncio.run(plugin.on_replyer_before_model_request(
                session_id="session-01",
                items=items,
                item_schema_version=schema_version,
                reply_reason="自然回复",
                reply_tool_args={},
            ))
            self.assertEqual(result["action"], "continue")
            modified = result["modified_kwargs"]
            self.assertEqual(modified["item_schema_version"], schema_version)
            self.assertEqual(modified["session_id"], "session-01")
            output = modified["items"]
            texts = [
                part.get("text", "")
                for item in output
                for part in item.get("parts", [])
                if part.get("type") == "text"
            ]
            self.assertIn("阿澄性格慢热", "\n".join(texts))
            self.assertEqual(output[0]["meta"]["item_id"], "sys")
            self.assertEqual(output[-1]["meta"]["item_id"], "final")
            self.assertEqual(items[0]["parts"][0]["text"], "MaiBot host system prompt")

            unmatched = asyncio.run(plugin.on_replyer_before_model_request(
                session_id="another-session", items=items, item_schema_version=schema_version,
            ))
            self.assertIsNone(unmatched)
        finally:
            sys.modules.pop("plugin", None)
            sys.modules.pop("maibot_sdk", None)
            sys.modules.pop("maibot_sdk.types", None)


if __name__ == "__main__":
    unittest.main()
