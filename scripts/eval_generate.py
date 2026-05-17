#!/usr/bin/env python3
"""
Agora listing generation eval — tests the vision+LLM pipeline against known items.

Usage:
    python scripts/eval_generate.py                        # run all cases against prod
    python scripts/eval_generate.py --url http://localhost:8001
    python scripts/eval_generate.py --case playmobil      # run one case by name

Place test images in scripts/eval_fixtures/<name>.jpg

Exit 0 = all assertions passed.
Exit 1 = at least one failure.
"""

from __future__ import annotations
import argparse
import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx

DEFAULT_URL = os.environ.get("AGORA_API_URL", "https://agora-production-2bbb.up.railway.app")
TEST_TOKEN  = "381803c8-0750-4828-a94e-ba62ed2f637a"  # Marcus (smoke-test seller)

FIXTURES = Path(__file__).parent / "eval_fixtures"

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
RESET  = "\033[0m"

# ── Test cases ─────────────────────────────────────────────────────────────────
# Each case: image file (optional), description, and assertions on the draft.
# Assertions are callables that receive the draft dict and return (bool, reason).

class Assertion:
    def __init__(self, label: str, fn):
        self.label = label
        self._fn = fn
    def __call__(self, draft) -> tuple[bool, str]:
        return self._fn(draft)

def _title_contains(*words) -> Assertion:
    def fn(draft):
        title = draft.get("title", "").lower()
        for w in words:
            if w.lower() in title:
                return True, ""
        return False, f"title {title!r} missing {words}"
    return Assertion(f"title contains {words}", fn)

def _brand_in_title_or_attrs(*brands) -> Assertion:
    def fn(draft):
        text = " ".join([
            draft.get("title", ""),
            json.dumps(draft.get("attributes", {})),
            draft.get("description", ""),
        ]).lower()
        for b in brands:
            if b.lower() in text:
                return True, ""
        return False, f"brand {brands} not found in title/attrs/description"
    return Assertion(f"brand {brands[0]} identified", fn)

def _price_in_range(lo: float, hi: float) -> Assertion:
    def fn(draft):
        p = draft.get("suggested_price", 0)
        if lo <= p <= hi:
            return True, ""
        return False, f"price ${p} outside ${lo}–${hi}"
    return Assertion(f"price ${lo}–${hi}", fn)

def _category_is(*cats) -> Assertion:
    def fn(draft):
        cat = draft.get("category_id", "")
        if cat in cats:
            return True, ""
        return False, f"got {cat!r}, expected one of {cats}"
    return Assertion(f"category in {cats}", fn)


CASES = [
    {
        "name": "adidas_slides",
        # Description intentionally omits brand — vision model must read the 3-stripe logo
        "description": "Black slides, size 10, barely worn",
        "image": "adidas_slides.jpg",
        "assertions": [
            _brand_in_title_or_attrs("Adidas"),
            _title_contains("adidas", "slide", "sandal"),
            _price_in_range(10, 60),
            _category_is("clothing", "sports"),
        ],
    },
    {
        "name": "playmobil_firetruck",
        # Description intentionally omits brand — vision model must read the logo on the toy/box
        "description": "Toy fire truck with extending ladder, red, good condition",
        "image": "playmobil_firetruck.jpg",
        "assertions": [
            _brand_in_title_or_attrs("Playmobil"),
            _title_contains("playmobil", "fire"),
            _price_in_range(5, 90),  # complete set with box can reach $85
            _category_is("toys"),
        ],
    },
    {
        "name": "vintage_floor_lamp",
        "description": "Vintage arc floor lamp, working, minor scratches on base",
        "image": None,
        "assertions": [
            _price_in_range(20, 200),
            _category_is("furniture", "other"),
        ],
    },
]


# ── HTTP helpers ───────────────────────────────────────────────────────────────

async def post(client: httpx.AsyncClient, base: str, path: str, body: dict) -> dict:
    r = await client.post(f"{base}{path}", json=body,
                          headers={"Authorization": f"Bearer {TEST_TOKEN}"}, timeout=30)
    r.raise_for_status()
    return r.json()

