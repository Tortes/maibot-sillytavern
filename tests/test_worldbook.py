from __future__ import annotations

import unittest
from pathlib import Path

from st_bridge.preset import PresetError, load_character
from st_bridge.worldbook import (
    compile_worldbooks,
    extract_scan_messages,
    load_worldbook,
    normalize_worldbook,
)

ROOT = Path(__file__).resolve().parents[1]


def item(item_type: str, text: str, item_id: str) -> dict:
    return {
        "item_type": item_type,
        "meta": {"item_id": item_id, "logical_turn_id": None, "timestamp": "2026-10-31T12:00:00+08:00"},
        "parts": [{"type": "text", "text": text}],
    }


def entry(uid: int, **overrides) -> dict:
    value = {
        "uid": uid,
        "key": [],
        "keysecondary": [],
        "content": f"lore-{uid}",
        "constant": False,
        "selective": False,
        "selectiveLogic": 0,
        "order": 100,
        "position": 0,
        "disable": False,
        "probability": 100,
        "useProbability": False,
        "depth": 4,
        "role": 0,
        "scanDepth": None,
        "caseSensitive": False,
        "matchWholeWords": False,
        "excludeRecursion": False,
        "preventRecursion": False,
        "delayUntilRecursion": False,
    }
    value.update(overrides)
    return value


def book(entries: list[dict], **settings) -> dict:
    value = {"name": "test-book", "entries": {str(e["uid"]): e for e in entries}}
    value.update(settings)
    return value


