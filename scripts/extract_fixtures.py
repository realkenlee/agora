#!/usr/bin/env python3
"""
Extract images from Claude Code conversation JSONL into eval fixtures.

Usage:
    python scripts/extract_fixtures.py                   # list all images found
    python scripts/extract_fixtures.py --save adidas_slides   # save newest image as adidas_slides.jpg
    python scripts/extract_fixtures.py --save playmobil_firetruck  # save newest as playmobil_firetruck.jpg
    python scripts/extract_fixtures.py --save-all        # save all images with auto-names

Tip: Send the photo in a Claude message, wait for the response, then run with --save <name>.
The conversation JSONL is written per-turn, so the image lands after Claude responds.
"""
import argparse
import base64
import json
import os
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "eval_fixtures"
FIXTURES.mkdir(exist_ok=True)

GREEN  = "\033[32m"
YELLOW = "\033[33m"
RESET  = "\033[0m"


def load_images() -> list[dict]:
    project_dir = Path.home() / ".claude" / "projects" / "-Users-ken-code"
    jsonls = sorted(project_dir.glob("*.jsonl"), key=os.path.getmtime, reverse=True)
    if not jsonls:
        print("No JSONL files found in ~/.claude/projects/-Users-ken-code/")
        sys.exit(1)

    path = jsonls[0]
    images = []
    with open(path) as f:
        for line in f:
            try:
                obj = json.loads(line)
                msg = obj.get("message", {})
                ts = obj.get("timestamp", "")
                content = msg.get("content", [])
                adjacent_text = ""
                found_images = []
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "image":
                                src = block.get("source", {})
                                found_images.append({
                                    "ts": ts,
                                    "mime": src.get("media_type", "image/jpeg"),
                                    "data": src.get("data", ""),
                                    "text": adjacent_text,
                                })
                            elif block.get("type") == "text":
                                adjacent_text = block.get("text", "")[:80]
                images.extend(found_images)
            except:
                pass
    return images


def main():
    parser = argparse.ArgumentParser(description="Extract eval fixture images from Claude conversation")
    parser.add_argument("--save", metavar="NAME", help="Save the most recent image as <name>.jpg")
    parser.add_argument("--index", type=int, default=-1, help="Image index to save (default: -1 = newest)")
    parser.add_argument("--save-all", action="store_true", help="Save all images with auto-names")
    args = parser.parse_args()

    images = load_images()
    if not images:
        print("No images found in conversation history.")
        sys.exit(1)

    print(f"Found {len(images)} image(s):\n")
    for i, img in enumerate(images):
        ext = "png" if "png" in img["mime"] else "jpg"
        kb = len(img["data"]) * 3 // 4 // 1024
        label = f"  [{i}] {img['ts'][:19]}  {kb}KB  {img['mime']}"
        if img["text"]:
            label += f'  — "{img["text"]}"'
        print(label)

    print()

    if args.save:
        idx = args.index if args.index >= 0 else len(images) - 1
        if idx >= len(images):
            print(f"Index {idx} out of range (0–{len(images)-1})")
            sys.exit(1)
        img = images[idx]
        ext = "png" if "png" in img["mime"] else "jpg"
        out = FIXTURES / f"{args.save}.{ext}"
        out.write_bytes(base64.b64decode(img["data"]))
        print(f"{GREEN}Saved:{RESET} {out}  ({out.stat().st_size // 1024}KB)")
        return

    if args.save_all:
        for i, img in enumerate(images):
            ext = "png" if "png" in img["mime"] else "jpg"
            tag = img["ts"][:10].replace("-", "")
            name = f"image_{i:03d}_{tag}.{ext}"
            out = FIXTURES / name
            if out.exists():
                print(f"{YELLOW}Skip:{RESET} {name} (exists)")
            else:
                out.write_bytes(base64.b64decode(img["data"]))
                print(f"{GREEN}Saved:{RESET} {name}  ({out.stat().st_size // 1024}KB)")
        return

    print("To save: python scripts/extract_fixtures.py --save <name>")
    print("         python scripts/extract_fixtures.py --save-all")


if __name__ == "__main__":
    main()
