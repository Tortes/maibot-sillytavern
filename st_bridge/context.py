"""Map compiled SillyTavern prompts onto MaiBot Context Item snapshots.

The adapter only creates ordinary System/User/Assistant message items. Existing
history and multimodal/tool items are copied unchanged. Tool-call turns are kept
atomic when applying depth insertions.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable
from uuid import uuid4

from .preset import CompiledPreset, CompiledPrompt

PLUGIN_ITEM_PREFIX = "stpreset:"
ROLE_TO_ITEM = {
    "system": "SystemMessageItem",
    "user": "UserMessageItem",
    "assistant": "AssistantMessageItem",
}
TAIL_PREFIXES = (
    "你的说话风格可以尝试：",
    "当前时间：",
    "请简短的回复",
    "可以针对问题做出较为详细的评论和说明",
    "【额外回复要求】",
    "【重生成约束】",
    "Current time:",
)


@dataclass(frozen=True)
class AppliedContext:
    items: list[dict[str, Any]]
    warnings: tuple[str, ...]
    inserted: tuple[str, ...]


def _item_text(item: dict[str, Any]) -> str:
    return "\n".join(
        str(part.get("text", ""))
        for part in item.get("parts", [])
        if isinstance(part, dict) and part.get("type") == "text"
    )


def _parse_timestamp(item: dict[str, Any]) -> datetime | None:
    raw = item.get("meta", {}).get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _is_generated_tail(
    item: dict[str, Any],
    anchor_time: datetime | None,
    *,
    reply_reason: str = "",
    reply_reference: str = "",
) -> bool:
    text = _item_text(item).strip()
    if any(text.startswith(prefix) for prefix in TAIL_PREFIXES):
        return True
    if text and (text == reply_reason.strip() or text == reply_reference.strip()):
        return True
    item_time = _parse_timestamp(item)
    if item_time is not None and anchor_time is not None:
        # MaiBot creates its temporary reply instructions immediately before the
        # "当前时间" final user block. Same-second generated items are excluded
        # from ST history depth; old IM messages keep their original timestamps.
        left = item_time.replace(microsecond=0)
        right = anchor_time.replace(microsecond=0)
        if left == right and item.get("item_type") == "UserMessageItem":
            return True
    return False


def _find_history_start(items: list[dict[str, Any]]) -> int:
    index = 0
    while index < len(items) and items[index].get("item_type") == "SystemMessageItem":
        index += 1
    return index


def _find_current_prompt_anchor(items: list[dict[str, Any]]) -> int:
    for index in range(len(items) - 1, -1, -1):
        item = items[index]
        if item.get("item_type") != "UserMessageItem":
            continue
        text = _item_text(item).lstrip()
        if text.startswith("当前时间：") or text.startswith("Current time:"):
            return index
    return len(items)


def _tool_call_id(item: dict[str, Any]) -> str:
    if item.get("item_type") == "FunctionCallItem":
        call = item.get("tool_call")
        if isinstance(call, dict):
            return str(call.get("call_id") or "")
    if item.get("item_type") == "FunctionCallOutputItem":
        return str(item.get("call_id") or "")
    return ""


def _safe_tool_boundary(items: list[dict[str, Any]], boundary: int) -> int:
    """Move a depth insertion before a tool turn if it would split that turn."""
    if boundary <= 0 or boundary >= len(items):
        return boundary
    left = items[boundary - 1]
    right = items[boundary]
    left_turn = (left.get("meta") or {}).get("logical_turn_id")
    right_turn = (right.get("meta") or {}).get("logical_turn_id")
    if left_turn and left_turn == right_turn:
        start = boundary - 1
        while start > 0 and (items[start - 1].get("meta") or {}).get("logical_turn_id") == left_turn:
            start -= 1
        return start

    if right.get("item_type") == "FunctionCallOutputItem":
        call_id = _tool_call_id(right)
        if call_id:
            for index in range(boundary - 1, -1, -1):
                if items[index].get("item_type") == "FunctionCallItem" and _tool_call_id(items[index]) == call_id:
                    start = index
                    turn_id = (items[index].get("meta") or {}).get("logical_turn_id")
                    while start > 0 and turn_id and (items[start - 1].get("meta") or {}).get("logical_turn_id") == turn_id:
                        start -= 1
                    return start
    return boundary


def _new_context_item(prompt: CompiledPrompt) -> dict[str, Any]:
    item_type = ROLE_TO_ITEM[prompt.role]
    item: dict[str, Any] = {
        "item_type": item_type,
        "meta": {
            "item_id": PLUGIN_ITEM_PREFIX + uuid4().hex,
            "logical_turn_id": None,
            "timestamp": datetime.now().astimezone().isoformat(),
        },
        "parts": [{"type": "text", "text": prompt.text}],
    }
    return item


def _new_prefill(text: str) -> dict[str, Any]:
    prompt = CompiledPrompt(
        identifier="assistant_prefill", role="assistant", text=text,
    )
    return _new_context_item(prompt)


def extract_history_macro_values(items: list[dict[str, Any]]) -> dict[str, str]:
    anchor = _find_current_prompt_anchor(items)
    anchor_time = _parse_timestamp(items[anchor]) if anchor < len(items) else None
    user_text = ""
    assistant_text = ""
    last_text = ""
    for item in reversed(items[:anchor]):
        if _is_generated_tail(item, anchor_time):
            continue
        text = _item_text(item).strip()
        if not text:
            continue
        item_type = item.get("item_type")
        if item_type not in ("UserMessageItem", "AssistantMessageItem"):
            continue
        if not last_text:
            last_text = text
        if not user_text and item_type == "UserMessageItem":
            user_text = text
        if not assistant_text and item_type == "AssistantMessageItem":
            assistant_text = text
        if user_text and assistant_text and last_text:
            break
    return {
        "lastmessage": last_text,
        "lastusermessage": user_text,
        "lastcharmessage": assistant_text,
    }


def apply_compiled_preset(
    items: list[dict[str, Any]],
    compiled: CompiledPreset,
    *,
    allow_assistant_prefill: bool = False,
    reply_reason: str = "",
    reply_reference: str = "",
) -> AppliedContext:
    """Insert role-aware preset entries without rewriting existing Context Items."""
    if not isinstance(items, list):
        raise TypeError("MaiBot items must be a list")

    # Remove this plugin's previous injected items before compiling again on retries.
    base = [
        deepcopy(item) for item in items
        if not str((item.get("meta") or {}).get("item_id", "")).startswith(PLUGIN_ITEM_PREFIX)
    ]
    history_start = _find_history_start(base)
    anchor = _find_current_prompt_anchor(base)
    anchor_time = _parse_timestamp(base[anchor]) if anchor < len(base) else None

    history_indices = [
        index for index in range(history_start, anchor)
        if base[index].get("item_type") != "SystemMessageItem"
        and not _is_generated_tail(
            base[index], anchor_time, reply_reason=reply_reason, reply_reference=reply_reference,
        )
    ]

    insertions: dict[int, list[tuple[int, int, dict[str, Any]]]] = {}
    sequence = 0
    inserted: list[str] = []

    def schedule(index: int, prompt: CompiledPrompt, priority: int) -> None:
        nonlocal sequence
        index = max(0, min(index, len(base)))
        new_item = _new_context_item(prompt)
        insertions.setdefault(index, []).append((priority, sequence, new_item))
        sequence += 1
        inserted.append(prompt.identifier)

    # Preserve MaiBot's leading system message as the host-level safety/identity layer.
    for prompt in compiled.before_history:
        schedule(history_start, prompt, 0)

    for prompt in compiled.after_history:
        schedule(anchor, prompt, 2)

    for prompt in compiled.depth_entries:
        depth = max(0, prompt.injection_depth)
        slot = max(0, len(history_indices) - depth)
        if slot >= len(history_indices):
            target = anchor
        else:
            target = history_indices[slot]
        target = _safe_tool_boundary(base, target)
        schedule(target, prompt, 1)

    warnings = list(compiled.warnings)
    if compiled.assistant_prefill:
        if allow_assistant_prefill:
            new_item = _new_prefill(compiled.assistant_prefill)
            insertions.setdefault(len(base), []).append((3, sequence, new_item))
            inserted.append("assistant_prefill")
        else:
            warnings.append("assistant_prefill present but disabled for this binding")

    output: list[dict[str, Any]] = []
    for index in range(len(base) + 1):
        for _, _, item in sorted(insertions.get(index, []), key=lambda value: (value[0], value[1])):
            output.append(item)
        if index < len(base):
            output.append(base[index])

    return AppliedContext(items=output, warnings=tuple(warnings), inserted=tuple(inserted))


__all__ = ["AppliedContext", "apply_compiled_preset", "extract_history_macro_values"]
