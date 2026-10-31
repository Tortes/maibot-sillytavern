"""Deterministic SillyTavern Chat Completion preset compiler.

This module deliberately implements a safe subset of Tavern macros. It never
executes JavaScript, imported regex scripts, or arbitrary preset code.
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_PROMPTS = 2000
MAX_OUTPUT_CHARS = 20000
MACRO_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
SUPPORTED_MACROS = {
    "char", "user", "description", "personality", "scenario", "mesexamples",
    "newline", "noop", "lastmessage", "lastusermessage", "lastcharmessage",
}
MARKER_FIELDS = {
    "chardescription": "description", "charpersonality": "personality",
    "scenario": "scenario", "dialogueexamples": "mesexamples",
    "description": "description", "personality": "personality",
}

class PresetError(ValueError):
    """Raised for malformed or unsupported resource containers."""

@dataclass(frozen=True)
class Preview:
    text: str
    warnings: tuple[str, ...]
    included: tuple[str, ...]

@dataclass(frozen=True)
class CompiledPrompt:
    identifier: str
    role: str
    text: str
    injection_position: int = 0
    injection_depth: int = 4
    injection_order: int = 100

@dataclass(frozen=True)
class CompiledPreset:
    before_history: tuple[CompiledPrompt, ...]
    after_history: tuple[CompiledPrompt, ...]
    depth_entries: tuple[CompiledPrompt, ...]
    assistant_prefill: str
    warnings: tuple[str, ...]
    included: tuple[str, ...]
    has_chat_history_marker: bool


def _read_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise PresetError(f"JSON exceeds {MAX_JSON_BYTES} bytes: {path.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise PresetError(f"Invalid UTF-8 JSON: {path.name}") from exc
    if not isinstance(data, dict):
        raise PresetError("Root JSON must be an object")
    return data


def safe_resource_path(resources: Path, filename: str) -> Path:
    """Reject absolute paths, traversal, and symlinks escaping resources/."""
    if (not filename or filename.startswith(".") or Path(filename).name != filename
            or not filename.lower().endswith(".json")):
        raise PresetError("Resource must be a single JSON filename within resources/")
    base = resources.resolve()
    file = (base / filename).resolve()
    if not file.is_relative_to(base):
        raise PresetError("Resource path leaves resources/")
    if not file.is_file():
        raise PresetError(f"Resource not found: {filename}")
    return file


def _unwrap_preset(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("format") == "dsh-preset-enhance":
        preset = data.get("preset", {}).get("data")
        if not isinstance(preset, dict):
            raise PresetError("Missing preset.data in DSH share file")
        return preset
    return data


def load_preset(path: Path) -> dict[str, Any]:
    data = _unwrap_preset(_read_json(path))
    prompts = data.get("prompts")
    if not isinstance(prompts, list) or not prompts or len(prompts) > MAX_PROMPTS:
        raise PresetError(f"Expected 1–{MAX_PROMPTS} prompts in ST Chat Completion JSON")
    seen: set[str] = set()
    for prompt in prompts:
        if not isinstance(prompt, dict) or not isinstance(prompt.get("identifier"), str) or not prompt["identifier"]:
            raise PresetError("Each prompt needs a non-empty string identifier")
        if prompt["identifier"] in seen:
            raise PresetError(f"Duplicate prompt identifier: {prompt['identifier']}")
        seen.add(prompt["identifier"])
        if prompt.get("content") is not None and not isinstance(prompt["content"], str):
            raise PresetError(f"Prompt content must be text: {prompt['identifier']}")
        if prompt.get("role") is not None and prompt["role"] not in ("system", "user", "assistant", "model"):
            raise PresetError(f"Unsupported prompt role: {prompt['identifier']}")
        if prompt.get("enabled") is not None and not isinstance(prompt["enabled"], bool):
            raise PresetError(f"Prompt enabled must be boolean: {prompt['identifier']}")
        position = prompt.get("injection_position")
        if position is not None and (type(position) is not int or position not in (0, 1)):
            raise PresetError(f"Invalid injection_position: {prompt['identifier']}")
        depth = prompt.get("injection_depth")
        if depth is not None and (type(depth) is not int or depth < 0):
            raise PresetError(f"Invalid injection_depth: {prompt['identifier']}")
        order = prompt.get("injection_order")
        if order is not None and type(order) is not int:
            raise PresetError(f"Invalid injection_order: {prompt['identifier']}")
        trigger = prompt.get("injection_trigger")
        if trigger is not None and (not isinstance(trigger, list) or any(not isinstance(x, str) for x in trigger)):
            raise PresetError(f"Invalid injection_trigger: {prompt['identifier']}")
    if data.get("prompt_order") is not None and not isinstance(data["prompt_order"], list):
        raise PresetError("prompt_order must be an array")
    for group in data.get("prompt_order") or []:
        if not isinstance(group, dict) or not isinstance(group.get("order"), list):
            raise PresetError("prompt_order group must contain an order array")
        order_seen: set[str] = set()
        for entry in group["order"]:
            if (not isinstance(entry, dict) or not isinstance(entry.get("identifier"), str)
                    or not isinstance(entry.get("enabled"), bool) or entry["identifier"] in order_seen):
                raise PresetError("prompt_order entry is invalid or duplicated")
            order_seen.add(entry["identifier"])
    if data.get("assistant_prefill") is not None and not isinstance(data["assistant_prefill"], str):
        raise PresetError("assistant_prefill must be text")
    return data


def load_character(path: Path) -> dict[str, str]:
    raw = _read_json(path)
    source = raw.get("data", raw)
    if not isinstance(source, dict):
        raise PresetError("Character data must be an object")
    keys = ("name", "description", "personality", "scenario", "mes_example")
    out = {key: str(source.get(key) or "") for key in keys}
    if source.get("character_book") or raw.get("character_book"):
        out["_has_character_book"] = "true"
    return out


def _order(preset: Mapping[str, Any], character_id: str | int | None = None) -> list[dict[str, Any]]:
    groups = preset.get("prompt_order") or []
    if groups:
        if character_id is None:
            selected = next((g for g in groups if str(g.get("character_id")) == "100001"), groups[0])
        else:
            selected = next((g for g in groups if str(g.get("character_id")) == str(character_id)), None)
            if selected is None:
                raise PresetError(f"prompt_order for character_id={character_id!r} not found")
        entries = selected.get("order", [])
        if not isinstance(entries, list):
            raise PresetError("Invalid prompt_order entries")
        return entries
    return [{"identifier": p["identifier"], "enabled": p.get("enabled", True)} for p in preset["prompts"]]


def _expand(text: str, values: Mapping[str, str]) -> tuple[str | None, str | None]:
    unknown = {m.group(1).strip() for m in MACRO_RE.finditer(text)
               if m.group(1).strip().lower() not in SUPPORTED_MACROS}
    if unknown:
        return None, "Unsupported macro(s): " + ", ".join(sorted(unknown))
    def replace(match: re.Match[str]) -> str:
        name = match.group(1).strip().lower()
        if name == "newline":
            return "\n"
        if name == "noop":
            return ""
        return values.get(name, "")
    expanded = MACRO_RE.sub(replace, text)
    if len(expanded) > MAX_OUTPUT_CHARS:
        return None, f"Expanded prompt exceeds {MAX_OUTPUT_CHARS} characters"
    return expanded, None


def compile_preset(
    preset: Mapping[str, Any], *, character: Mapping[str, str] | None = None,
    user_name: str = "群友", char_name: str = "", character_id: str | int | None = None,
    trigger: str = "normal", markers: Mapping[str, str] | None = None,
    macro_values: Mapping[str, str] | None = None, max_chars: int = MAX_OUTPUT_CHARS,
) -> CompiledPreset:
    """Compile Tavern prompts into role-aware entries with before/after/depth placement.

    chatHistory is a boundary marker. Entries before it go before host history;
    entries after it go after host history. injection_position=1 targets history
    by message depth. Imported scripts are never executed.
    """
    char = character or {}
    values = {
        "char": char_name or str(char.get("name") or "角色"), "user": user_name,
        "description": str(char.get("description") or ""), "personality": str(char.get("personality") or ""),
        "scenario": str(char.get("scenario") or ""), "mesexamples": str(char.get("mes_example") or ""),
        "lastmessage": "", "lastusermessage": "", "lastcharmessage": "",
    }
    if macro_values:
        values.update({str(k).lower(): str(v) for k, v in macro_values.items()})
    marker_values = {
        "charDescription": values["description"], "charPersonality": values["personality"],
        "scenario": values["scenario"], "dialogueExamples": values["mesexamples"],
    }
    if markers:
        marker_values.update({str(k): str(v) for k, v in markers.items()})
    warnings: list[str] = []
    if char.get("_has_character_book"):
        warnings.append("Character book exists but lorebook matching is not implemented")
    extensions = preset.get("extensions") or {}
    if isinstance(extensions, dict) and extensions.get("regex_scripts"):
        warnings.append("regex_scripts are preserved as data, but never executed")
    if isinstance(extensions, dict) and extensions.get("regex"):
        warnings.append("Prompt regex rules are not implemented in this version")
    by_id = {p["identifier"]: p for p in preset["prompts"]}
    before: list[CompiledPrompt] = []
    after: list[CompiledPrompt] = []
    depth_entries: list[CompiledPrompt] = []
    included: list[str] = []
    has_history = False
    total_chars = 0
    for order_index, entry in enumerate(_order(preset, character_id)):
        if not isinstance(entry, dict) or not isinstance(entry.get("identifier"), str):
            warnings.append("Skipped malformed order entry")
            continue
        identifier = entry["identifier"]
        if not entry.get("enabled", True):
            continue
        prompt = by_id.get(identifier)
        if prompt is None:
            warnings.append(f"Missing referenced prompt: {identifier}")
            continue
        if prompt.get("enabled") is False and not preset.get("prompt_order"):
            continue
        if identifier == "chatHistory":
            has_history = True
            continue
        prompt_trigger = prompt.get("injection_trigger") or []
        if prompt_trigger and trigger not in prompt_trigger:
            continue
        role = str(prompt.get("role") or "system").lower()
        if role == "model":
            role = "assistant"
        if role not in ("system", "user", "assistant"):
            warnings.append(f"Unsupported role skipped: {identifier} ({role})")
            continue
        if prompt.get("marker") is True:
            text = marker_values.get(identifier, "")
            if not text:
                warnings.append(f"Marker has no supplied content: {identifier}")
                continue
        else:
            text = prompt.get("content") or ""
            if not isinstance(text, str):
                warnings.append(f"Prompt content not text: {identifier}")
                continue
        expanded, error = _expand(text, values)
        if error:
            warnings.append(f"{identifier}: {error}; prompt skipped")
            continue
        if not expanded or not expanded.strip():
            continue
        if total_chars + len(expanded) > max_chars:
            warnings.append(f"Prompt character budget exhausted; skipped: {identifier}")
            continue
        position = prompt.get("injection_position", 0)
        compiled = CompiledPrompt(
            identifier=identifier, role=role, text=expanded.strip(),
            injection_position=position, injection_depth=prompt.get("injection_depth", 4),
            injection_order=prompt.get("injection_order", 100),
        )
        if position == 1:
            depth_entries.append(compiled)
        elif has_history:
            after.append(compiled)
        else:
            before.append(compiled)
        included.append(identifier)
        total_chars += len(expanded)
    prefill = ""
    raw_prefill = preset.get("assistant_prefill") or ""
    if raw_prefill:
        prefill, error = _expand(raw_prefill, values)
        if error:
            warnings.append(f"assistant_prefill: {error}")
            prefill = ""
        else:
            prefill = prefill.strip()
            total_chars += len(prefill)
            if total_chars > max_chars:
                warnings.append("assistant_prefill exceeds prompt character budget")
                prefill = ""
    depth_entries.sort(key=lambda item: item.injection_order)
    return CompiledPreset(
        before_history=tuple(before), after_history=tuple(after), depth_entries=tuple(depth_entries),
        assistant_prefill=prefill, warnings=tuple(warnings), included=tuple(included),
        has_chat_history_marker=has_history,
    )


def build_overlay(
    preset: Mapping[str, Any], *, character: Mapping[str, str] | None = None,
    user_name: str = "群友", char_name: str = "", max_chars: int = MAX_OUTPUT_CHARS,
) -> Preview:
    """Compatibility wrapper for the original flattened CLI preview."""
    compiled = compile_preset(
        preset, character=character, user_name=user_name, char_name=char_name, max_chars=max_chars
    )
    blocks = [p.text for p in compiled.before_history + compiled.after_history]
    blocks.extend(p.text for p in compiled.depth_entries)
    if compiled.assistant_prefill:
        blocks.append(compiled.assistant_prefill)
    return Preview(text="\n\n".join(blocks), warnings=compiled.warnings, included=compiled.included)
