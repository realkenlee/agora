"""
SSE event bus — in-process pub/sub for real-time agent and UI notifications.

Agents subscribe to GET /events and receive marketplace events as they happen.
The same stream the web UI uses — one protocol, all clients.
"""

from __future__ import annotations
import asyncio
import json
from typing import Any

# user_id (str) → list of queues (one per open connection)
_connections: dict[str, list[asyncio.Queue]] = {}


def subscribe(user_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _connections.setdefault(str(user_id), []).append(q)
    return q


def unsubscribe(user_id: str, q: asyncio.Queue) -> None:
    conns = _connections.get(str(user_id), [])
    if q in conns:
        conns.remove(q)
    if not conns:
        _connections.pop(str(user_id), None)


async def emit(user_id: str, event: str, data: dict[str, Any]) -> None:
    for q in list(_connections.get(str(user_id), [])):
        try:
            q.put_nowait({"event": event, "data": data})
        except asyncio.QueueFull:
            pass  # slow consumer — drop rather than block


async def emit_many(user_ids: list, event: str, data: dict[str, Any]) -> None:
    for uid in user_ids:
        await emit(str(uid), event, data)


async def stream(user_id: str, q: asyncio.Queue):
    """Yield SSE-formatted strings. Cleans up subscription on disconnect."""
    yield "event: connected\ndata: {}\n\n"
    try:
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=15)
                payload = json.dumps(msg["data"])
                yield f"event: {msg['event']}\ndata: {payload}\n\n"
            except asyncio.TimeoutError:
                yield ": ping\n\n"  # keep connection alive through proxies
    finally:
        unsubscribe(user_id, q)
