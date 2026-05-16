"""
Agora Marketplace API — Agent-Native Protocol

Designed to be consumed by agents first, humans via UI second.
Every response tells agents what they can do next (state.valid_actions).
Every error has a machine-readable error_code agents can reason over.
Real-time events delivered via GET /events (SSE) — no polling needed.
"""

from __future__ import annotations
import asyncio
import base64
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import io
import uuid as uuid_mod
import boto3
import httpx
from dotenv import load_dotenv
from PIL import Image
from fastapi import FastAPI, HTTPException, Header, Depends, UploadFile, File, Request, Form
from fastapi.responses import StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from api import db
import api.events as events_bus
from api.models import (
    CreateListingRequest, UpdateListingRequest, ListingResponse,
    SearchRequest, SearchResponse, SearchResult,
    CreateOfferRequest, RespondOfferRequest, OfferResponse,
    SendMessageRequest, MessageResponse,
    GenerateListingRequest, GenerateListingResponse,
    GenerateJobResponse, DraftResponse, NotificationResponse,
    UserSummary, Location,
)
from ai.generate import generate_listing_draft, analyze_photos, analyze_brand
from ai.embed import embed_text
from ai.moderate import moderate_listing


# ── App setup ─────────────────────────────────────────────────────────────────

# ── Telegram ──────────────────────────────────────────────────────────────────

_TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_WEB_URL  = os.environ.get("WEB_URL", "https://tryagora.vercel.app")

# ── Photo storage (Tigris / S3-compatible) ────────────────────────────────────

_S3_BUCKET   = os.environ.get("RAILWAY_BUCKET_BUCKET_NAME", "")
_S3_ENDPOINT = os.environ.get("RAILWAY_BUCKET_ENDPOINT", "")
_S3_KEY_ID   = os.environ.get("RAILWAY_BUCKET_ACCESS_KEY_ID", "")
_S3_SECRET   = os.environ.get("RAILWAY_BUCKET_SECRET_ACCESS_KEY", "")
_S3_REGION   = os.environ.get("RAILWAY_BUCKET_REGION", "auto")
_PHOTO_MAX   = 1200

def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=_S3_ENDPOINT,
        aws_access_key_id=_S3_KEY_ID,
        aws_secret_access_key=_S3_SECRET,
        region_name=_S3_REGION,
    )