class WorldbookTests(unittest.TestCase):
    def test_load_standalone_worldbook_export(self):
        loaded = load_worldbook(ROOT / "resources" / "example-worldbook.json")
        self.assertEqual(loaded["name"], "阿澄的沙丘话题补充")
        self.assertEqual(len(loaded["_normalized_entries"]), 5)

    def test_character_v2_preserves_embedded_character_book(self):
        character = load_character(ROOT / "resources" / "example-character.json")
        self.assertIn("_character_book", character)
        result = compile_worldbooks(
            [character["_character_book"]],
            [item("UserMessageItem", "你平时怎么做胶片冲洗？我想看看暗房。", "u1")],
            character=character,
        )
        self.assertEqual(len(result.before_character), 1)
        self.assertIn("小暗房", result.before_character[0].text)

    def test_keyword_activation_and_disabled_entries(self):
        data = book([
            entry(1, key=["沙丘"], content="沙丘设定被激活"),
            entry(2, key=["沙丘"], content="禁用内容", disable=True),
            entry(3, constant=True, content="常驻设定"),
        ])
        result = compile_worldbooks(
            [data], [item("UserMessageItem", "我刚看完沙丘。", "u1")],
        )
        texts = [p.text for p in result.before_character]
        self.assertIn("沙丘设定被激活", texts)
        self.assertIn("常驻设定", texts)
        self.assertNotIn("禁用内容", texts)

    def test_scan_depth_uses_recent_user_and_assistant_messages(self):
        data = book([
            entry(1, key=["旧地点"], content="旧消息命中", scanDepth=3),
            entry(2, key=["旧地点"], content="不应命中", scanDepth=1),
            entry(3, key=["新地点"], content="新消息命中", scanDepth=2),
        ])
        messages = [
            item("UserMessageItem", "我们去了旧地点", "u1"),
            item("AssistantMessageItem", "新地点不错", "a1"),
            item("UserMessageItem", "今天继续聊", "u2"),
        ]
        result = compile_worldbooks([data], messages, scan_depth=1)
        texts = [p.text for p in result.before_character]
        self.assertIn("旧消息命中", texts)
        self.assertNotIn("不应命中", texts)
        self.assertIn("新消息命中", texts)

    def test_scan_includes_current_user_message_but_excludes_host_tail(self):
        messages = [
            item("SystemMessageItem", "system 沙丘", "sys"),
            item("UserMessageItem", "以前聊过摄影", "u1"),
            item("UserMessageItem", "时间：2026-10-31 12:00:00", "time"),
            item("UserMessageItem", "我想聊聊沙丘", "current"),
            item("UserMessageItem", "当前聊天额外注意事项：不要刷屏", "tail"),
        ]
        self.assertEqual(
            extract_scan_messages(messages),
            ["以前聊过摄影", "我想聊聊沙丘"],
        )
        result = compile_worldbooks(
            [book([entry(1, key=["沙丘"], content="命中当前消息")])],
            messages,
        )
        self.assertIn("命中当前消息", [p.text for p in result.before_character])

    def test_selective_logic_and_any(self):
        messages = [item("UserMessageItem", "沙丘 保罗", "u1")]
        def active(logic: int) -> bool:
            result = compile_worldbooks(
                [book([entry(
                    1, key=["沙丘"], keysecondary=["保罗", "香料"],
                    selective=True, selectiveLogic=logic, content="selective lore",
                )])],
                messages,
            )
            return any(p.text == "selective lore" for p in result.before_character)
        self.assertTrue(active(0))   # AND_ANY
        self.assertTrue(active(1))   # NOT_ALL
        self.assertFalse(active(2))  # NOT_ANY
        self.assertFalse(active(3))  # AND_ALL

    def test_selective_logic_and_all_requires_every_secondary_key(self):
        messages = [item("UserMessageItem", "沙丘 保罗 香料", "u1")]
        for logic in (0, 1, 2, 3):
            result = compile_worldbooks(
                [book([entry(
                    1, key=["沙丘"], keysecondary=["保罗", "香料"],
                    selective=True, selectiveLogic=logic, content=f"logic-{logic}",
                )])],
                messages,
            )
            active = any(p.text == f"logic-{logic}" for p in result.before_character)
            self.assertEqual(active, logic in (0, 3))

    def test_case_sensitive_and_whole_word_options(self):
        messages = [item("UserMessageItem", "I like liking and KING.", "u1")]
        data = book([
            entry(1, key=["king"], content="whole-word", matchWholeWords=True),
            entry(2, key=["King"], content="case-sensitive", caseSensitive=True),
            entry(3, key=["lik"], content="substring", matchWholeWords=False),
        ])
        result = compile_worldbooks([data], messages)
        texts = [p.text for p in result.before_character]
        self.assertIn("whole-word", texts)
        self.assertNotIn("case-sensitive", texts)
        self.assertIn("substring", texts)

    def test_recursive_activation_and_recursion_guards(self):
        data = book([
            entry(1, key=["沙丘"], content="厄拉科斯是沙漠星球"),
            entry(2, key=["厄拉科斯"], content="那里有香料", delayUntilRecursion=True),
            entry(3, key=["香料"], content="香料引来沙虫", delayUntilRecursion=True),
            entry(4, key=["沙虫"], content="递归排除内容", delayUntilRecursion=True, excludeRecursion=True),
        ], recursiveScanning=True)
        result = compile_worldbooks(
            [data], [item("UserMessageItem", "我在看沙丘", "u1")],
            max_recursion_steps=3,
        )
        texts = [p.text for p in result.before_character]
        self.assertIn("厄拉科斯是沙漠星球", texts)
        self.assertIn("那里有香料", texts)
        self.assertIn("香料引来沙虫", texts)
        self.assertNotIn("递归排除内容", texts)

    def test_prevent_recursion_stops_entry_content_from_triggering_more_entries(self):
        data = book([
            entry(1, key=["沙丘"], content="这里提到了香料", preventRecursion=True),
            entry(2, key=["香料"], content="不应递归激活", delayUntilRecursion=True),
        ], recursiveScanning=True)
        result = compile_worldbooks(
            [data], [item("UserMessageItem", "沙丘", "u1")],
            max_recursion_steps=3,
        )
        texts = [p.text for p in result.before_character]
        self.assertIn("这里提到了香料", texts)
        self.assertNotIn("不应递归激活", texts)

    def test_depth_position_role_and_prompt_positions(self):
        data = book([
            entry(1, key=["沙丘"], content="before character", position=0, order=10),
            entry(2, key=["沙丘"], content="after character", position=1, order=20),
            entry(3, key=["沙丘"], content="depth assistant", position=4, depth=2, role=2, order=30),
        ])
        result = compile_worldbooks(
            [data], [item("UserMessageItem", "沙丘", "u1")],
        )
        self.assertEqual([p.text for p in result.before_character], ["before character"])
        self.assertEqual([p.text for p in result.after_character], ["after character"])
        self.assertEqual(result.depth_entries[0].role, "assistant")
        self.assertEqual(result.depth_entries[0].injection_depth, 2)

    def test_unsupported_positions_are_warned_and_not_injected(self):
        data = book([entry(1, key=["沙丘"], content="author note", position=2)])
        result = compile_worldbooks(
            [data], [item("UserMessageItem", "沙丘", "u1")],
        )
        self.assertFalse(result.before_character)
        self.assertTrue(any("position 2 is not supported" in warning for warning in result.warnings))

    def test_recursion_is_off_unless_enabled(self):
        data = book([
            entry(1, key=["沙丘"], content="厄拉科斯"),
            entry(2, key=["厄拉科斯"], content="递归条目", delayUntilRecursion=True),
        ])
        result = compile_worldbooks(
            [data], [item("UserMessageItem", "沙丘", "u1")],
            recursive=False,
        )
        self.assertEqual([p.text for p in result.before_character], ["厄拉科斯"])

    def test_worldbook_budget_and_constant_priority(self):
        data = book([
            entry(1, key=["沙丘"], content="x" * 60, order=999),
            entry(2, constant=True, content="c" * 60, order=1),
        ])
        result = compile_worldbooks(
            [data], [item("UserMessageItem", "沙丘", "u1")], max_chars=100,
        )
        texts = [p.text for p in result.before_character]
        self.assertEqual(texts, ["c" * 60])
        self.assertTrue(any("budget exhausted" in warning for warning in result.warnings))

    def test_shared_budget_prioritizes_constant_across_multiple_books(self):
        first = book([entry(1, key=["沙丘"], content="x" * 60, order=999)], name="character-book")
        second = book([entry(2, constant=True, content="c" * 60, order=1)], name="external-book")
        result = compile_worldbooks(
            [first, second], [item("UserMessageItem", "沙丘", "u1")], max_chars=100,
        )
        self.assertEqual([p.text for p in result.before_character], ["c" * 60])
        self.assertTrue(any("external-book" in value for value in result.activated))

    def test_regex_keys_are_skipped_with_warning(self):
        data = book([entry(1, key=["/.*沙丘.*/"], content="regex should not run")])
        result = compile_worldbooks(
            [data], [item("UserMessageItem", "沙丘", "u1")],
        )
        self.assertFalse(result.before_character)
        self.assertTrue(any("regex keyword skipped for safety" in warning for warning in result.warnings))

    def test_nullable_st_entry_defaults_are_normalized(self):
        data = book([entry(
            1, key=["沙丘"], content="nullable defaults", position=None, depth=None,
            order=None, selectiveLogic=None, role=None, delayUntilRecursion=None,
        )])
        normalized = normalize_worldbook(data)["_normalized_entries"][0]
        self.assertEqual(normalized["position"], 0)
        self.assertEqual(normalized["depth"], 4)
        self.assertEqual(normalized["order"], 100)
        self.assertEqual(normalized["selectiveLogic"], 0)
        self.assertEqual(normalized["_role"], "system")
        self.assertFalse(normalized["delayUntilRecursion"])

    def test_vectorized_entry_is_not_misinterpreted_as_keyword_entry(self):
        data = book([entry(
            1, key=["沙丘"], content="vectorized-only", vectorized=True,
        )])
        result = compile_worldbooks(
            [data], [item("UserMessageItem", "沙丘", "u1")],
        )
        self.assertFalse(result.before_character)
        self.assertTrue(any("vectorized activation is not implemented" in warning for warning in result.warnings))

    def test_unsupported_activation_controls_are_skipped_safely(self):
        data = book([
            entry(1, key=["沙丘"], content="character filtered", characterFilter={"names": ["Other"]}),
            entry(2, key=["沙丘"], content="sticky", sticky=3),
            entry(3, key=["沙丘"], content="@@activate\nforced lore"),
            entry(4, key=["沙丘"], content="persona scan", matchPersonaDescription=True),
        ])
        result = compile_worldbooks(
            [data], [item("UserMessageItem", "沙丘", "u1")],
        )
        self.assertFalse(result.before_character)
        joined = "\n".join(result.warnings)
        self.assertIn("character-filtered entry skipped", joined)
        self.assertIn("timed sticky/cooldown/delay entry skipped", joined)
        self.assertIn("activation decorators are not implemented", joined)
        self.assertIn("unsupported global scan source flag", joined)

    def test_invalid_worldbook_shape_is_rejected(self):
        with self.assertRaises(PresetError):
            normalize_worldbook({"name": "bad", "entries": "not-an-object"})


if __name__ == "__main__":
    unittest.main()
