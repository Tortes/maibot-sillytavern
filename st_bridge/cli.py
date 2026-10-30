"""Stand-alone preview; requires Python 3.12+, no MaiBot SDK."""
from __future__ import annotations
import argparse
from pathlib import Path
from .preset import build_overlay, load_preset, load_character

def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m st_bridge.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("preview")
    p.add_argument("preset", type=Path)
    p.add_argument("--character", type=Path)
    p.add_argument("--user", default="群友")
    p.add_argument("--char", default="")
    args = parser.parse_args()
    preview = build_overlay(
        load_preset(args.preset), character=load_character(args.character) if args.character else None,
        user_name=args.user, char_name=args.char,
    )
    print("=== Overlay ===\n" + (preview.text or "[empty]"))
    print("\n=== Included ===\n" + ", ".join(preview.included))
    print("\n=== Warnings ===")
    for warning in preview.warnings:
        print("- " + warning)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