async def upload_photo(image_bytes: bytes) -> str | None:
    if not _S3_BUCKET:
        return None
    loop = asyncio.get_event_loop()
    def _upload():
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((_PHOTO_MAX, _PHOTO_MAX), Image.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        key = f"photos/{uuid_mod.uuid4()}.jpg"
        _s3_client().put_object(
            Bucket=_S3_BUCKET, Key=key, Body=buf,
            ContentType="image/jpeg",
        )
        return f"https://agora-production-fb42.up.railway.app/photos/{key}"
    try:
        return await loop.run_in_executor(None, _upload)
    except Exception as e:
        print(f"[upload_photo] failed: {e}")
        return None


async def send_telegram(chat_id: int, text: str) -> None:
    if not _TG_TOKEN:
        return
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    await db.execute(
        """CREATE TABLE IF NOT EXISTS listing_drafts (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL REFERENCES users(id),
            status TEXT NOT NULL DEFAULT 'processing',
            description TEXT,
            price_hint FLOAT,
            draft JSONB,
            error TEXT,
            telegram_chat_id BIGINT,
            brand_candidates JSONB,
            confirmed_brand TEXT,
            photo_urls JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )"""
    )
    await db.execute(
        "ALTER TABLE listing_drafts ADD COLUMN IF NOT EXISTS telegram_chat_id BIGINT"
    )
    await db.execute(
        "ALTER TABLE listing_drafts ADD COLUMN IF NOT EXISTS brand_candidates JSONB"
    )
    await db.execute(
        "ALTER TABLE listing_drafts ADD COLUMN IF NOT EXISTS confirmed_brand TEXT"
    )
    await db.execute(
        "ALTER TABLE listing_drafts ADD COLUMN IF NOT EXISTS photo_urls JSONB"
    )
    await db.execute(
        """CREATE TABLE IF NOT EXISTS telegram_accounts (
            chat_id BIGINT PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            first_name TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )"""
    )
    yield
    await db.close_pool()


app = FastAPI(
    title="Agora Marketplace API",
    description="Agent-native local marketplace. Buy, sell, negotiate — human or AI.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Semantic error helper ──────────────────────────────────────────────────────

def _err(status: int, code: str, detail: str, **context):
    """Raise a structured error agents can reason about."""
    raise HTTPException(status_code=status, detail={
        "error_code": code,
        "detail": detail,
        "context": context,
    })


# ── Auth ──────────────────────────────────────────────────────────────────────

async def current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization:
        _err(401, "AUTH_REQUIRED", "Authorization header required")

    token = authorization.removeprefix("Bearer ").strip()

    # Agent session token
    session = await db.fetchrow(
        "SELECT * FROM agent_sessions WHERE token_hash = $1 AND (expires_at IS NULL OR expires_at > NOW())",
        token,
    )
    if session:
        return {
            "user_id": session["user_id"],
            "agent_session_id": session["id"],
            "is_agent": True,
            "can_list": session["can_list"],
            "can_offer": session["can_offer"],
            "can_message": session["can_message"],
            "max_offer": session["max_offer"],
        }

    user = await db.fetchrow("SELECT id, display_name FROM users WHERE id::text = $1", token)
    if not user:
        _err(401, "INVALID_TOKEN", "Token does not match any user or agent session")

    return {
        "user_id": user["id"],
        "agent_session_id": None,
        "is_agent": False,
        "can_list": True,
        "can_offer": True,
        "can_message": True,
        "max_offer": None,
    }


async def _resolve_token(token: str) -> Optional[dict]:
    """Resolve a raw token string to a user dict, or None."""
    u = await db.fetchrow("SELECT id FROM users WHERE id::text = $1", token)
    if u:
        return {"user_id": u["id"], "is_agent": False}
    return None


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/")
async def health():
    return {"status": "ok", "service": "agora-marketplace", "version": "0.2.0"}


@app.get("/photos/{path:path}")
async def serve_photo(path: str):
    if not _S3_BUCKET:
        raise HTTPException(404, "No photo storage configured")
    loop = asyncio.get_event_loop()
    def _fetch():
        obj = _s3_client().get_object(Bucket=_S3_BUCKET, Key=path)
        return obj["Body"].read()
    try:
        data = await loop.run_in_executor(None, _fetch)
        return Response(content=data, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=31536000"})
    except Exception:
        raise HTTPException(404, "Photo not found")


# ── SSE Event Stream ──────────────────────────────────────────────────────────

@app.get("/events")
async def event_stream(
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    """
    Real-time event stream for agents and UI clients.
    Agents subscribe here instead of polling endpoints.
    Pass token as query param (?token=...) or Authorization header.

    Events: draft_ready, draft_failed, offer_received, offer_accepted,
            offer_rejected, offer_countered, message_received, listing_live
    """
    raw = token or (authorization.removeprefix("Bearer ").strip() if authorization else None)
    if not raw:
        _err(401, "AUTH_REQUIRED", "Pass token as query param or Authorization header")

    user = await db.fetchrow("SELECT id FROM users WHERE id::text = $1", raw)
    if not user:
        _err(401, "INVALID_TOKEN", "Token does not match any user")

    user_id = str(user["id"])
    q = events_bus.subscribe(user_id)

    return StreamingResponse(
        events_bus.stream(user_id, q),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Listings ──────────────────────────────────────────────────────────────────

@app.post("/listings", response_model=ListingResponse, status_code=201)
async def create_listing(body: CreateListingRequest, caller=Depends(current_user)):
    if not caller["can_list"]:
        _err(403, "PERMISSION_DENIED", "Agent session does not have listing permission")

    mod = await moderate_listing(body.title, body.description, body.category_id)
    if not mod["allowed"]:
        _err(422, "CONTENT_REJECTED", f"Listing rejected by moderation", reason=mod["reason"])

    _vec = await embed_text(f"{body.title} {body.description} {body.category_id}")
    embedding = "[" + ",".join(str(x) for x in _vec) + "]"

    row = await db.fetchrow(
        """
        INSERT INTO listings
            (seller_id, title, description, category_id, condition, attributes,
             price, price_negotiable, min_price, lat, lng, location_text,
             listed_by, embedding)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
        RETURNING *
        """,
        caller["user_id"], body.title, body.description, body.category_id,
        body.condition.value, dict(body.attributes), float(body.price),
        body.price_negotiable,
        float(body.min_price) if body.min_price else None,
        body.location.lat, body.location.lng, body.location.text,
        body.listed_by, embedding,
    )

    if body.photo_urls:
        await db.executemany(
            "INSERT INTO listing_photos (listing_id, url, position) VALUES ($1,$2,$3)",
            [(row["id"], url, i) for i, url in enumerate(body.photo_urls)],
        )

    return await _listing_response(row, caller["user_id"])


@app.get("/listings/{listing_id}", response_model=ListingResponse)
async def get_listing(listing_id: UUID, authorization: Optional[str] = Header(None)):
    await db.execute("UPDATE listings SET views = views + 1 WHERE id = $1", listing_id)
    row = await db.fetchrow("SELECT * FROM listings WHERE id = $1", listing_id)
    if not row:
        _err(404, "LISTING_NOT_FOUND", "No listing with that ID")
    viewer_id = None
    if authorization:
        token = authorization.removeprefix("Bearer ").strip()
        u = await db.fetchrow("SELECT id FROM users WHERE id::text = $1", token)
        if u:
            viewer_id = u["id"]
    return await _listing_response(row, viewer_id)


@app.patch("/listings/{listing_id}", response_model=ListingResponse)
async def update_listing(listing_id: UUID, body: UpdateListingRequest, caller=Depends(current_user)):
    row = await db.fetchrow("SELECT * FROM listings WHERE id = $1", listing_id)
    if not row:
        _err(404, "LISTING_NOT_FOUND", "No listing with that ID")
    if row["seller_id"] != caller["user_id"]:
        _err(403, "NOT_YOUR_LISTING", "Only the seller can update this listing")

    updates, vals = [], []
    for field, val in body.model_dump(exclude_none=True).items():
        updates.append(f"{field} = ${len(vals)+1}")
        vals.append(val.value if hasattr(val, "value") else val)

    if not updates:
        return await _listing_response(row, caller["user_id"])

    vals.append(listing_id)
    updated = await db.fetchrow(
        f"UPDATE listings SET {', '.join(updates)} WHERE id = ${len(vals)} RETURNING *",
        *vals,
    )
    return await _listing_response(updated, caller["user_id"])


@app.delete("/listings/{listing_id}", status_code=204)
async def delete_listing(listing_id: UUID, caller=Depends(current_user)):
    row = await db.fetchrow("SELECT seller_id FROM listings WHERE id = $1", listing_id)
    if not row:
        _err(404, "LISTING_NOT_FOUND", "No listing with that ID")
    if row["seller_id"] != caller["user_id"]:
        _err(403, "NOT_YOUR_LISTING", "Only the seller can delete this listing")
    await db.execute("UPDATE listings SET status = 'removed' WHERE id = $1", listing_id)


# ── Search ────────────────────────────────────────────────────────────────────

@app.post("/search", response_model=SearchResponse)
async def search(body: SearchRequest):
    """
    Hybrid semantic + geo search.
    Natural language queries work best — agents should use full sentences.
    Trivial queries (empty / "everything" / "all") skip embedding and use recency sort.
    """
    trivial = body.query.lower().strip() in ("", "everything", "all")

    filters, vals = ["l.status = 'active'"], []

    if not trivial:
        embedding = await embed_text(body.query)
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
        vals.append(embedding_str)
        score_expr = "COALESCE(1 - (l.embedding <=> $1::vector), 0)"
        order_expr = f"{score_expr} DESC"
    else:
        score_expr = "1.0"
        order_expr = "l.created_at DESC"

    if body.max_price:
        vals.append(float(body.max_price))
        filters.append(f"l.price <= ${len(vals)}")
    if body.min_price:
        vals.append(float(body.min_price))
        filters.append(f"l.price >= ${len(vals)}")
    if body.category_id:
        vals.append(body.category_id)
        filters.append(f"(l.category_id = ${len(vals)} OR l.category_id LIKE ${len(vals)} || '/%')")
    if body.condition:
        vals.append([c.value for c in body.condition])
        filters.append(f"l.condition = ANY(${len(vals)})")

    if body.location:
        lat_idx = len(vals) + 1
        lng_idx = len(vals) + 2
        vals.extend([body.location.lat, body.location.lng])
        dist_expr = f"earth_distance(ll_to_earth(l.lat, l.lng), ll_to_earth(${lat_idx}, ${lng_idx})) / 1609.34"
        if body.radius_miles:
            vals.append(body.radius_miles * 1609.34)
            filters.append(f"earth_distance(ll_to_earth(l.lat, l.lng), ll_to_earth(${lat_idx}, ${lng_idx})) <= ${len(vals)}")
    else:
        dist_expr = "NULL::float"

    where = " AND ".join(filters)
    rows = await db.fetch(
        f"""
        SELECT l.*, {score_expr} AS score, {dist_expr} AS distance_mi
        FROM listings l
        WHERE {where}
        ORDER BY {order_expr}
        LIMIT {body.limit} OFFSET {body.offset}
        """,
        *vals,
    )

    listings = await _listing_responses_bulk(rows, None)
    results = [
        SearchResult(
            listing=listing,
            score=float(row["score"] or 0),
            distance_mi=float(row["distance_mi"]) if row.get("distance_mi") else None,
        )
        for listing, row in zip(listings, rows)
    ]

    return SearchResponse(results=results, total=len(results), query=body.query)


# ── Offers ────────────────────────────────────────────────────────────────────

@app.post("/listings/{listing_id}/offers", response_model=OfferResponse, status_code=201)
async def make_offer(listing_id: UUID, body: CreateOfferRequest, caller=Depends(current_user)):
    if not caller["can_offer"]:
        _err(403, "PERMISSION_DENIED", "Agent session does not have offer permission")
    if caller["max_offer"] and float(body.amount) > float(caller["max_offer"]):
        _err(403, "EXCEEDS_AGENT_LIMIT",
             f"Offer exceeds agent's max_offer limit",
             offered=float(body.amount), agent_limit=float(caller["max_offer"]))

    listing = await db.fetchrow(
        "SELECT seller_id, status, price, title FROM listings WHERE id = $1", listing_id
    )
    if not listing:
        _err(404, "LISTING_NOT_FOUND", "No listing with that ID")
    if listing["seller_id"] == caller["user_id"]:
        _err(400, "SELF_OFFER", "Cannot make an offer on your own listing")
    if listing["status"] != "active":
        _err(409, "LISTING_NOT_ACTIVE",
             f"Listing is {listing['status']}, not available for offers",
             status=listing["status"])

    offer_pct = round(float(body.amount) / float(listing["price"]) * 100, 1)

    row = await db.fetchrow(
        "INSERT INTO offers (listing_id, buyer_id, amount, message, offered_by) VALUES ($1,$2,$3,$4,$5) RETURNING *",
        listing_id, caller["user_id"], float(body.amount), body.message, body.offered_by,
    )
    await db.execute(
        "UPDATE listings SET status = 'pending' WHERE id = $1 AND status = 'active'", listing_id
    )

    buyer = await db.fetchrow("SELECT display_name FROM users WHERE id = $1", caller["user_id"])
    buyer_name = buyer["display_name"] if buyer else "Buyer"

    await events_bus.emit(str(listing["seller_id"]), "offer_received", {
        "offer_id": str(row["id"]),
        "listing_id": str(listing_id),
        "listing_title": listing["title"],
        "amount": float(body.amount),
        "asking_price": float(listing["price"]),
        "offer_pct": offer_pct,
        "from": buyer_name,
        "message": body.message,
    })

    # Telegram push to seller if registered
    seller_tg = await db.fetchrow(
        "SELECT chat_id FROM telegram_accounts WHERE user_id=$1", listing["seller_id"]
    )
    if seller_tg:
        msg_line = f'\n"{body.message}"' if body.message else ""
        await send_telegram(
            seller_tg["chat_id"],
            f'New offer on "{listing["title"]}"!\n'
            f'{buyer_name} offered ${float(body.amount):.0f} '
            f'(asking ${float(listing["price"]):.0f} · {offer_pct}%){msg_line}\n\n'
            f'Reply ACCEPT or DECLINE, or review at {_WEB_URL}/listings/{listing_id}',
        )

    return await _offer_response(row, caller["user_id"])


@app.get("/listings/{listing_id}/offers", response_model=list[OfferResponse])
async def list_offers(listing_id: UUID, caller=Depends(current_user)):
    listing = await db.fetchrow("SELECT seller_id FROM listings WHERE id = $1", listing_id)
    if not listing:
        _err(404, "LISTING_NOT_FOUND", "No listing with that ID")
    if listing["seller_id"] != caller["user_id"]:
        _err(403, "PERMISSION_DENIED", "Only the seller can view all offers")
    rows = await db.fetch(
        "SELECT * FROM offers WHERE listing_id = $1 ORDER BY created_at DESC", listing_id
    )
    return [await _offer_response(r, caller["user_id"]) for r in rows]


@app.patch("/offers/{offer_id}", response_model=OfferResponse)
async def respond_to_offer(offer_id: UUID, body: RespondOfferRequest, caller=Depends(current_user)):
    offer = await db.fetchrow(
        "SELECT o.*, l.seller_id, l.title FROM offers o JOIN listings l ON l.id = o.listing_id WHERE o.id = $1",
        offer_id,
    )
    if not offer:
        _err(404, "OFFER_NOT_FOUND", "No offer with that ID")
    if offer["seller_id"] != caller["user_id"]:
        _err(403, "PERMISSION_DENIED", "Only the seller can respond to this offer")
    if offer["status"] != "pending":
        _err(409, "OFFER_NOT_PENDING",
             f"Offer is already {offer['status']} — no further action possible",
             status=offer["status"])
    if body.action == "counter" and not body.counter_amount:
        _err(400, "COUNTER_AMOUNT_REQUIRED", "counter_amount is required when action is 'counter'")

    status_map = {"accept": "accepted", "reject": "rejected", "counter": "countered"}
    new_status = status_map[body.action]

    row = await db.fetchrow(
        """UPDATE offers SET status=$1, counter_amount=$2, counter_message=$3,
           responded_by=$4, responded_at=NOW() WHERE id=$5 RETURNING *""",
        new_status,
        float(body.counter_amount) if body.counter_amount else None,
        body.message, body.responded_by, offer_id,
    )

    if body.action == "accept":
        await db.execute("UPDATE listings SET status='sold' WHERE id=$1", offer["listing_id"])
    elif body.action == "reject":
        await db.execute(
            "UPDATE listings SET status='active' WHERE id=$1 AND status='pending'",
            offer["listing_id"],
        )

    event_data = {
        "offer_id": str(offer_id),
        "listing_id": str(offer["listing_id"]),
        "listing_title": offer["title"],
        "status": new_status,
        "amount": float(offer["amount"]),
    }
    if body.action == "counter":
        event_data["counter_amount"] = float(body.counter_amount)

    await events_bus.emit_many(
        [str(offer["buyer_id"]), str(caller["user_id"])],
        f"offer_{new_status}",
        event_data,
    )

    return await _offer_response(row, caller["user_id"])


# ── Messages ──────────────────────────────────────────────────────────────────

@app.get("/listings/{listing_id}/messages", response_model=list[MessageResponse])
async def get_messages(listing_id: UUID, caller=Depends(current_user)):
    rows = await db.fetch(
        """SELECT m.* FROM messages m WHERE m.listing_id=$1
           AND (m.sender_id=$2 OR m.recipient_id=$2) ORDER BY m.created_at ASC""",
        listing_id, caller["user_id"],
    )
    await db.execute(
        "UPDATE messages SET read_at=NOW() WHERE listing_id=$1 AND recipient_id=$2 AND read_at IS NULL",
        listing_id, caller["user_id"],
    )
    return [await _message_response(r) for r in rows]


@app.post("/listings/{listing_id}/messages", response_model=MessageResponse, status_code=201)
async def send_message(listing_id: UUID, body: SendMessageRequest, caller=Depends(current_user)):
    if not caller["can_message"]:
        _err(403, "PERMISSION_DENIED", "Agent session does not have messaging permission")

    listing = await db.fetchrow("SELECT seller_id, title FROM listings WHERE id=$1", listing_id)
    if not listing:
        _err(404, "LISTING_NOT_FOUND", "No listing with that ID")

    recipient_id = listing["seller_id"] if listing["seller_id"] != caller["user_id"] else None
    if not recipient_id:
        _err(400, "SELF_MESSAGE", "Cannot send a message to yourself")

    row = await db.fetchrow(
        "INSERT INTO messages (listing_id, sender_id, recipient_id, body, sent_by) VALUES ($1,$2,$3,$4,$5) RETURNING *",
        listing_id, caller["user_id"], recipient_id, body.body, body.sent_by,
    )

    sender = await db.fetchrow("SELECT display_name FROM users WHERE id=$1", caller["user_id"])
    await events_bus.emit(str(recipient_id), "message_received", {
        "listing_id": str(listing_id),
        "listing_title": listing["title"],
        "from": sender["display_name"] if sender else "Someone",
        "preview": body.body[:120],
    })

    return await _message_response(row)


# ── Dev helpers ───────────────────────────────────────────────────────────────

@app.get("/dev/users")
async def dev_users():
    rows = await db.fetch(
        "SELECT id, display_name FROM users ORDER BY created_at DESC LIMIT 50"
    )
    return [{"id": str(r["id"]), "display_name": r["display_name"]} for r in rows]


# ── My listings / offers ──────────────────────────────────────────────────────

@app.get("/me/listings", response_model=list[ListingResponse])
async def my_listings(status: str = "active", caller=Depends(current_user)):
    q = "SELECT * FROM listings WHERE seller_id=$1"
    args = [caller["user_id"]]
    if status != "all":
        args.append(status)
        q += f" AND status=${len(args)}"
    q += " ORDER BY updated_at DESC LIMIT 100"
    rows = await db.fetch(q, *args)
    return [await _listing_response(r, caller["user_id"]) for r in rows]


@app.get("/me/offers", response_model=list[OfferResponse])
async def my_offers(direction: str = "all", caller=Depends(current_user)):
    if direction == "sent":
        rows = await db.fetch(
            "SELECT * FROM offers WHERE buyer_id=$1 ORDER BY created_at DESC LIMIT 50",
            caller["user_id"],
        )
    elif direction == "received":
        rows = await db.fetch(
            "SELECT o.* FROM offers o JOIN listings l ON l.id=o.listing_id WHERE l.seller_id=$1 ORDER BY o.created_at DESC LIMIT 50",
            caller["user_id"],
        )
    else:
        rows = await db.fetch(
            "SELECT o.* FROM offers o LEFT JOIN listings l ON l.id=o.listing_id WHERE o.buyer_id=$1 OR l.seller_id=$1 ORDER BY o.created_at DESC LIMIT 50",
            caller["user_id"],
        )
    return [await _offer_response(r, caller["user_id"]) for r in rows]


# ── AI / Drafts ───────────────────────────────────────────────────────────────

_AI_DAILY_CAP    = int(os.environ.get("AI_DAILY_CAP", "200"))
_AI_FREE_MONTHLY = int(os.environ.get("AI_FREE_MONTHLY", "20"))


async def _check_caps(user_id):
    global_count = await db.fetchval(
        "SELECT COUNT(*) FROM ai_usage_log WHERE created_at >= CURRENT_DATE"
    )
    if global_count >= _AI_DAILY_CAP:
        _err(429, "DAILY_CAP_REACHED", "Global daily AI limit reached — try again tomorrow",
             resets_at="midnight UTC")
    if user_id:
        monthly = await db.fetchval(
            "SELECT COUNT(*) FROM ai_usage_log WHERE user_id=$1 AND created_at >= date_trunc('month', NOW())",
            user_id,
        )
        if monthly >= _AI_FREE_MONTHLY:
            from datetime import date
            next_month = date.today().replace(day=1)
            _err(429, "AI_MONTHLY_LIMIT",
                 f"Used all {_AI_FREE_MONTHLY} free AI listings this month",
                 used=int(monthly), limit=_AI_FREE_MONTHLY,
                 resets_at=f"{next_month.year}-{next_month.month + 1:02d}-01")


async def _generate_draft_background(draft_id, user_id, photo_urls, description, price_hint, location_text, confirmed_brand=None):
    print(f"[generate] starting draft {draft_id} for user {user_id}")
    try:
        await asyncio.wait_for(
            _do_generate(draft_id, user_id, photo_urls, description, price_hint, location_text, confirmed_brand),
            timeout=240,
        )
        print(f"[generate] done draft {draft_id}")
    except asyncio.TimeoutError:
        print(f"[generate] timeout draft {draft_id}")
        await db.execute(
            "UPDATE listing_drafts SET status='failed', error='Generation timed out', updated_at=NOW() WHERE id=$1",
            draft_id,
        )
        if user_id:
            await events_bus.emit(str(user_id), "draft_failed", {
                "draft_id": str(draft_id),
                "error": "Generation timed out",
            })
        tg_row = await db.fetchrow(
            "SELECT telegram_chat_id FROM listing_drafts WHERE id=$1", draft_id
        )
        if tg_row and tg_row["telegram_chat_id"]:
            await send_telegram(tg_row["telegram_chat_id"],
                "Sorry, it's taking too long to generate your listing. Please try again.")


async def _do_generate(draft_id, user_id, photo_urls, description, price_hint, location_text, confirmed_brand=None):
    try:
        print(f"[generate] calling LLM for draft {draft_id}")
        draft_data = await generate_listing_draft(
            description=description,
            price_hint=price_hint,
            location=location_text,
            photo_urls=photo_urls,
            confirmed_brand=confirmed_brand,
        )
        draft_data["photo_urls"] = photo_urls or []
        await db.execute(
            "UPDATE listing_drafts SET status='ready', draft=$1, updated_at=NOW() WHERE id=$2",
            json.dumps(draft_data), draft_id,
        )
        await db.execute(
            "INSERT INTO ai_usage_log (endpoint, user_id) VALUES ('generate', $1)", user_id,
        )
        if user_id:
            await events_bus.emit(str(user_id), "draft_ready", {
                "draft_id": str(draft_id),
                "title": draft_data["title"],
                "suggested_price": draft_data["suggested_price"],
                "condition": draft_data["condition"],
                "category_id": draft_data["category_id"],
            })
        # Notify seller via Telegram if this draft was initiated there
        tg_row = await db.fetchrow(
            "SELECT telegram_chat_id FROM listing_drafts WHERE id=$1", draft_id
        )
        if tg_row and tg_row["telegram_chat_id"]:
            price = draft_data["suggested_price"]
            title = draft_data["title"]
            await send_telegram(
                tg_row["telegram_chat_id"],
                f"Your listing is ready!\n\n\"{title}\" — ${price:.0f}\n\nReply YES to publish, or NO to cancel."
            )
    except Exception as e:
        await db.execute(
            "UPDATE listing_drafts SET status='failed', error=$1, updated_at=NOW() WHERE id=$2",
            str(e)[:500], draft_id,
        )
        if user_id:
            await events_bus.emit(str(user_id), "draft_failed", {
                "draft_id": str(draft_id),
                "error": str(e)[:200],
            })
        tg_row = await db.fetchrow(
            "SELECT telegram_chat_id FROM listing_drafts WHERE id=$1", draft_id
        )
        if tg_row and tg_row["telegram_chat_id"]:
            await send_telegram(
                tg_row["telegram_chat_id"],
                "Sorry, something went wrong generating your listing. Please try again."
            )


@app.post("/ai/generate", response_model=GenerateJobResponse, status_code=202)
async def generate_listing(body: GenerateListingRequest, authorization: Optional[str] = Header(None)):
    """
    Async listing generation. Returns draft_id immediately.
    Subscribe to GET /events to receive draft_ready or draft_failed event.
    """
    user_id = None
    if authorization:
        token = authorization.removeprefix("Bearer ").strip()
        u = await db.fetchrow("SELECT id FROM users WHERE id::text = $1", token)
        if u:
            user_id = u["id"]

    await _check_caps(user_id)

    loc_text = body.location.text if body.location else None
    draft_id = await db.fetchval(
        """INSERT INTO listing_drafts (user_id, status, description, price_hint,
                                       location_lat, location_lng, location_text)
           VALUES ($1,'processing',$2,$3,$4,$5,$6) RETURNING id""",
        user_id, body.description, body.price_hint,
        body.location.lat if body.location else None,
        body.location.lng if body.location else None,
        loc_text,
    )

    asyncio.create_task(_generate_draft_background(
        draft_id, user_id, body.photo_urls,
        body.description, body.price_hint, loc_text,
    ))

    return GenerateJobResponse(draft_id=draft_id)


# ── Telegram webhook ─────────────────────────────────────────────────────────

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """
    Telegram Bot webhook. Seller sends photo + caption → brand confidence check → listing.
    Brand ladder: HIGH = proceed silently, MEDIUM/LOW = ask seller to confirm, NONE = ask brand.
    Reply YES to publish, NO to cancel. Numeric reply or text to confirm brand.
    """
    data = await request.json()
    msg = data.get("message") or data.get("edited_message")
    if not msg:
        return {"ok": True}

    chat_id: int = msg["chat"]["id"]
    text: str = (msg.get("text") or msg.get("caption") or "").strip()
    photos = msg.get("photo")  # list of sizes, largest last

    async def reply(t: str) -> None:
        await send_telegram(chat_id, t)

    # Look up or auto-register seller by Telegram chat_id
    tg_row = await db.fetchrow(
        "SELECT user_id FROM telegram_accounts WHERE chat_id=$1", chat_id
    )
    if not tg_row:
        first_name = msg.get("from", {}).get("first_name", "Seller")
        user_id = await db.fetchval(
            "INSERT INTO users (display_name) VALUES ($1) RETURNING id", first_name,
        )
        await db.execute(
            "INSERT INTO telegram_accounts (chat_id, user_id, first_name) VALUES ($1,$2,$3)",
            chat_id, user_id, first_name,
        )
        await reply(
            f"Welcome to Agora, {first_name}! Send me a photo of what you want to sell with a short description."
        )
        return {"ok": True}

    user_id = tg_row["user_id"]

    # ── YES / NO (for ready drafts) ────────────────────────────────────────────
    if text.upper() in ("YES", "Y", "PUBLISH"):
        draft = await db.fetchrow(
            "SELECT id FROM listing_drafts WHERE user_id=$1 AND status='ready' AND telegram_chat_id=$2 "
            "ORDER BY created_at DESC LIMIT 1",
            user_id, chat_id,
        )
        if not draft:
            await reply("No listing ready to publish. Send me a photo of what you want to sell!")
            return {"ok": True}
        listing = await _publish_draft_internal(draft["id"], user_id)
        url = f"{_WEB_URL}/listings/{listing['id']}" if listing else _WEB_URL
        await reply(f"You're live!\n{url}")
        return {"ok": True}

    if text.upper() in ("NO", "N", "CANCEL"):
        await db.execute(
            "UPDATE listing_drafts SET status='failed', error='Cancelled by seller', updated_at=NOW() "
            "WHERE user_id=$1 AND status IN ('ready','awaiting_brand') AND telegram_chat_id=$2",
            user_id, chat_id,
        )
        await reply("Listing cancelled. Send me a photo when you're ready to sell something.")
        return {"ok": True}

    if text.upper() in ("ACCEPT",):
        offer = await db.fetchrow(
            "SELECT o.*, l.title FROM offers o JOIN listings l ON l.id=o.listing_id "
            "WHERE l.seller_id=$1 AND o.status='pending' ORDER BY o.created_at DESC LIMIT 1",
            user_id,
        )
        if not offer:
            await reply("No pending offers to accept.")
            return {"ok": True}
        await db.execute("UPDATE offers SET status='accepted', responded_at=NOW() WHERE id=$1", offer["id"])
        await db.execute("UPDATE listings SET status='sold' WHERE id=$1", offer["listing_id"])
        buyer = await db.fetchrow("SELECT display_name FROM users WHERE id=$1", offer["buyer_id"])
        await events_bus.emit_many(
            [str(offer["buyer_id"]), str(user_id)], "offer_accepted",
            {"offer_id": str(offer["id"]), "listing_id": str(offer["listing_id"]),
             "listing_title": offer["title"], "status": "accepted", "amount": float(offer["amount"])},
        )
        await reply(f'Sold! "{offer["title"]}" to {buyer["display_name"] if buyer else "buyer"} for ${float(offer["amount"]):.0f}.')
        return {"ok": True}

    if text.upper() in ("DECLINE", "REJECT"):
        offer = await db.fetchrow(
            "SELECT o.*, l.title FROM offers o JOIN listings l ON l.id=o.listing_id "
            "WHERE l.seller_id=$1 AND o.status='pending' ORDER BY o.created_at DESC LIMIT 1",
            user_id,
        )
        if not offer:
            await reply("No pending offers to decline.")
            return {"ok": True}
        await db.execute("UPDATE offers SET status='rejected', responded_at=NOW() WHERE id=$1", offer["id"])
        await db.execute("UPDATE listings SET status='active' WHERE id=$1 AND status='pending'", offer["listing_id"])
        await events_bus.emit(str(offer["buyer_id"]), "offer_rejected",
            {"offer_id": str(offer["id"]), "listing_id": str(offer["listing_id"]),
             "listing_title": offer["title"], "status": "rejected", "amount": float(offer["amount"])},
        )
        await reply(f'Offer declined. "{offer["title"]}" is back to active.')
        return {"ok": True}

    # ── Brand reply (if awaiting_brand draft exists and no photo in message) ───
    if not photos:
        awaiting = await db.fetchrow(
            "SELECT id, brand_candidates, description, price_hint, location_text, photo_urls "
            "FROM listing_drafts WHERE user_id=$1 AND status='awaiting_brand' AND telegram_chat_id=$2 "
            "ORDER BY created_at DESC LIMIT 1",
            user_id, chat_id,
        )
        if awaiting:
            candidates = awaiting["brand_candidates"] or []
            if isinstance(candidates, str):
                candidates = json.loads(candidates)

            t = text.strip()
            if not t:
                await reply("Please reply with a number, the brand name, or SKIP")
                return {"ok": True}

            if t.isdigit():
                idx = int(t) - 1
                if 0 <= idx < len(candidates):
                    confirmed_brand: str | None = candidates[idx]
                else:
                    await reply(f"Please reply 1–{len(candidates)}, type the brand name, or SKIP")
                    return {"ok": True}
            elif t.upper() == "SKIP":
                confirmed_brand = None
            else:
                confirmed_brand = t  # treat message as brand override

            stored_urls = awaiting["photo_urls"] or []
            if isinstance(stored_urls, str):
                stored_urls = json.loads(stored_urls)

            await db.execute(
                "UPDATE listing_drafts SET status='processing', confirmed_brand=$1 WHERE id=$2",
                confirmed_brand, awaiting["id"],
            )

            brand_msg = f"Got it — using {confirmed_brand}! " if confirmed_brand else "OK, I'll figure it out! "
            await reply(f"{brand_msg}Writing your listing now — I'll message you in ~1 minute.")

            asyncio.create_task(_generate_draft_background(
                awaiting["id"], user_id,
                stored_urls,
                awaiting["description"],
                awaiting["price_hint"],
                awaiting["location_text"],
                confirmed_brand=confirmed_brand,
            ))
            return {"ok": True}

    # ── New listing ────────────────────────────────────────────────────────────

    # Download photo if present
    photo_bytes: bytes | None = None
    if photos and _TG_TOKEN:
        largest = photos[-1]["file_id"]
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(
                    f"https://api.telegram.org/bot{_TG_TOKEN}/getFile",
                    params={"file_id": largest},
                )
                file_path = r.json()["result"]["file_path"]
                r2 = await client.get(
                    f"https://api.telegram.org/file/bot{_TG_TOKEN}/{file_path}"
                )
                if r2.status_code == 200:
                    photo_bytes = r2.content
        except Exception:
            pass

    if not text and not photo_bytes:
        await reply("Send me a photo of what you want to sell, with a short description!")
        return {"ok": True}

    description = text or "Item for sale"

    # Upload to storage immediately
    photo_url: str | None = None
    photo_b64s: list[str] = []
    if photo_bytes:
        photo_url = await upload_photo(photo_bytes)
        photo_b64s = [base64.b64encode(photo_bytes).decode()]

    photo_urls_list = [photo_url] if photo_url else []

    # Vision analysis — enrich description so brand search is more accurate
    vision_caption = ""
    if photo_b64s:
        try:
            vision_caption = await analyze_photos(photo_b64s)
            description = f"{text}\n\nPhotos show: {vision_caption}" if text else f"Photos show: {vision_caption}"
        except Exception:
            pass

    # Brand confidence analysis
    candidates, confidence = await analyze_brand(description, vision_caption)
    print(f"[brand] confidence={confidence} candidates={candidates[:3]}")

    if confidence == "HIGH":
        confirmed_brand = candidates[0]
        draft_id = await db.fetchval(
            """INSERT INTO listing_drafts
                 (user_id, status, description, telegram_chat_id, photo_urls, confirmed_brand)
               VALUES ($1,'processing',$2,$3,$4,$5) RETURNING id""",
            user_id, description, chat_id, json.dumps(photo_urls_list), confirmed_brand,
        )
        asyncio.create_task(_generate_draft_background(
            draft_id, user_id, photo_urls_list, description, None, None,
            confirmed_brand=confirmed_brand,
        ))
        await reply(f"Got it — I see this is a {confirmed_brand} item. Writing your listing now, I'll message you in ~1 minute.")
    else:
        draft_id = await db.fetchval(
            """INSERT INTO listing_drafts
                 (user_id, status, description, telegram_chat_id, photo_urls, brand_candidates)
               VALUES ($1,'awaiting_brand',$2,$3,$4,$5) RETURNING id""",
            user_id, description, chat_id,
            json.dumps(photo_urls_list), json.dumps(candidates),
        )
        if candidates:
            options = "\n".join(f"{i+1}. {b}" for i, b in enumerate(candidates))
            if confidence == "MEDIUM":
                msg = f"I think this might be one of these brands:\n{options}\n\nReply 1–{len(candidates)} to confirm, type the brand name, or SKIP to let me decide."
            else:
                msg = f"What brand is this?\n{options}\n\nReply 1–{len(candidates)}, type the brand name, or SKIP."
        else:
            msg = "What brand is this? Type the brand name (e.g. 'Nike', 'Apple') or SKIP to let me figure it out."
        await reply(msg)

    return {"ok": True}


async def _publish_draft_internal(draft_id: UUID, user_id: UUID):
    """Publish a ready draft — shared by web endpoint and SMS YES reply. Returns listing row."""
    row = await db.fetchrow("SELECT * FROM listing_drafts WHERE id=$1", draft_id)
    if not row or row["status"] != "ready":
        return None
    d = row["draft"] if isinstance(row["draft"], dict) else json.loads(row["draft"])
    _vec = await embed_text(f"{d['title']} {d.get('description', '')} {d.get('category_id', '')}")
    embedding = "[" + ",".join(str(x) for x in _vec) + "]"
    listing = await db.fetchrow(
        """INSERT INTO listings
             (seller_id, title, description, category_id, condition, attributes,
              price, price_negotiable, lat, lng, location_text, listed_by, embedding)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'agent',$12) RETURNING *""",
        user_id, d["title"], d["description"], d["category_id"],
        d["condition"], d.get("attributes", {}), float(d["suggested_price"]),
        d.get("price_negotiable", True), 0.0, 0.0, "",
        embedding,
    )
    photo_urls = d.get("photo_urls") or []
    if photo_urls:
        await db.executemany(
            "INSERT INTO listing_photos (listing_id, url, position) VALUES ($1,$2,$3)",
            [(listing["id"], url, i) for i, url in enumerate(photo_urls)],
        )
    await db.execute(
        "UPDATE listing_drafts SET status='published', updated_at=NOW() WHERE id=$1", draft_id
    )
    await events_bus.emit(str(user_id), "listing_live", {
        "listing_id": str(listing["id"]),
        "title": d["title"],
        "price": float(d["suggested_price"]),
    })
    return listing


@app.get("/drafts/{draft_id}", response_model=DraftResponse)
async def get_draft(draft_id: UUID):
    row = await db.fetchrow("SELECT * FROM listing_drafts WHERE id=$1", draft_id)
    if not row:
        _err(404, "DRAFT_NOT_FOUND", "No draft with that ID")
    return DraftResponse(
        id=row["id"], status=row["status"],
        draft=(row["draft"] if isinstance(row["draft"], dict) else json.loads(row["draft"])) if row["draft"] else None,
        error=row["error"], created_at=row["created_at"],
    )


@app.post("/drafts/{draft_id}/publish", response_model=ListingResponse, status_code=201)
async def publish_draft(draft_id: UUID, caller=Depends(current_user)):
    row = await db.fetchrow("SELECT * FROM listing_drafts WHERE id=$1", draft_id)
    if not row:
        _err(404, "DRAFT_NOT_FOUND", "No draft with that ID")
    if row["status"] != "ready":
        _err(409, "DRAFT_NOT_READY",
             f"Draft is '{row['status']}', must be 'ready' to publish",
             draft_status=row["status"])

    listing = await _publish_draft_internal(draft_id, caller["user_id"])
    return await _listing_response(listing, caller["user_id"])


# ── Notifications (legacy — prefer SSE stream) ────────────────────────────────

@app.get("/me/notifications", response_model=list[NotificationResponse])
async def get_notifications(caller=Depends(current_user)):
    rows = await db.fetch(
        "SELECT * FROM notifications WHERE user_id=$1 ORDER BY created_at DESC LIMIT 30",
        caller["user_id"],
    )
    return [NotificationResponse(
        id=r["id"], type=r["type"], title=r["title"], body=r["body"],
        action_type=r["action_type"], action_url=r["action_url"],
        payload=(r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"])) if r["payload"] else {},
        read_at=r["read_at"], created_at=r["created_at"],
    ) for r in rows]


@app.patch("/me/notifications/{notification_id}/read", status_code=204)
async def mark_notification_read(notification_id: UUID, caller=Depends(current_user)):
    await db.execute(
        "UPDATE notifications SET read_at=NOW() WHERE id=$1 AND user_id=$2",
        notification_id, caller["user_id"],
    )


@app.get("/me/usage")
async def get_usage(caller=Depends(current_user)):
    monthly = await db.fetchval(
        "SELECT COUNT(*) FROM ai_usage_log WHERE user_id=$1 AND created_at >= date_trunc('month', NOW())",
        caller["user_id"],
    )
    return {
        "used": int(monthly),
        "limit": _AI_FREE_MONTHLY,
        "remaining": max(0, _AI_FREE_MONTHLY - int(monthly)),
    }


@app.post("/ai/analyze-photo")
async def analyze_photo(request: Request, file: UploadFile = File(...)):
    contents = await file.read()
    import base64
    b64 = base64.b64encode(contents).decode()
    caption = await analyze_photos([b64])
    return {"caption": caption}


# ── Response builders ─────────────────────────────────────────────────────────

def _listing_state(row, viewer_id) -> dict:
    status = row["status"]
    is_owner = viewer_id and str(viewer_id) == str(row["seller_id"])
    if status == "active" and not is_owner:
        actions = ["make_offer", "send_message"]
    elif status == "active" and is_owner:
        actions = ["update", "delete"]
    elif status == "pending" and is_owner:
        actions = ["view_offers"]
    else:
        actions = []
    return {
        "valid_actions": actions,
        "days_listed": (datetime.now(timezone.utc) - row["created_at"].replace(tzinfo=timezone.utc)).days,
        "views": row["views"],
    }


def _offer_state(row, caller_id) -> dict:
    status = row["status"]
    is_buyer = str(caller_id) == str(row["buyer_id"])
    if status == "pending":
        actions = ["withdraw"] if is_buyer else ["accept", "reject", "counter"]
    elif status == "countered" and is_buyer:
        actions = ["accept", "reject", "withdraw"]
    else:
        actions = []
    expires_at = row.get("expires_at")
    expires_in = None
    if expires_at:
        diff = expires_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
        expires_in = max(0, int(diff.total_seconds()))
    return {
        "valid_actions": actions,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "expires_in_seconds": expires_in,
    }


async def _listing_responses_bulk(rows, viewer_id) -> list[ListingResponse]:
    """Fetch photos + sellers in 2 queries instead of 2×N."""
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    seller_ids = list({row["seller_id"] for row in rows})

    all_photos = await db.fetch(
        "SELECT listing_id, url FROM listing_photos WHERE listing_id = ANY($1) ORDER BY listing_id, position",
        ids,
    )
    photos_by_id: dict[str, list[str]] = {}
    for p in all_photos:
        photos_by_id.setdefault(str(p["listing_id"]), []).append(p["url"])

    sellers = await db.fetch("SELECT * FROM users WHERE id = ANY($1)", seller_ids)
    sellers_by_id = {str(s["id"]): s for s in sellers}

    results = []
    for row in rows:
        attrs = row["attributes"]
        if attrs and not isinstance(attrs, dict):
            attrs = json.loads(attrs)
        seller = sellers_by_id.get(str(row["seller_id"]))
        results.append(ListingResponse(
            id=row["id"], title=row["title"], description=row["description"],
            price=row["price"], condition=row["condition"], category_id=row["category_id"],
            attributes=attrs or {},
            location=Location(lat=row["lat"], lng=row["lng"], text=row["location_text"]),
            status=row["status"], price_negotiable=row["price_negotiable"],
            photos=photos_by_id.get(str(row["id"]), []),
            seller=_user_summary(seller) if seller else _user_summary({"id": row["seller_id"], "display_name": "Unknown", "avatar_url": None, "trust_score": 0.5, "sold_total": 0, "avg_rating": None, "phone_verified": False}),
            listed_by=row["listed_by"],
            views=row["views"], created_at=row["created_at"], updated_at=row["updated_at"],
            state=_listing_state(row, viewer_id),
        ))
    return results


async def _listing_response(row, viewer_id) -> ListingResponse:
    photos = await db.fetch(
        "SELECT url FROM listing_photos WHERE listing_id=$1 ORDER BY position", row["id"]
    )
    seller = await db.fetchrow("SELECT * FROM users WHERE id=$1", row["seller_id"])
    attrs = row["attributes"]
    if attrs and not isinstance(attrs, dict):
        attrs = json.loads(attrs)
    return ListingResponse(
        id=row["id"], title=row["title"], description=row["description"],
        price=row["price"], condition=row["condition"], category_id=row["category_id"],
        attributes=attrs or {},
        location=Location(lat=row["lat"], lng=row["lng"], text=row["location_text"]),
        status=row["status"], price_negotiable=row["price_negotiable"],
        photos=[p["url"] for p in photos],
        seller=_user_summary(seller), listed_by=row["listed_by"],
        views=row["views"], created_at=row["created_at"], updated_at=row["updated_at"],
        state=_listing_state(row, viewer_id),
    )


async def _offer_response(row, caller_id) -> OfferResponse:
    buyer = await db.fetchrow("SELECT * FROM users WHERE id=$1", row["buyer_id"])
    return OfferResponse(
        id=row["id"], listing_id=row["listing_id"],
        buyer=_user_summary(buyer), amount=row["amount"],
        message=row["message"], status=row["status"],
        counter_amount=row["counter_amount"], counter_message=row["counter_message"],
        offered_by=row["offered_by"], responded_by=row["responded_by"],
        created_at=row["created_at"], expires_at=row["expires_at"],
        responded_at=row["responded_at"],
        state=_offer_state(row, caller_id) if caller_id else None,
    )


async def _message_response(row) -> MessageResponse:
    sender = await db.fetchrow("SELECT * FROM users WHERE id=$1", row["sender_id"])
    return MessageResponse(
        id=row["id"], sender=_user_summary(sender), body=row["body"],
        sent_by=row["sent_by"], read_at=row["read_at"], created_at=row["created_at"],
    )


def _user_summary(row) -> UserSummary:
    return UserSummary(
        id=row["id"], display_name=row["display_name"], avatar_url=row["avatar_url"],
        trust_score=float(row["trust_score"] or 0.5), sold_total=row["sold_total"],
        avg_rating=float(row["avg_rating"]) if row["avg_rating"] else None,
        phone_verified=row["phone_verified"],
    )
