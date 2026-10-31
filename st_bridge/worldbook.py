"""Safe SillyTavern World Info / Lorebook importer and bounded activator.

This implements a deliberately small, deterministic subset of ST World Info.
It never executes imported scripts or regular-expression keys.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .preset import CompiledPrompt, PresetError, _expand

MAX_WORLD_BOOK_ENTRIES = 2000
MAX_WORLD_BOOK_CONTENT_CHARS = 20000
MAX_WORLD_BOOK_TOTAL_CHARS = 200000
MAX_SCAN_DEPTH = 1000
MAX_RECURSION_STEPS = 5
ROLE_MAP = {0: "system", 1: "user", 2: "assistant"}
POSITION_BEFORE_CHARACTER = 0
POSITION_AFTER_CHARACTER = 1
POSITION_AT_DEPTH = 4
TAIL_PREFIXES = (
    "你的说话风格可以尝试：",
    "时间：",
    "当前时间：",
    "请简短的回复",
    "可以针对问题做出较为详细的评论和说明",
    "【额外回复要求】",
    "【重生成约束】",
    "Current time:",
    "Time:",
    "当前聊天额外注意事项：",
)


@dataclass(frozen=True)
class WorldbookResult:
    before_character: tuple[CompiledPrompt, ...]
    after_character: tuple[CompiledPrompt, ...]
    depth_entries: tuple[CompiledPrompt, ...]
    warnings: tuple[str, ...]
    activated: tuple[str, ...]


def _read_worldbook_json(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > 8 * 1024 * 1024:
            raise PresetError("Worldbook JSON exceeds 8 MiB")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise PresetError(f"Invalid UTF-8 worldbook JSON: {path.name}") from exc
    if not isinstance(data, dict):
        raise PresetError("Worldbook root must be an object")
    return data


def normalize_worldbook(data: Mapping[str, Any], *, source: str = "worldbook") -> dict[str, Any]:
    """Validate and normalize an exported ST World Info object."""
    if not isinstance(data, Mapping):
        raise PresetError(f"{source}: worldbook root must be an object")
    raw_entries = data.get("entries")
    if isinstance(raw_entries, dict):
        rows = list(raw_entries.items())
    elif isinstance(raw_entries, list):
        rows = [(str(index), value) for index, value in enumerate(raw_entries)]
    else:
        raise PresetError(f"{source}: expected an entries object or array")
    if len(rows) > MAX_WORLD_BOOK_ENTRIES:
        raise PresetError(f"{source}: too many entries (max {MAX_WORLD_BOOK_ENTRIES})")

    for field in ("recursiveScanning", "caseSensitive", "matchWholeWords"):
        if field in data and data[field] is not None and not isinstance(data[field], bool):
            raise PresetError(f"{source}: {field} must be boolean")
    if data.get("maxRecursionSteps") is not None and (
        type(data["maxRecursionSteps"]) is not int
        or not 0 <= data["maxRecursionSteps"] <= MAX_RECURSION_STEPS
    ):
        raise PresetError(f"{source}: maxRecursionSteps is out of range")

    entries: list[dict[str, Any]] = []
    seen_uids: set[str] = set()
    total_chars = 0
    for source_index, (key, raw) in enumerate(rows):
        if not isinstance(raw, dict):
            raise PresetError(f"{source}: entry {key!r} must be an object")
        entry = dict(raw)
        if entry.get("uid") is None:
            entry["uid"] = key
        content = entry.get("content", "")
        if not isinstance(content, str):
            raise PresetError(f"{source}: entry {key!r} content must be text")
        if len(content) > MAX_WORLD_BOOK_CONTENT_CHARS:
            raise PresetError(f"{source}: entry {key!r} content exceeds character limit")
        total_chars += len(content)
        if total_chars > MAX_WORLD_BOOK_TOTAL_CHARS:
            raise PresetError(f"{source}: total worldbook content exceeds character limit")

        for field in ("key", "keysecondary"):
            value = entry.get(field) or []
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise PresetError(f"{source}: entry {key!r} {field} must be a string array")
            entry[field] = [item.strip() for item in value if item.strip()]

        for field in ("disable", "constant", "selective", "useProbability",
                      "caseSensitive", "matchWholeWords", "excludeRecursion", "preventRecursion"):
            if field in entry and entry[field] is not None and not isinstance(entry[field], bool):
                raise PresetError(f"{source}: entry {key!r} {field} must be boolean")

        for field, default, minimum, maximum in (
            ("selectiveLogic", 0, 0, 3),
            ("position", 0, 0, 7),
            ("depth", 4, 0, MAX_SCAN_DEPTH),
            ("order", 100, -100000, 100000),
            ("scanDepth", None, 0, MAX_SCAN_DEPTH),
        ):
            value = entry.get(field, default)
            if value is None and field == "scanDepth":
                continue
            if value is None:
                value = default
            if type(value) is not int or not minimum <= value <= maximum:
                raise PresetError(f"{source}: entry {key!r} has invalid {field}")
            entry[field] = value

        probability = entry.get("probability", 100)
        if probability is not None and (
            isinstance(probability, bool) or not isinstance(probability, (int, float))
            or not 0 <= probability <= 100
        ):
            raise PresetError(f"{source}: entry {key!r} probability must be between 0 and 100")
        entry["probability"] = 100 if probability is None else float(probability)

        delay = entry.get("delayUntilRecursion", False)
        if delay is None:
            delay = False
        if not isinstance(delay, (bool, int)) or isinstance(delay, float):
            raise PresetError(f"{source}: entry {key!r} delayUntilRecursion must be boolean or integer")
        if isinstance(delay, int) and not isinstance(delay, bool) and not 0 <= delay <= MAX_RECURSION_STEPS:
            raise PresetError(f"{source}: entry {key!r} delayUntilRecursion is out of range")

        role = entry.get("role", 0)
        if role is None:
            role = 0
        if isinstance(role, str):
            if role.lower() not in ("system", "user", "assistant"):
                raise PresetError(f"{source}: entry {key!r} has unsupported role")
            entry["_role"] = role.lower()
        elif type(role) is int and role in ROLE_MAP:
            entry["_role"] = ROLE_MAP[role]
        else:
            raise PresetError(f"{source}: entry {key!r} has unsupported role")
        entry["_source_uid"] = str(entry.get("uid", key))
        entry["_source_index"] = source_index
        if entry["_source_uid"] in seen_uids:
            raise PresetError(f"{source}: duplicate entry uid {entry['_source_uid']!r}")
        seen_uids.add(entry["_source_uid"])
        entry["_source"] = str(data.get("name") or source)
        entries.append(entry)

    normalized = dict(data)
    normalized["_normalized_entries"] = entries
    return normalized


def load_worldbook(path: Path) -> dict[str, Any]:
    """Load a standalone SillyTavern World Info JSON export."""
    return normalize_worldbook(_read_worldbook_json(path), source=path.name)


def _item_text(item: Mapping[str, Any]) -> str:
    parts = item.get("parts", [])
    if not isinstance(parts, list):
        return ""
    return "\n".join(
        str(part.get("text", ""))
        for part in parts
        if isinstance(part, dict) and part.get("type") == "text"
    ).strip()


def extract_scan_messages(
    items: Sequence[Mapping[str, Any]], *, reply_reason: str = "", reply_reference: str = "",
) -> list[str]:
    """Return chronological user/assistant text, excluding MaiBot-generated tail prompts."""
    messages: list[str] = []
    excluded_exact = {reply_reason.strip(), reply_reference.strip()} - {""}
    for item in items:
        if item.get("item_type") not in ("UserMessageItem", "AssistantMessageItem"):
            continue
        text = _item_text(item)
        if not text or text in excluded_exact:
            continue
        if any(text.lstrip().startswith(prefix) for prefix in TAIL_PREFIXES):
            continue
        messages.append(text)
    return messages


def _matches(text: str, key: str, *, case_sensitive: bool, whole_words: bool) -> bool:
    key = key.strip()
    if not key:
        return False
    # ST accepts regex keys, but imported regular expressions can cause ReDoS.
    # This bridge intentionally skips them rather than evaluating untrusted code.
    if len(key) >= 2 and key.startswith("/") and key.rfind("/") > 0:
        return False
    if not case_sensitive:
        text, key = text.casefold(), key.casefold()
    if whole_words and len(key.split()) == 1:
        # ASCII word boundaries mirror ST's punctuation-aware matching and
        # deliberately leave CJK characters as non-word boundaries.
        pattern = r"(?<![A-Za-z0-9_])" + re.escape(key) + r"(?![A-Za-z0-9_])"
        return re.search(pattern, text, flags=re.ASCII) is not None
    return key in text


def _entry_matches(
    entry: Mapping[str, Any],
    scan_text: str,
    *,
    default_case_sensitive: bool,
    default_whole_words: bool,
    macro_values: Mapping[str, str],
    character: Mapping[str, Any],
) -> tuple[bool, str | None]:
    case_sensitive = entry.get("caseSensitive")
    if case_sensitive is None:
        case_sensitive = default_case_sensitive
    whole_words = entry.get("matchWholeWords")
    if whole_words is None:
        whole_words = default_whole_words

    extra: list[str] = []
    if entry.get("matchCharacterDescription"):
        extra.append(str(character.get("description") or ""))
    if entry.get("matchCharacterPersonality"):
        extra.append(str(character.get("personality") or ""))
    if entry.get("matchScenario"):
        extra.append(str(character.get("scenario") or ""))
    haystack = scan_text + ("\n" + "\n".join(extra) if extra else "")

    primary: list[str] = []
    for raw_key in entry.get("key", []):
        expanded, error = _expand(raw_key, macro_values)
        if error:
            return False, f"entry {entry['_source_uid']}: unsupported keyword macro ({error})"
        if expanded and expanded.strip():
            if len(expanded) >= 2 and expanded.startswith("/") and expanded.rfind("/") > 0:
                return False, f"entry {entry['_source_uid']}: regex keyword skipped for safety"
            primary.append(expanded.strip())
    if not primary or not any(
        _matches(haystack, key, case_sensitive=bool(case_sensitive), whole_words=bool(whole_words))
        for key in primary
    ):
        return False, None

    secondary = entry.get("keysecondary", [])
    if not entry.get("selective") or not secondary:
        return True, None

    secondary_matches: list[bool] = []
    for raw_key in secondary:
        expanded, error = _expand(raw_key, macro_values)
        if error:
            return False, f"entry {entry['_source_uid']}: unsupported secondary-key macro ({error})"
        if expanded and expanded.strip():
            if len(expanded) >= 2 and expanded.startswith("/") and expanded.rfind("/") > 0:
                return False, f"entry {entry['_source_uid']}: regex secondary keyword skipped for safety"
            secondary_matches.append(
                _matches(haystack, expanded.strip(), case_sensitive=bool(case_sensitive),
                         whole_words=bool(whole_words))
            )
    if not secondary_matches:
        return True, None

    logic = entry.get("selectiveLogic", 0)
    if logic == 0:       # AND_ANY: at least one secondary key
        return any(secondary_matches), None
    if logic == 1:       # NOT_ALL: at least one secondary key is absent
        return not all(secondary_matches), None
    if logic == 2:       # NOT_ANY: no secondary key is present
        return not any(secondary_matches), None
    if logic == 3:       # AND_ALL: every secondary key is present
        return all(secondary_matches), None
    return False, f"entry {entry['_source_uid']}: unsupported selectiveLogic {logic}"


def compile_worldbooks(
    books: Sequence[Mapping[str, Any]],
    items: Sequence[Mapping[str, Any]],
    *,
    character: Mapping[str, Any] | None = None,
    user_name: str = "群友",
    char_name: str = "",
    macro_values: Mapping[str, str] | None = None,
    scan_depth: int = 2,
    max_chars: int = 6000,
    recursive: bool = False,
    max_recursion_steps: int = 3,
    case_sensitive: bool = False,
    match_whole_words: bool = False,
    reply_reason: str = "",
    reply_reference: str = "",
) -> WorldbookResult:
    """Activate a bounded safe subset of ST World Info entries for this request."""
    if not 0 <= scan_depth <= MAX_SCAN_DEPTH:
        raise ValueError(f"scan_depth must be between 0 and {MAX_SCAN_DEPTH}")
    if not 100 <= max_chars <= 50000:
        raise ValueError("worldbook max_chars must be between 100 and 50000")
    max_recursion_steps = max(0, min(int(max_recursion_steps), MAX_RECURSION_STEPS))
    char = character or {}
    macro_values = {str(k).lower(): str(v) for k, v in (macro_values or {}).items()}
    macro_values.setdefault("char", char_name or str(char.get("name") or "角色"))
    macro_values.setdefault("user", user_name)
    macro_values.setdefault("description", str(char.get("description") or ""))
    macro_values.setdefault("personality", str(char.get("personality") or ""))
    macro_values.setdefault("scenario", str(char.get("scenario") or ""))
    macro_values.setdefault("mesexamples", str(char.get("mes_example") or ""))

    messages = extract_scan_messages(items, reply_reason=reply_reason, reply_reference=reply_reference)
    warnings: list[str] = []
    before_entries: list[CompiledPrompt] = []
    after_entries: list[CompiledPrompt] = []
    depth_entries: list[CompiledPrompt] = []
    included: list[str] = []
    total_used_chars = 0
    for book_index, raw_book in enumerate(books):
        source = str(raw_book.get("name") or f"worldbook-{book_index + 1}")
        try:
            book = normalize_worldbook(raw_book, source=source)
        except PresetError as exc:
            warnings.append(str(exc))
            continue
        book_entries = book["_normalized_entries"]
        candidates: list[tuple[dict[str, Any], int, str]] = []
        book_scan_depth = book.get("scanDepth")
        if book_scan_depth is not None and (
            type(book_scan_depth) is not int or not 0 <= book_scan_depth <= MAX_SCAN_DEPTH
        ):
            warnings.append(f"{source}: invalid book scanDepth; using binding default")
            book_scan_depth = None
        book_recursive = book.get("recursiveScanning")
        use_recursive = bool(book_recursive) if isinstance(book_recursive, bool) else recursive
        book_steps = max_recursion_steps
        if type(book.get("maxRecursionSteps")) is int:
            book_steps = max(0, min(book["maxRecursionSteps"], MAX_RECURSION_STEPS))
        if not use_recursive:
            book_steps = 0

        for entry_index, entry in enumerate(book_entries):
            if entry.get("disable") is True:
                continue
            if entry.get("group"):
                warnings.append(f"{source} entry {entry['_source_uid']}: inclusion-group scoring is not implemented")
            if entry.get("vectorized"):
                warnings.append(f"{source} entry {entry['_source_uid']}: vectorized activation is not implemented; entry skipped")
                continue
            if entry.get("position", 0) not in (
                POSITION_BEFORE_CHARACTER, POSITION_AFTER_CHARACTER, POSITION_AT_DEPTH,
            ):
                warnings.append(
                    f"{source} entry {entry['_source_uid']}: ST position {entry.get('position')} "
                    "is not supported yet; entry was not injected"
                )
                continue
            candidates.append((entry, entry_index, source))

        activated: dict[tuple[str, str], dict[str, Any]] = {}
        recursion_text: list[str] = []
        for recursion_level in range(book_steps + 1):
            newly_activated: list[dict[str, Any]] = []
            scan_parts_by_depth: dict[int, str] = {}
            for entry, entry_index, entry_source in candidates:
                identity = (entry_source, entry["_source_uid"])
                if identity in activated:
                    continue
                delay = entry.get("delayUntilRecursion", False)
                delay_level = int(delay) if isinstance(delay, int) and not isinstance(delay, bool) else (1 if delay else 0)
                if recursion_level < delay_level:
                    continue
                if recursion_level > 0 and entry.get("excludeRecursion"):
                    continue
                if entry.get("constant") is True:
                    matched, warning = (recursion_level == 0), None
                else:
                    entry_depth = entry.get("scanDepth")
                    if entry_depth is None:
                        entry_depth = book_scan_depth if book_scan_depth is not None else scan_depth
                    if entry_depth not in scan_parts_by_depth:
                        selected = messages[-entry_depth:] if entry_depth else []
                        scan_parts_by_depth[entry_depth] = "\n".join(selected + recursion_text)
                    scan_text = scan_parts_by_depth[entry_depth]
                    matched, warning = _entry_matches(
                        entry, scan_text,
                        default_case_sensitive=bool(book.get("caseSensitive", case_sensitive)),
                        default_whole_words=bool(book.get("matchWholeWords", match_whole_words)),
                        macro_values=macro_values, character=char,
                    )
                if warning:
                    warnings.append(f"{entry_source}: {warning}")
                if not matched:
                    continue
                if entry.get("useProbability") and random.random() * 100 > entry.get("probability", 100):
                    continue
                activated[identity] = entry
                newly_activated.append(entry)

            if not newly_activated:
                break
            if recursion_level < book_steps:
                for entry in newly_activated:
                    if not entry.get("preventRecursion"):
                        content, error = _expand(str(entry.get("content") or ""), macro_values)
                        if error:
                            warnings.append(f"{source} entry {entry['_source_uid']}: {error}; content skipped")
                            continue
                        if content:
                            recursion_text.append(content)

        # Select entries within the request-wide character budget. Constants and
        # higher-order entries win budget first, matching ST's priority policy.
        ordered_for_budget = sorted(
            activated.items(),
            key=lambda pair: (
                0 if pair[1].get("constant") else 1,
                -int(pair[1].get("order", 100)),
                int(pair[1].get("_source_index", 0)),
            ),
        )
        selected_entries: list[dict[str, Any]] = []
        for _, entry in ordered_for_budget:
            content, error = _expand(str(entry.get("content") or ""), macro_values)
            if error:
                warnings.append(f"{source} entry {entry['_source_uid']}: {error}; content skipped")
                continue
            if not content or not content.strip():
                continue
            if total_used_chars + len(content) > max_chars:
                warnings.append(f"Worldbook character budget exhausted; skipped entry {entry['_source_uid']}")
                continue
            total_used_chars += len(content)
            entry["_compiled_content"] = content.strip()
            selected_entries.append(entry)

        # ST processes high order first and unshifts each item, yielding low-to-high
        # order in the final prompt. Keep stable source order for ties.
        selected_entries.sort(key=lambda entry: (int(entry.get("order", 100)), int(entry.get("_source_index", 0))))
        for entry in selected_entries:
            uid = entry["_source_uid"]
            identifier = f"worldbook:{source}:{uid}"
            position = entry.get("position", 0)
            content = entry["_compiled_content"]
            if position in (POSITION_BEFORE_CHARACTER, POSITION_AFTER_CHARACTER):
                prompt = CompiledPrompt(
                    identifier=identifier, role="system", text=content,
                    injection_position=0, injection_depth=4, injection_order=int(entry.get("order", 100)),
                )
                if position == POSITION_BEFORE_CHARACTER:
                    before_entries.append(prompt)
                else:
                    after_entries.append(prompt)
            elif position == POSITION_AT_DEPTH:
                depth_entries.append(CompiledPrompt(
                    identifier=identifier, role=entry.get("_role", "system"), text=content,
                    injection_position=1, injection_depth=int(entry.get("depth", 4)),
                    injection_order=int(entry.get("order", 100)),
                ))
            included.append(identifier)

    return WorldbookResult(
        before_character=tuple(before_entries),
        after_character=tuple(after_entries),
        depth_entries=tuple(sorted(depth_entries, key=lambda item: item.injection_order)),
        warnings=tuple(dict.fromkeys(warnings)),
        activated=tuple(included),
    )


__all__ = [
    "WorldbookResult", "compile_worldbooks", "extract_scan_messages",
    "load_worldbook", "normalize_worldbook",
]
