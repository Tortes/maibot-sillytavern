from __future__ import annotations
import unittest

from st_bridge.context import apply_compiled_preset
from st_bridge.preset import compile_preset


def meta(item_id, timestamp="2026-10-30T10:00:00+08:00", turn=None):
    return {"item_id": item_id, "logical_turn_id": turn, "timestamp": timestamp}


def text_item(item_type, item_id, text, timestamp="2026-10-30T10:00:00+08:00", turn=None):
    return {
        "item_type": item_type,
        "meta": meta(item_id, timestamp, turn),
        "parts": [{"type": "text", "text": text}],
    }


def base_items():
    now = "2026-10-31T13:57:00+08:00"
    return [
        text_item("SystemMessageItem", "sys", "MaiBot host prompt"),
        text_item("UserMessageItem", "u1", "昨晚看了电影"),
        text_item("AssistantMessageItem", "a1", "哪一部？"),
        text_item("UserMessageItem", "u2", "沙丘"),
        text_item("UserMessageItem", "tail-style", "你的说话风格可以尝试：自然简短", now),
        text_item("UserMessageItem", "final", "当前时间：2026-10-31 13:57:00", now),
    ]


class ContextTests(unittest.TestCase):
    def make_compiled(self, depth=1):
        preset = {
            "prompts": [
                {"identifier": "before", "role": "system", "content": "角色基础设定"},
                {"identifier": "chatHistory", "role": "system", "marker": True},
                {"identifier": "depth", "role": "assistant", "content": "记住刚才的对话", "injection_position": 1, "injection_depth": depth, "injection_order": 3},
                {"identifier": "after-user", "role": "user", "content": "这是额外的背景"},
                {"identifier": "after-assistant", "role": "assistant", "content": "我会保持角色口吻"},
            ],
            "prompt_order": [{
                "character_id": 100001,
                "order": [
                    {"identifier": "before", "enabled": True},
                    {"identifier": "chatHistory", "enabled": True},
                    {"identifier": "depth", "enabled": True},
                    {"identifier": "after-user", "enabled": True},
                    {"identifier": "after-assistant", "enabled": True},
                ],
            }],
        }
        return compile_preset(preset)

    def test_roles_before_after_and_depth(self):
        original = base_items()
        applied = apply_compiled_preset(original, self.make_compiled())
        result = applied.items
        types = [item["item_type"] for item in result]
        texts = [item.get("parts", [{}])[0].get("text", "") for item in result]
        self.assertEqual(texts[0], "MaiBot host prompt")
        self.assertEqual(texts[1], "角色基础设定")
        self.assertLess(texts.index("昨晚看了电影"), texts.index("哪一部？"))
        self.assertLess(texts.index("哪一部？"), texts.index("记住刚才的对话"))
        self.assertLess(texts.index("记住刚才的对话"), texts.index("沙丘"))
        self.assertLess(texts.index("沙丘"), texts.index("这是额外的背景"))
        self.assertLess(texts.index("这是额外的背景"), texts.index("我会保持角色口吻"))
        self.assertLess(texts.index("我会保持角色口吻"), texts.index("当前时间：2026-10-31"))
        self.assertEqual(types[texts.index("这是额外的背景")], "UserMessageItem")
        self.assertEqual(types[texts.index("我会保持角色口吻")], "AssistantMessageItem")
        self.assertEqual(len(result), len(original) + 5)

    def test_depth_zero_goes_to_history_end(self):
        applied = apply_compiled_preset(base_items(), self.make_compiled(depth=0))
        texts = [item.get("parts", [{}])[0].get("text", "") for item in applied.items]
        self.assertLess(texts.index("沙丘"), texts.index("记住刚才的对话"))
        self.assertLess(texts.index("记住刚才的对话"), texts.index("当前时间：2026-10-31"))

    def test_tool_call_turn_is_not_split(self):
        items = [
            text_item("SystemMessageItem", "sys", "host"),
            text_item("AssistantMessageItem", "a-call", "调用工具", turn="turn-1"),
            {
                "item_type": "FunctionCallItem",
                "meta": meta("call", turn="turn-1"),
                "tool_call": {"call_id": "call-1", "func_name": "search", "args": {}, "extra_content": None},
            },
            {
                "item_type": "FunctionCallOutputItem",
                "meta": meta("output", turn="turn-1"),
                "call_id": "call-1", "output": "结果", "success": True, "tool_name": "search",
            },
            text_item("UserMessageItem", "u2", "后来又聊了别的"),
            text_item("UserMessageItem", "final", "当前时间：2026-10-31 13:57:00", "2026-10-31T13:57:00+08:00"),
        ]
        preset = {
            "prompts": [
                {"identifier": "chatHistory", "marker": True},
                {"identifier": "depth", "role": "system", "content": "深度设定", "injection_position": 1, "injection_depth": 2},
            ],
            "prompt_order": [{"character_id": 100001, "order": [
                {"identifier": "chatHistory", "enabled": True},
                {"identifier": "depth", "enabled": True},
            ]}],
        }
        compiled = compile_preset(preset)
        result = apply_compiled_preset(items, compiled).items
        ids = [item["meta"]["item_id"] for item in result]
        depth_index = next(i for i, item in enumerate(result) if item.get("parts", [{}])[0].get("text") == "深度设定")
        self.assertLess(depth_index, ids.index("a-call"))
        self.assertLess(ids.index("call"), ids.index("output"))

    def test_inserted_items_have_valid_unique_metadata(self):
        result = apply_compiled_preset(base_items(), self.make_compiled()).items
        inserted = [item for item in result if item["meta"]["item_id"].startswith("stpreset:")]
        ids = [item["meta"]["item_id"] for item in inserted]
        self.assertEqual(len(ids), len(set(ids)))
        for item in inserted:
            self.assertIsNone(item["meta"]["logical_turn_id"])
            self.assertTrue(item["meta"]["timestamp"])
            self.assertTrue(item["parts"][0]["text"])

    def test_prefill_is_opt_in(self):
        preset = {"prompts": [{"identifier": "p", "content": "基础"}], "assistant_prefill": "阿澄："}
        compiled = compile_preset(preset)
        off = apply_compiled_preset(base_items(), compiled)
        self.assertTrue(any("disabled" in warning for warning in off.warnings))
        self.assertFalse(any(item["meta"]["item_id"].startswith("stpreset:") and item["item_type"] == "AssistantMessageItem" for item in off.items))
        on = apply_compiled_preset(base_items(), compiled, allow_assistant_prefill=True)
        self.assertEqual(on.items[-1]["item_type"], "AssistantMessageItem")
        self.assertEqual(on.items[-1]["parts"][0]["text"], "阿澄：")

    def test_reapplication_does_not_duplicate(self):
        original = base_items()
        first = apply_compiled_preset(original, self.make_compiled())
        second = apply_compiled_preset(first.items, self.make_compiled())
        first_ids = [x["meta"]["item_id"] for x in first.items if x["meta"]["item_id"].startswith("stpreset:")]
        second_ids = [x["meta"]["item_id"] for x in second.items if x["meta"]["item_id"].startswith("stpreset:")]
        self.assertEqual(len(first_ids), len(second_ids))
        self.assertEqual(len(second.items), len(first.items))

if __name__ == "__main__":
    unittest.main()
