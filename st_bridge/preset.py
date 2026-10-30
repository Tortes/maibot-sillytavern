"""Limited, deterministic ST Chat Completion preset compiler for MaiBot overlay mode.

No eval, no regex execution from files, no arbitrary script processing. This is
an independent MVP, not a source-level port of DSH Preset Enhance.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_PROMPTS = 500
MAX_OUTPUT_CHARS = 20000
MACRO_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
SUPPORTED_MACROS = {
    "char", "user", "description", "personality", "scenario", "mesexamples"
}
# Only markers that can be mapped from basic exported card JSON are used.
MARKER_FIELDS = {
    "chardescription": "description", "charpersonality": "personality",
    "scenario": "scenario", "dialogueexamples": "mes_examples",
}

class PresetError(ValueError):
    """Raised for malformed or unsupported resource container."""

@dataclass(frozen=True)
class Preview:
    text: str
    warnings: tuple[str, ...]
    included: tuple[str, ...]


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
    """Reject absolute paths, traversal, and symlinks escaping resource directory."""
    if not filename or filename.startswith(".") or Path(filename).name != filename or not filename.lower().endswith(".json"):
        raise PresetError("Resource must be a single JSON filename within resources/")
    base = resources.resolve()
    file = (base / filename).resolve()
    if not file.is_relative_to(base):
        raise PresetError("Resource path leaves resources/")
    if not file.is_file():
        raise PresetError(f"Resource not found: {filename}")
    return file


def load_preset(path: Path) -> dict[str, Any]:
    data = _read_json(path)
    if data.get("format") == "dsh-preset-enhance":
        preset = data.get("preset", {}).get("data")
        if not isinstance(preset, dict):
            raise PresetError("Missing preset.data in DSH share file")
        data = preset
    prompts = data.get("prompts")
    if not isinstance(prompts, list) or not prompts or len(prompts) > MAX_PROMPTS:
        raise PresetError("Expected 1–500 prompts in ST Chat Completion JSON")
    seen = set()
    for p in prompts:
        if not isinstance(p, dict) or not isinstance(p.get("identifier"), str):
            raise PresetError("Each prompt needs a string identifier")
        if p["identifier"] in seen:
            raise PresetError("Duplicate prompt identifiers are not supported")
        seen.add(p["identifier"])
    if "prompt_order" in data and not isinstance(data["prompt_order"], list):
        raise PresetError("prompt_order must be an array")
    return data


def load_character(path: Path) -> dict[str, str]:
    raw = _read_json(path)
    source = raw.get("data", raw)
    if not isinstance(source, dict):
        raise PresetError("Character data must be an object")
    # ST V2 cards use data.*; plain JSON exports sometimes use top-level fields.
    keys = ("name", "description", "personality", "scenario", "mes_example")
    out = {key: str(source.get(key) or "") for key in keys}
    if source.get("character_book") or raw.get("character_book"):
        # Lorebook parsing planned for a separate engine; never silently run it here.
        out["_has_character_book"] = "true"
    return out


def _order(preset: Mapping[str, Any], character_id: str = "100001") -> list[dict[str, Any]]:
    groups = preset.get("prompt_order") or []
    if groups:
        if not all(isinstance(g, dict) for g in groups):
            raise PresetError("Invalid prompt_order group")
        selected = next((g for g in groups if str(g.get("character_id")) == character_id), groups[0])
        entries = selected.get("order", [])
        if not isinstance(entries, list):
            raise PresetError("Invalid prompt_order entries")
        return entries
    return [{"identifier": p["identifier"], "enabled": p.get("enabled", True)} for p in preset["prompts"]]


def _expand(text: str, values: Mapping[str, str]) -> tuple[str | None, str | None]:
    bad = {m.group(1) for m in MACRO_RE.finditer(text) if m.group(1).lower() not in SUPPORTED_MACROS}
    if bad:
        return None, "Unsupported macro(s): " + ", ".join(sorted(bad))
    return MACRO_RE.sub(lambda m: values[m.group(1).lower()], text), None


def build_overlay(
    preset: Mapping[str, Any], *, character: Mapping[str, str] | None = None,
    user_name: str = "群友", char_name: str = "", max_chars: int = MAX_OUTPUT_CHARS,
) -> Preview:
    """Compile safe text into an *overlay*, not an ST-accurate request sequence.

    Unsupported entries are skipped with explicit warnings to avoid leaking
    control macros as literal model instructions.
    """
    char = character or {}
    values = {
        "char": char_name or str(char.get("name") or "角色"),
        "user": user_name,
        "description": str(char.get("description") or ""),
        "personality": str(char.get("personality") or ""),
        "scenario": str(char.get("scenario") or ""),
        "mesexamples": str(char.get("mes_example") or ""),
    }
    warnings: list[str] = []
    if char.get("_has_character_book"):
        warnings.append("Character book exists but lorebook matching is not implemented")
    if preset.get("assistant_prefill"):
        warnings.append("assistant_prefill is not supported in overlay mode")
    if (preset.get("extensions") or {}).get("regex_scripts"):
        warnings.append("regex_scripts are preserved as data, but never executed")
    by_id = {p["identifier"]: p for p in preset["prompts"]}
    blocks: list[str] = []
    included: list[str] = []
    try:
        entries = _order(preset)
    except (ValueError, TypeError) as exc:
        raise PresetError(str(exc)) from exc
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("identifier"), str):
            warnings.append("Skipped malformed order entry")
            continue
        pid = entry["identifier"]
        if not entry.get("enabled", True):
            continue
        item = by_id.get(pid)
        if not item:
            warnings.append(f"Missing referenced prompt: {pid}")
            continue
        marker = bool(item.get("marker", False))
        role = str(item.get("role") or "system").lower()
        if pid == "chatHistory":
            continue  # MaiBot provides its own history, untouched.
        if marker:
            field = MARKER_FIELDS.get(pid.lower())
            if not field:
                warnings.append(f"Unsupported ST marker skipped: {pid}")
                continue
            text = values["mesexamples"] if field == "mes_examples" else values.get(field, "")
        else:
            text = item.get("content") or ""
            if not isinstance(text, str):
                warnings.append(f"Prompt content not text: {pid}")
                continue
        if role not in ("system", "user", "assistant", "model"):
            warnings.append(f"Unsupported role skipped: {pid} ({role})")
            continue
        if role in ("assistant", "model"):
            warnings.append(f"Assistant role skipped (prefill not implemented): {pid}")
            continue
        if role == "user":
            warnings.append(f"User role flattened to system overlay: {pid}")
        expanded, err = _expand(text, values)
        if err:
            warnings.append(f"{pid}: {err}; prompt skipped")
            continue
        if not expanded or not expanded.strip():
            continue
        # Max length is a hard bound; do not truncate in the middle of a macro / rule.
        if sum(len(b) for b in blocks) + len(expanded) > max_chars:
            warnings.append(f"Overlay char budget exhausted; skipped: {pid}")
            continue
        blocks.append(expanded.strip())
        included.append(pid)
    return Preview(text="\n\n".join(blocks), warnings=tuple(warnings), included=tuple(included))
