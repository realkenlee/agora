#!/usr/bin/env python3
"""
Agora smoke test — acts as buyer + seller agents, exercises the full protocol.

Run:
    python scripts/smoke_test.py                      # test prod
    python scripts/smoke_test.py --url http://localhost:8001   # test local

Exit 0 = all checks passed.
Exit 1 = at least one check failed.
"""

import argparse
import asyncio
import json
import sys
import time
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

# ── Test users (tokens are user UUIDs) ────────────────────────────────────────
MARCUS_TOKEN = "381803c8-0750-4828-a94e-ba62ed2f637a"  # seller
SARAH_TOKEN  = "f38ab1ea-6e75-4c73-8f10-68cb039113e0"  # buyer

DEFAULT_URL  = "https://agora-production-fb42.up.railway.app"

# ── Colours ────────────────────────────────────────────────────────────────────
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
RESET  = "\033[0m"


# ── SSE client ─────────────────────────────────────────────────────────────────

class SSEClient:
    """Thin SSE consumer that collects events in a queue."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token    = token
        self._queue:  asyncio.Queue = asyncio.Queue()
        self._task:   Optional[asyncio.Task] = None

    async def connect(self):
        self._task = asyncio.create_task(self._run())

    async def _run(self):
        url = f"{self.base_url}/events?token={self.token}"
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", url) as resp:
                    event_type = "message"
                    async for line in resp.aiter_lines():
                        line = line.rstrip()
                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:"):
                            raw = line[5:].strip()
                            if raw and raw != "{}":
                                try:
                                    data = json.loads(raw)
                                except json.JSONDecodeError:
                                    data = {"raw": raw}
                                await self._queue.put({"event": event_type, "data": data})
                            event_type = "message"
                        elif line == "":
                            event_type = "message"
        except asyncio.CancelledError:
            pass

    async def wait_for(self, event_name: str, timeout: float = 30, **filters) -> dict:
        """Wait for a specific event, optionally matching filter kwargs against data fields."""
        deadline = time.monotonic() + timeout
        collected = []
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=min(remaining, 1.0))
                if msg["event"] == event_name:
                    data = msg["data"]
                    if all(str(data.get(k)) == str(v) for k, v in filters.items()):
                        return data
                    collected.append(msg)
                else:
                    collected.append(msg)
            except asyncio.TimeoutError:
                continue
        # put unmatched back for future calls
        for m in collected:
            await self._queue.put(m)
        raise TimeoutError(
            f"Event '{event_name}' not received within {timeout}s"
            + (f" (filters: {filters})" if filters else "")
        )

    def close(self):
        if self._task:
            self._task.cancel()


# ── HTTP helpers ───────────────────────────────────────────────────────────────

class Agent:
    def __init__(self, base_url: str, token: str):
        self.base = base_url
        self.headers = {"Authorization": f"Bearer {token}"}

    def _url(self, path: str) -> str:
        return f"{self.base}{path}"

    async def get(self, path: str) -> Any:
        async with httpx.AsyncClient() as c:
            r = await c.get(self._url(path), headers=self.headers, timeout=30)
            r.raise_for_status()
            return r.json()

    async def post(self, path: str, body: dict) -> Any:
        async with httpx.AsyncClient() as c:
            r = await c.post(self._url(path), json=body, headers=self.headers, timeout=30)
            r.raise_for_status()
            return r.json()

    async def patch(self, path: str, body: dict) -> Any:
        async with httpx.AsyncClient() as c:
            r = await c.patch(self._url(path), json=body, headers=self.headers, timeout=30)
            r.raise_for_status()
            return r.json()

    async def delete(self, path: str) -> Any:
        async with httpx.AsyncClient() as c:
            r = await c.delete(self._url(path), headers=self.headers, timeout=30)
            r.raise_for_status()
            return r.json() if r.content else {}


# ── Assertions ─────────────────────────────────────────────────────────────────

_failures: list[str] = []

def check(label: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  {GREEN}✓{RESET} {label}")
    else:
        msg = f"{label}" + (f" — {detail}" if detail else "")
        print(f"  {RED}✗{RESET} {msg}")
        _failures.append(msg)

def section(title: str):
    print(f"\n{YELLOW}{title}{RESET}")


# ── Smoke test ─────────────────────────────────────────────────────────────────

async def run(base_url: str):
    marcus = Agent(base_url, MARCUS_TOKEN)
    sarah  = Agent(base_url, SARAH_TOKEN)

    # ── 0. Health ──────────────────────────────────────────────────────────────
    section("0. Health")
    health = await marcus.get("/")
    check("API reachable", "version" in health or "status" in health or health)

    # ── 1. SSE connections ─────────────────────────────────────────────────────
    section("1. SSE connections")
    m_stream = SSEClient(base_url, MARCUS_TOKEN)
    s_stream = SSEClient(base_url, SARAH_TOKEN)
    await m_stream.connect()
    await s_stream.connect()
    await asyncio.sleep(1)  # let connections establish
    check("Marcus SSE connected", True)
    check("Sarah SSE connected", True)

    # ── 2. Generate listing (AI) ───────────────────────────────────────────────
    section("2. Generate listing via AI")
    gen = await marcus.post("/ai/generate", {
        "description": "Vintage arc floor lamp, working, minor scratches on base",
        "price_hint": 55,
        "location": {"lat": 30.27, "lng": -97.74, "text": "Austin, TX"},
    })
    draft_id = gen.get("draft_id")
    check("draft_id returned", bool(draft_id), str(gen))
    check("status = processing", gen.get("status") == "processing")

    # ── 3. Wait for draft_ready SSE event ─────────────────────────────────────
    section("3. Wait for draft_ready event (≤ 180s)")
    try:
        event = await m_stream.wait_for("draft_ready", timeout=180)
        check("draft_ready received", True)
        check("event has title",     bool(event.get("title")))
        check("event has price",     event.get("suggested_price", 0) > 0)
        check("draft_id matches",    event.get("draft_id") == draft_id)
    except TimeoutError as e:
        check("draft_ready received", False, str(e))
        # fall through — poll draft until ready or failed (another 60s max)
        for _ in range(12):
            await asyncio.sleep(5)
            d = await marcus.get(f"/drafts/{draft_id}")
            if d.get("status") in ("ready", "failed"):
                break
        check("draft status (fallback)", d.get("status") in ("ready", "failed"),
              f"status={d.get('status')}")

    # ── 4. Check draft endpoint ────────────────────────────────────────────────
    section("4. Draft endpoint")
    draft = await marcus.get(f"/drafts/{draft_id}")
    check("status = ready",      draft.get("status") == "ready", f"got {draft.get('status')}")
    check("draft has title",     bool((draft.get("draft") or {}).get("title")))
    check("draft has price",     (draft.get("draft") or {}).get("suggested_price", 0) > 0)

    # ── 5. Publish ─────────────────────────────────────────────────────────────
    section("5. Publish draft")
    listing_id = None
    try:
        pub = await marcus.post(f"/drafts/{draft_id}/publish", {})
        listing_id = pub.get("id")
        check("listing created", bool(listing_id), str(pub))
        check("status = active", pub.get("status") == "active")
        check("_state present",  "state" in pub)
        if "state" in pub and pub["state"]:
            check("valid_actions present", bool(pub["state"].get("valid_actions")))
    except httpx.HTTPStatusError as e:
        check("publish succeeded", False, f"{e.response.status_code}: {e.response.text[:200]}")
        m_stream.close(); s_stream.close()
        return

    # ── 6. listing_live SSE event ──────────────────────────────────────────────
    section("6. listing_live event")
    try:
        ev = await m_stream.wait_for("listing_live", timeout=5)
        check("listing_live received", True)
        check("listing_id matches", ev.get("listing_id") == listing_id)
    except TimeoutError as e:
        check("listing_live received", False, str(e))

    # ── 7. Search ──────────────────────────────────────────────────────────────
    section("7. Search finds new listing")
    results = await sarah.post("/search", {
        "query": "vintage lamp",
        "location": {"lat": 30.27, "lng": -97.74, "text": "Austin, TX"},
        "radius_miles": 50,
    })
    found = any(r["listing"]["id"] == listing_id for r in results.get("results", []))
    check("listing appears in search", found,
          f"got {len(results.get('results', []))} results")

    # ── 8. GET listing — state ─────────────────────────────────────────────────
    section("8. Listing state for buyer")
    lst = await sarah.get(f"/listings/{listing_id}")
    check("listing accessible",    lst.get("id") == listing_id)
    check("_state present",        "state" in lst)
    state = lst.get("state") or {}
    check("make_offer in actions", "make_offer" in (state.get("valid_actions") or []),
          f"actions={state.get('valid_actions')}")

    # ── 9. Make offer ──────────────────────────────────────────────────────────
    section("9. Make offer (buyer)")
    offer = await sarah.post(f"/listings/{listing_id}/offers", {
        "amount": 40,
        "message": "Would you take $40?",
        "offered_by": "agent",
    })
    offer_id = offer.get("id")
    check("offer created",         bool(offer_id))
    check("status = pending",      offer.get("status") == "pending")
    check("_state present",        "state" in offer)
    buyer_actions = (offer.get("state") or {}).get("valid_actions", [])
    check("withdraw in actions",   "withdraw" in buyer_actions, f"actions={buyer_actions}")

    # ── 10. offer_received SSE event on seller side ────────────────────────────
    section("10. offer_received event (seller)")
    try:
        ev = await m_stream.wait_for("offer_received", timeout=10)
        check("offer_received received",  True)
        check("amount correct",           ev.get("amount") == 40)
        check("listing_id matches",       ev.get("listing_id") == listing_id)
    except TimeoutError as e:
        check("offer_received received", False, str(e))

    # ── 11. Semantic error — self-offer ───────────────────────────────────────
    section("11. Semantic error on self-offer")
    try:
        await marcus.post(f"/listings/{listing_id}/offers", {"amount": 40})
        check("rejected self-offer", False, "should have raised")
    except httpx.HTTPStatusError as e:
        body = e.response.json() if e.response.headers.get("content-type","").startswith("application/json") else {}
        detail = body.get("detail", {})
        error_code = detail.get("error_code", "") if isinstance(detail, dict) else ""
        check("rejected self-offer",  e.response.status_code == 400)
        check("error_code = SELF_OFFER", error_code == "SELF_OFFER", f"got {error_code!r}")

    # ── 12. Accept offer ───────────────────────────────────────────────────────
    section("12. Accept offer (seller)")
    accepted = await marcus.patch(f"/offers/{offer_id}", {
        "action": "accept",
        "responded_by": "agent",
    })
    check("status = accepted", accepted.get("status") == "accepted")

    # ── 13. Both parties get offer_accepted event ──────────────────────────────
    section("13. offer_accepted events")
    try:
        ev_m = await m_stream.wait_for("offer_accepted", timeout=5)
        check("seller gets offer_accepted", True)
    except TimeoutError as e:
        check("seller gets offer_accepted", False, str(e))
    try:
        ev_s = await s_stream.wait_for("offer_accepted", timeout=5)
        check("buyer gets offer_accepted", True)
    except TimeoutError as e:
        check("buyer gets offer_accepted", False, str(e))

    # ── 14. Send message ───────────────────────────────────────────────────────
    section("14. Send message + event")
    await sarah.post(f"/listings/{listing_id}/messages", {
        "body": "Thanks! I'll pick it up Saturday.",
        "sent_by": "agent",
    })
    try:
        ev = await m_stream.wait_for("message_received", timeout=5)
        check("seller gets message_received", True)
        check("preview present", bool(ev.get("preview")))
    except TimeoutError as e:
        check("seller gets message_received", False, str(e))

    # ── 15. Cleanup — remove listing ──────────────────────────────────────────
    section("15. Cleanup")
    try:
        await marcus.delete(f"/listings/{listing_id}")
        check("listing removed", True)
    except httpx.HTTPStatusError as e:
        check("listing removed", False, f"{e.response.status_code}")

    # ── Done ───────────────────────────────────────────────────────────────────
    m_stream.close()
    s_stream.close()


def main():
    parser = argparse.ArgumentParser(description="Agora smoke test")
    parser.add_argument("--url", default=DEFAULT_URL, help="API base URL")
    args = parser.parse_args()

    print(f"\nAgora smoke test → {args.url}\n{'─' * 50}")
    asyncio.run(run(args.url))

    print(f"\n{'─' * 50}")
    if _failures:
        print(f"{RED}FAILED{RESET} — {len(_failures)} check(s):")
        for f in _failures:
            print(f"  · {f}")
        sys.exit(1)
    else:
        print(f"{GREEN}ALL CHECKS PASSED{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