async def get(client: httpx.AsyncClient, base: str, path: str) -> dict:
    r = await client.get(f"{base}{path}",
                         headers={"Authorization": f"Bearer {TEST_TOKEN}"}, timeout=30)
    r.raise_for_status()
    return r.json()


async def wait_for_draft(client: httpx.AsyncClient, base: str, draft_id: str,
                         timeout: float = 120) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        d = await get(client, base, f"/drafts/{draft_id}")
        if d["status"] in ("ready", "failed"):
            return d
        await asyncio.sleep(4)
    raise TimeoutError(f"draft {draft_id} not ready after {timeout}s")


# ── Runner ─────────────────────────────────────────────────────────────────────

_failures: list[str] = []

def check(label: str, ok: bool, detail: str = ""):
    if ok:
        print(f"  {GREEN}✓{RESET} {label}")
    else:
        msg = label + (f" — {detail}" if detail else "")
        print(f"  {RED}✗{RESET} {msg}")
        _failures.append(msg)


async def run_case(client: httpx.AsyncClient, base: str, case: dict):
    name = case["name"]
    print(f"\n{YELLOW}{name}{RESET}")

    # Build photo_urls if fixture exists
    photo_urls = []
    img_path = FIXTURES / case["image"] if case.get("image") else None
    if img_path and img_path.exists():
        b64 = base64.b64encode(img_path.read_bytes()).decode()
        photo_urls = [f"data:image/jpeg;base64,{b64}"]
        print(f"  image: {img_path.name} ({img_path.stat().st_size // 1024}KB)")
    elif case.get("image"):
        print(f"  {YELLOW}⚠ fixture {case['image']} not found — running text-only{RESET}")

    body = {"description": case["description"]}
    if photo_urls:
        body["photo_urls"] = photo_urls

    t0 = time.monotonic()
    resp = await post(client, base, "/ai/generate", body)
    draft_id = resp.get("draft_id")
    check("draft_id returned", bool(draft_id), str(resp))
    if not draft_id:
        return

    draft_resp = await wait_for_draft(client, base, draft_id)
    elapsed = time.monotonic() - t0
    check(f"draft ready in {elapsed:.0f}s", draft_resp["status"] == "ready",
          f"status={draft_resp['status']} error={draft_resp.get('error')}")

    if draft_resp["status"] != "ready":
        return

    draft = draft_resp.get("draft") or {}
    print(f"  title:     {draft.get('title')}")
    print(f"  price:     ${draft.get('suggested_price')}")
    print(f"  condition: {draft.get('condition')}")
    print(f"  category:  {draft.get('category_id')}")
    print(f"  attrs:     {draft.get('attributes')}")
    print(f"  reasoning: {draft.get('reasoning')}")

    for assertion in case["assertions"]:
        ok, detail = assertion(draft)
        check(assertion.label, ok, detail)


async def run(base: str, only: str | None):
    cases = [c for c in CASES if not only or c["name"] == only]
    if not cases:
        print(f"No case named {only!r}. Available: {[c['name'] for c in CASES]}")
        sys.exit(1)

    print(f"\nAgora generate eval → {base}")
    print(f"Running {len(cases)} case(s)\n{'─' * 50}")

    async with httpx.AsyncClient() as client:
        for i, case in enumerate(cases):
            if i > 0:
                await asyncio.sleep(8)  # avoid free-tier rate limit (20 req/min)
            await run_case(client, base, case)


def main():
    parser = argparse.ArgumentParser(description="Agora generate eval")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--case", default=None, help="Run only this case name")
    args = parser.parse_args()

    asyncio.run(run(args.url, args.case))

    print(f"\n{'─' * 50}")
    if _failures:
        print(f"{RED}FAILED{RESET} — {len(_failures)} assertion(s):")
        for f in _failures:
            print(f"  · {f}")
        sys.exit(1)
    else:
        print(f"{GREEN}ALL ASSERTIONS PASSED{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
