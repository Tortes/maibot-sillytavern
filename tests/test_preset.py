from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

from st_bridge.preset import (
    PresetError, build_overlay, load_character, load_preset, safe_resource_path,
)

ROOT = Path(__file__).resolve().parents[1]

class PresetTests(unittest.TestCase):
    def setUp(self):
        self.preset = load_preset(ROOT / "resources/example-st-preset.json")
        self.character = load_character(ROOT / "resources/example-character.json")

    def test_prompt_order_marker_and_macro(self):
        p = build_overlay(self.preset, character=self.character, user_name="喵喵")
        self.assertEqual(p.included, ("main", "charDescription", "style"))
        self.assertLess(p.text.index("你在群聊"), p.text.index("阿澄性格"))
        self.assertLess(p.text.index("阿澄性格"), p.text.index("对 喵喵 说话"))
        self.assertNotIn("{{", p.text)
        self.assertFalse(any("chatHistory" in s for s in p.warnings))

    def test_disabled_prompt_skipped(self):
        self.preset["prompt_order"][0]["order"][2]["enabled"] = False
        p = build_overlay(self.preset, character=self.character)
        self.assertNotIn("style", p.included)

    def test_unknown_macro_skips_entry(self):
        self.preset["prompts"][0]["content"] = "{{setvar::foo::bar}}"
        p = build_overlay(self.preset, character=self.character)
        self.assertNotIn("main", p.included)
        self.assertTrue(any("Unsupported macro" in s for s in p.warnings))

    def test_assistant_prefill_flagged_and_skipped(self):
        self.preset["prompts"].append({"identifier": "prefix", "role": "assistant", "content": "你好"})
        self.preset["prompt_order"][0]["order"].append({"identifier": "prefix", "enabled": True})
        p = build_overlay(self.preset, character=self.character)
        self.assertNotIn("prefix", p.included)
        self.assertTrue(any("prefill" in s for s in p.warnings))

    def test_duplicate_ids_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "bad.json"
            f.write_text(json.dumps({"prompts": [{"identifier": "x"}, {"identifier": "x"}]}))
            with self.assertRaises(PresetError):
                load_preset(f)

    def test_path_traversal_rejected(self):
        with self.assertRaises(PresetError):
            safe_resource_path(ROOT / "resources", "../README.md")

    def test_dsh_share_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wrap.json"
            path.write_text(json.dumps({"format":"dsh-preset-enhance","preset":{"format":"sillytavern","data":self.preset}}))
            self.assertEqual(len(load_preset(path)["prompts"]), 4)

    def test_lorebook_warning(self):
        c = dict(self.character, _has_character_book="true")
        p = build_overlay(self.preset, character=c)
        self.assertTrue(any("lorebook" in x.lower() for x in p.warnings))

if __name__ == "__main__":
    unittest.main()
