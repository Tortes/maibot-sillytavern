from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

from st_bridge.preset import (
    PresetError, build_overlay, compile_preset, load_character, load_preset, safe_resource_path,
)

ROOT = Path(__file__).resolve().parents[1]


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.preset = load_preset(ROOT / "resources/example-st-preset.json")
        self.character = load_character(ROOT / "resources/example-character.json")

    def test_prompt_order_marker_and_macro(self):
        compiled = compile_preset(self.preset, character=self.character, user_name="喵喵")
        self.assertEqual(
            compiled.included,
            ("main", "charDescription", "charPersonality", "scenario", "dialogueExamples", "depthMemory", "afterHistory"),
        )
        self.assertEqual(len(compiled.before_history), 5)
        self.assertEqual(len(compiled.depth_entries), 1)
        self.assertEqual(len(compiled.after_history), 1)
        preview = build_overlay(self.preset, character=self.character, user_name="喵喵")
        self.assertLess(preview.text.index("你正在群聊中"), preview.text.index("阿澄性格"))
        self.assertIn("冷幽默", preview.text)
        self.assertIn("摄影", preview.text)
        self.assertIn("对 喵喵", preview.text)
        self.assertNotIn("{{", preview.text)

    def test_disabled_prompt_skipped(self):
        entry = next(
            item for item in self.preset["prompt_order"][0]["order"]
            if item["identifier"] == "charPersonality"
        )
        entry["enabled"] = False
        compiled = compile_preset(self.preset, character=self.character)
        self.assertNotIn("charPersonality", compiled.included)

    def test_unknown_macro_skips_entry(self):
        self.preset["prompts"][0]["content"] = "{{setvar::foo::bar}}"
        compiled = compile_preset(self.preset, character=self.character)
        self.assertNotIn("main", compiled.included)
        self.assertTrue(any("Unsupported macro" in warning for warning in compiled.warnings))

    def test_assistant_prefill_compiled(self):
        self.preset["assistant_prefill"] = "{{char}}:"
        compiled = compile_preset(self.preset, character=self.character)
        self.assertEqual(compiled.assistant_prefill, "阿澄:")

    def test_role_and_depth_metadata_preserved(self):
        self.preset["prompts"].append({
            "identifier": "depth", "role": "assistant", "content": "回到刚才的话题",
            "injection_position": 1, "injection_depth": 3, "injection_order": 7,
        })
        self.preset["prompts"].append({
            "identifier": "after", "role": "user", "content": "补充上下文",
        })
        self.preset["prompt_order"][0]["order"].extend([
            {"identifier": "depth", "enabled": True},
            {"identifier": "after", "enabled": True},
        ])
        compiled = compile_preset(self.preset, character=self.character)
        added_depth = next(item for item in compiled.depth_entries if item.identifier == "depth")
        added_after = next(item for item in compiled.after_history if item.identifier == "after")
        self.assertEqual(added_depth.role, "assistant")
        self.assertEqual(added_depth.injection_depth, 3)
        self.assertEqual(added_after.role, "user")

    def test_explicit_character_order_group(self):
        preset = {
            "prompts": [
                {"identifier": "a", "content": "default"},
                {"identifier": "b", "content": "other"},
            ],
            "prompt_order": [
                {"character_id": 100001, "order": [{"identifier": "a", "enabled": True}]},
                {"character_id": 42, "order": [{"identifier": "b", "enabled": True}]},
            ],
        }
        self.assertEqual(compile_preset(preset).included, ("a",))
        self.assertEqual(compile_preset(preset, character_id=42).included, ("b",))
        with self.assertRaises(PresetError):
            compile_preset(preset, character_id=99)

    def test_null_depth_and_order_use_defaults(self):
        preset = {
            "prompts": [{
                "identifier": "depth",
                "role": "assistant",
                "content": "depth prompt",
                "injection_position": 1,
                "injection_depth": None,
                "injection_order": None,
            }],
        }
        compiled = compile_preset(preset)
        self.assertEqual(compiled.depth_entries[0].injection_depth, 4)
        self.assertEqual(compiled.depth_entries[0].injection_order, 100)

    def test_duplicate_ids_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps({"prompts": [{"identifier": "x"}, {"identifier": "x"}]}))
            with self.assertRaises(PresetError):
                load_preset(path)

    def test_path_traversal_rejected(self):
        with self.assertRaises(PresetError):
            safe_resource_path(ROOT / "resources", "../README.md")

    def test_dsh_share_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wrap.json"
            path.write_text(json.dumps({
                "format": "dsh-preset-enhance",
                "preset": {"format": "sillytavern", "data": self.preset},
            }))
            self.assertEqual(len(load_preset(path)["prompts"]), 4)

    def test_lorebook_warning(self):
        character = dict(self.character, _has_character_book="true")
        compiled = compile_preset(self.preset, character=character)
        self.assertTrue(any("lorebook" in warning.lower() for warning in compiled.warnings))


if __name__ == "__main__":
    unittest.main()
