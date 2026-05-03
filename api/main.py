"""
Agora Marketplace API

All routes return structured JSON — designed to be consumed by agents and humans alike.
Auth: Bearer token in Authorization header (user JWT or agent session token).
"""

from __future__ import annotations
import os
from contextlib import asynccontextmanager
from typing import Optional
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from api import db
from api.models import (
    CreateListingRequest, UpdateListingRequest, ListingResponse,
    SearchRequest, SearchResponse, SearchResult,
    CreateOfferRequest, RespondOfferRequest, OfferResponse,
    SendMessageRequest, MessageResponse,
    GenerateListingRequest, GenerateListingResponse,
    UserSummary, Location,
)
from ai.generate import generate_listing_draft, analyze_photos
from ai.embed import embed_text
from ai.moderate import moderate_listing


# ── App setup ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    yield
    await db.close_pool()


app = FastAPI(
    title="Agora Marketplace API",
    description="Agent-native local marketplace. Buy, sell, negotiate — human or AI.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth ──────────────────────────────────────────────────────────────────────

async def current_user(authorization: Optional[str] = Header(None)) -> dict:
    """
    Resolve the caller from a Bearer token.
    Returns user dict with id, agent_session_id (if agent), permissions.
    Dev shortcut: pass X-Dev-User-Id header to skip auth.
    """
    if not authorization:
        raise HTTPException(401, "Authorization header required")

    token = authorization.removeprefix("Bearer ").strip()

    # Check agent sessions first
    row = await db.fetchrow(
        """
        SELECT s.id as session_id, s.user_id, s.can_list, s.can_offer,
               s.can_message, s.max_offer, u.display_name
        FROM agent_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = crypt($1, s.token_hash)
          AND (s.expires_at IS NULL OR s.expires_at > NOW())
        """,
        token,
    )
    if row:
        await db.execute(
            "UPDATE agent_sessions SET last_used_at = NOW() WHERE id = $1",
            row["session_id"],
        )
        return {
            "user_id": row["user_id"],
            "agent_session_id": row["session_id"],
            "is_agent": True,
            "can_list": row["can_list"],
            "can_offer": row["can_offer"],
            "can_message": row["can_message"],
            "max_offer": row["max_offer"],
        }

    # Fall back to user JWT (simplified — swap for real JWT lib in prod)
    user = await db.fetchrow(
        "SELECT id, display_name FROM users WHERE id::text = $1", token
    )
    if not user:
        raise HTTPException(401, "Invalid token")

    return {
        "user_id": user["id"],
        "agent_session_id": None,
        "is_agent": False,
        "can_list": True,
        "can_offer": True,
        "can_message": True,
        "max_offer": None,
    }


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/")
async def health():
    return {"status": "ok", "service": "agora-marketplace"}


# ── Listings ──────────────────────────────────────────────────────────────────

@app.post("/listings", response_model=ListingResponse, status_code=201)
async def create_listing(body: CreateListingRequest, caller=Depends(current_user)):
    if not caller["can_list"]:
        raise HTTPException(403, "This agent session does not have listing permission")

    # Moderate content before publishing
    mod = await moderate_listing(body.title, body.description, body.category_id)
    if not mod["allowed"]:
        raise HTTPException(422, f"Listing rejected: {mod['reason']}")

    # Generate semantic embedding
    embedding = await embed_text(f"{body.title} {body.description} {body.category_id}")

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
        raise HTTPException(404, "Listing not found")
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
        raise HTTPException(404, "Listing not found")
    if row["seller_id"] != caller["user_id"]:
        raise HTTPException(403, "Not your listing")

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
        raise HTTPException(404)
    if row["seller_id"] != caller["user_id"]:
        raise HTTPException(403, "Not your listing")
    await db.execute("UPDATE listings SET status = 'removed' WHERE id = $1", listing_id)


# ── Search ────────────────────────────────────────────────────────────────────

@app.post("/search", response_model=SearchResponse)
async def search(body: SearchRequest):
    """
    Hybrid search: semantic vector similarity + structured filters.
    Agents should use this with natural language queries.
    """
    embedding = await embed_text(body.query)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    # Build filter clauses
    filters, vals = ["l.status = 'active'"], [embedding_str]

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

    # Add location params once (used in both filter and select)
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
        SELECT l.*,
               COALESCE(1 - (l.embedding <=> $1::vector), 0) AS score,
               {dist_expr} AS distance_mi
        FROM listings l
        WHERE {where}
        ORDER BY COALESCE(1 - (l.embedding <=> $1::vector), 0) DESC
        LIMIT {body.limit} OFFSET {body.offset}
        """,
        *vals,
    )

    results = []
    for row in rows:
        listing = await _listing_response(row, None)
        results.append(SearchResult(
            listing=listing,
            score=float(row["score"] or 0),
            distance_mi=float(row["distance_mi"]) if row.get("distance_mi") else None,
        ))

    return SearchResponse(results=results, total=len(results), query=body.query)


# ── Offers ────────────────────────────────────────────────────────────────────

@app.post("/listings/{listing_id}/offers", response_model=OfferResponse, status_code=201)
async def make_offer(listing_id: UUID, body: CreateOfferRequest, caller=Depends(current_user)):
    if not caller["can_offer"]:
        raise HTTPException(403, "This agent session does not have offer permission")
    if caller["max_offer"] and float(body.amount) > float(caller["max_offer"]):
        raise HTTPException(403, f"Offer ${body.amount} exceeds agent limit ${caller['max_offer']}")

    listing = await db.fetchrow(
        "SELECT seller_id, status, price FROM listings WHERE id = $1", listing_id
    )
    if not listing:
        raise HTTPException(404, "Listing not found")
    if listing["status"] != "active":
        raise HTTPException(409, "Listing is not available")
    if listing["seller_id"] == caller["user_id"]:
        raise HTTPException(400, "Can't offer on your own listing")

    row = await db.fetchrow(
        """
        INSERT INTO offers (listing_id, buyer_id, amount, message, offered_by)
        VALUES ($1, $2, $3, $4, $5) RETURNING *
        """,
        listing_id, caller["user_id"], float(body.amount), body.message, body.offered_by,
    )

    await db.execute(
        "UPDATE listings SET status = 'pending' WHERE id = $1 AND status = 'active'",
        listing_id,
    )
    return await _offer_response(row)


@app.get("/listings/{listing_id}/offers", response_model=list[OfferResponse])
async def list_offers(listing_id: UUID, caller=Depends(current_user)):
    listing = await db.fetchrow("SELECT seller_id FROM listings WHERE id = $1", listing_id)
    if not listing:
        raise HTTPException(404)
    if listing["seller_id"] != caller["user_id"]:
        raise HTTPException(403, "Only seller can view offers")

    rows = await db.fetch(
        "SELECT * FROM offers WHERE listing_id = $1 ORDER BY created_at DESC", listing_id
    )
    return [await _offer_response(r) for r in rows]


@app.patch("/offers/{offer_id}", response_model=OfferResponse)
async def respond_to_offer(offer_id: UUID, body: RespondOfferRequest, caller=Depends(current_user)):
    offer = await db.fetchrow(
        """
        SELECT o.*, l.seller_id FROM offers o
        JOIN listings l ON l.id = o.listing_id
        WHERE o.id = $1
        """,
        offer_id,
    )
    if not offer:
        raise HTTPException(404)
    if offer["seller_id"] != caller["user_id"]:
        raise HTTPException(403, "Only seller can respond")
    if offer["status"] != "pending":
        raise HTTPException(409, f"Offer is already {offer['status']}")
    if body.action == "counter" and not body.counter_amount:
        raise HTTPException(400, "counter_amount required when countering")

    status_map = {"accept": "accepted", "reject": "rejected", "counter": "countered"}
    row = await db.fetchrow(
        """
        UPDATE offers
        SET status = $1, counter_amount = $2, counter_message = $3,
            responded_by = $4, responded_at = NOW()
        WHERE id = $5 RETURNING *
        """,
        status_map[body.action],
        float(body.counter_amount) if body.counter_amount else None,
        body.message,
        body.responded_by,
        offer_id,
    )

    if body.action == "accept":
        await db.execute(
            "UPDATE listings SET status = 'sold' WHERE id = $1", offer["listing_id"]
        )
    elif body.action == "reject":
        await db.execute(
            "UPDATE listings SET status = 'active' WHERE id = $1 AND status = 'pending'",
            offer["listing_id"],
        )

    return await _offer_response(row)


# ── Messages ──────────────────────────────────────────────────────────────────

@app.get("/listings/{listing_id}/messages", response_model=list[MessageResponse])
async def get_messages(listing_id: UUID, caller=Depends(current_user)):
    rows = await db.fetch(
        """
        SELECT m.* FROM messages m
        WHERE m.listing_id = $1
          AND (m.sender_id = $2 OR m.recipient_id = $2)
        ORDER BY m.created_at ASC
        """,
        listing_id, caller["user_id"],
    )
    await db.execute(
        """
        UPDATE messages SET read_at = NOW()
        WHERE listing_id = $1 AND recipient_id = $2 AND read_at IS NULL
        """,
        listing_id, caller["user_id"],
    )
    return [await _message_response(r) for r in rows]


@app.post("/listings/{listing_id}/messages", response_model=MessageResponse, status_code=201)
async def send_message(listing_id: UUID, body: SendMessageRequest, caller=Depends(current_user)):
    if not caller["can_message"]:
        raise HTTPException(403, "This agent session does not have messaging permission")

    listing = await db.fetchrow("SELECT seller_id FROM listings WHERE id = $1", listing_id)
    if not listing:
        raise HTTPException(404)

    recipient_id = (
        listing["seller_id"]
        if listing["seller_id"] != caller["user_id"]
        else None
    )
    if not recipient_id:
        raise HTTPException(400, "Cannot message yourself")

    row = await db.fetchrow(
        """
        INSERT INTO messages (listing_id, sender_id, recipient_id, body, sent_by)
        VALUES ($1,$2,$3,$4,$5) RETURNING *
        """,
        listing_id, caller["user_id"], recipient_id, body.body, body.sent_by,
    )
    return await _message_response(row)


# ── My listings / offers ──────────────────────────────────────────────────────

@app.get("/me/listings", response_model=list[ListingResponse])
async def my_listings(status: str = "active", caller=Depends(current_user)):
    q = "SELECT * FROM listings WHERE seller_id = $1"
    args = [caller["user_id"]]
    if status != "all":
        args.append(status)
        q += f" AND status = ${len(args)}"
    q += " ORDER BY updated_at DESC LIMIT 100"
    rows = await db.fetch(q, *args)
    return [await _listing_response(r, caller["user_id"]) for r in rows]


@app.get("/me/offers", response_model=list[OfferResponse])
async def my_offers(direction: str = "all", caller=Depends(current_user)):
    if direction == "sent":
        rows = await db.fetch(
            "SELECT * FROM offers WHERE buyer_id = $1 ORDER BY created_at DESC LIMIT 50",
            caller["user_id"],
        )
    elif direction == "received":
        rows = await db.fetch(
            """
            SELECT o.* FROM offers o
            JOIN listings l ON l.id = o.listing_id
            WHERE l.seller_id = $1
            ORDER BY o.created_at DESC LIMIT 50
            """,
            caller["user_id"],
        )
    else:
        rows = await db.fetch(
            """
            SELECT o.* FROM offers o
            LEFT JOIN listings l ON l.id = o.listing_id
            WHERE o.buyer_id = $1 OR l.seller_id = $1
            ORDER BY o.created_at DESC LIMIT 50
            """,
            caller["user_id"],
        )
    return [await _offer_response(r) for r in rows]


# ── AI endpoints ──────────────────────────────────────────────────────────────

@app.post("/ai/generate", response_model=GenerateListingResponse)
async def generate_listing(body: GenerateListingRequest):
    """
    Turn a casual description into a structured listing draft.
    Agents should call this before POST /listings when they have informal input.
    """
    draft = await generate_listing_draft(
        description=body.description,
        price_hint=body.price_hint,
        location=body.location,
        photo_urls=body.photo_urls,
    )
    return draft


@app.post("/ai/analyze-photo")
async def analyze_photo(file: UploadFile = File(...)):
    """Upload a photo and get an AI description back."""
    contents = await file.read()
    import base64
    b64 = base64.b64encode(contents).decode()
    caption = await analyze_photos([b64])
    return {"caption": caption}


# ── Response builders ─────────────────────────────────────────────────────────

async def _listing_response(row, viewer_id) -> ListingResponse:
    photos = await db.fetch(
        "SELECT url FROM listing_photos WHERE listing_id = $1 ORDER BY position", row["id"]
    )
    seller = await db.fetchrow("SELECT * FROM users WHERE id = $1", row["seller_id"])
    return ListingResponse(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        price=row["price"],
        condition=row["condition"],
        category_id=row["category_id"],
        attributes=dict(row["attributes"] or {}),
        location=Location(lat=row["lat"], lng=row["lng"], text=row["location_text"]),
        status=row["status"],
        price_negotiable=row["price_negotiable"],
        photos=[p["url"] for p in photos],
        seller=_user_summary(seller),
        listed_by=row["listed_by"],
        views=row["views"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _offer_response(row) -> OfferResponse:
    buyer = await db.fetchrow("SELECT * FROM users WHERE id = $1", row["buyer_id"])
    return OfferResponse(
        id=row["id"],
        listing_id=row["listing_id"],
        buyer=_user_summary(buyer),
        amount=row["amount"],
        message=row["message"],
        status=row["status"],
        counter_amount=row["counter_amount"],
        counter_message=row["counter_message"],
        offered_by=row["offered_by"],
        responded_by=row["responded_by"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        responded_at=row["responded_at"],
    )


async def _message_response(row) -> MessageResponse:
    sender = await db.fetchrow("SELECT * FROM users WHERE id = $1", row["sender_id"])
    return MessageResponse(
        id=row["id"],
        sender=_user_summary(sender),
        body=row["body"],
        sent_by=row["sent_by"],
        read_at=row["read_at"],
        created_at=row["created_at"],
    )


def _user_summary(row) -> UserSummary:
    return UserSummary(
        id=row["id"],
        display_name=row["display_name"],
        avatar_url=row["avatar_url"],
        trust_score=float(row["trust_score"] or 0.5),
        sold_total=row["sold_total"],
        avg_rating=float(row["avg_rating"]) if row["avg_rating"] else None,
        phone_verified=row["phone_verified"],
    )
