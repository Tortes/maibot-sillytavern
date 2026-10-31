"""Stand-alone preset and worldbook inspection; no MaiBot SDK required."""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from .preset import compile_preset, load_character, load_preset
from .worldbook import compile_worldbooks, load_worldbook


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m st_bridge.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    preview = sub.add_parser("preview", help="Compile a preset and show its insertion plan")
    preview.add_argument("preset", type=Path)
    preview.add_argument("--character", type=Path)
    preview.add_argument("--worldbook", type=Path, action="append", default=[])
    preview.add_argument("--scan-text", action="append", default=[], help="Chat message text to scan; may be repeated")
    preview.add_argument("--scan-depth", type=int, default=2)
    preview.add_argument("--recursive", action="store_true", help="enable recursion when the book has no recursiveScanning setting")
    preview.add_argument("--worldbook-max-chars", type=int, default=6000)
    preview.add_argument("--user", default="群友")
    preview.add_argument("--char", default="")
    preview.add_argument("--character-id", default=None)
    preview.add_argument("--trigger", default="normal")
    args = parser.parse_args()

    character = load_character(args.character) if args.character else None
    compiled = compile_preset(
        load_preset(args.preset),
        character=character,
        user_name=args.user,
        char_name=args.char,
        character_id=args.character_id,
        trigger=args.trigger,
    )

    books = []
    if character and isinstance(character.get("_character_book"), dict):
        books.append(character["_character_book"])
    books.extend(load_worldbook(path) for path in args.worldbook)
    if books:
        scan_items = [
            {
                "item_type": "UserMessageItem",
                "meta": {"item_id": f"preview-{index}", "logical_turn_id": None, "timestamp": ""},
                "parts": [{"type": "text", "text": message}],
            }
            for index, message in enumerate(args.scan_text)
        ]
        lore = compile_worldbooks(
            books,
            scan_items,
            character=character,
            user_name=args.user,
            char_name=args.char,
            scan_depth=args.scan_depth,
            max_chars=args.worldbook_max_chars,
            recursive=args.recursive,
        )
        compiled = replace(
            compiled,
            before_history=lore.before_character + compiled.before_history + lore.after_character,
            depth_entries=tuple(sorted(
                compiled.depth_entries + lore.depth_entries,
                key=lambda item: item.injection_order,
            )),
            warnings=compiled.warnings + lore.warnings,
            included=compiled.included + lore.activated,
        )

    sections = (
        ("BEFORE HISTORY", compiled.before_history),
        ("DEPTH INSERTIONS", compiled.depth_entries),
        ("AFTER HISTORY", compiled.after_history),
    )
    for title, prompts in sections:
        print(f"\n=== {title} ===")
        if not prompts:
            print("[none]")
        for prompt in prompts:
            print(f"[{prompt.role}] {prompt.identifier} depth={prompt.injection_depth} order={prompt.injection_order}")
            print(prompt.text)
    if compiled.assistant_prefill:
        print("\n=== ASSISTANT PREFILL (opt-in at runtime) ===")
        print(compiled.assistant_prefill)
    print("\n=== INCLUDED ===")
    print(", ".join(compiled.included) or "[none]")
    print("\n=== WARNINGS ===")
    for warning in compiled.warnings:
        print("- " + warning)
    if not compiled.warnings:
        print("[none]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
