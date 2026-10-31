"""Reference fixture for the supported DSH/SillyTavern prompt semantics.

Expected values are hand-normalized from the DSH Preset Enhance compiler's
documented ordering rules; this is not a live differential execution test.
"""
from __future__ import annotations
import json
import unittest
from pathlib import Path

from st_bridge.preset import compile_preset, load_character, load_preset

FIXTURES = Path(__file__).parent / "fixtures"


class GoldenPresetTests(unittest.TestCase):
    def test_reference_compile_matches_expected(self):
        preset = load_preset(FIXTURES / "st-preset-reference.json")
        character = load_character(FIXTURES / "st-character-reference.json")
        expected = json.loads((FIXTURES / "dsh-reference-expected.json").read_text(encoding="utf-8"))
        compiled = compile_preset(
            preset,
            character=character,
            user_name="群友",
            macro_values={"lastUserMessage": "今晚吃什么?"},
        )
        actual = {
            "before_history": [
                {"identifier": p.identifier, "role": p.role, "text": p.text}
                for p in compiled.before_history
            ],
            "depth_entries": [
                {
                    "identifier": p.identifier,
                    "role": p.role,
                    "text": p.text,
                    "depth": p.injection_depth,
                    "order": p.injection_order,
                }
                for p in compiled.depth_entries
            ],
            "after_history": [
                {"identifier": p.identifier, "role": p.role, "text": p.text}
                for p in compiled.after_history
            ],
            "assistant_prefill": compiled.assistant_prefill,
        }
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
