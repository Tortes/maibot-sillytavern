"""Stand-alone preset inspection; no MaiBot SDK required."""
from __future__ import annotations
import argparse
from pathlib import Path

from .preset import compile_preset, load_character, load_preset


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m st_bridge.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    preview = sub.add_parser("preview", help="Compile a preset and show its insertion plan")
    preview.add_argument("preset", type=Path)
    preview.add_argument("--character", type=Path)
    preview.add_argument("--user", default="群友")
    preview.add_argument("--char", default="")
    preview.add_argument("--character-id", default=None)
    preview.add_argument("--trigger", default="normal")
    args = parser.parse_args()

    compiled = compile_preset(
        load_preset(args.preset),
        character=load_character(args.character) if args.character else None,
        user_name=args.user,
        char_name=args.char,
        character_id=args.character_id,
        trigger=args.trigger,
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
