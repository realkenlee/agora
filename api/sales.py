"""
Agora close-tool: hold → ship → release.

Buyer never browses. Seller inventory gets one Stripe Checkout URL.
Funds land on the platform (separate charges and transfers), then a Transfer
releases to the seller's Connect Express account when they mark shipped.

Dispute handling is a freeze stub — not an escrow court.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import replace
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from api import db
import api.events as events_bus
from api.sale_state import (
    InvalidSaleTransition,
    SALE_STATUSES,
    SaleError,
    SaleState,
    TRANSITIONS,
    VALID_ACTIONS,
    apply_event,
    close_sale_on_ship,
    transfer_group_for,
)

# Re-export for callers that import from api.sales
__all__ = [
    "InvalidSaleTransition",
    "SALE_STATUSES",
    "SaleError",
    "SaleState",
    "TRANSITIONS",
    "VALID_ACTIONS",
    "apply_event",
    "close_sale_on_ship",
    "transfer_group_for",
]


# ── Schema (applied at API startup so existing DBs pick this up) ──────────────

SCHEMA_STATEMENTS = (
    """
    ALTER TABLE users
        ADD COLUMN IF NOT EXISTS stripe_account_id TEXT
    """,
    """
    ALTER TABLE users
        ADD COLUMN IF NOT EXISTS stripe_payouts_enabled BOOLEAN DEFAULT FALSE
    """,
    """
    ALTER TABLE users
        ADD COLUMN IF NOT EXISTS stripe_details_submitted BOOLEAN DEFAULT FALSE
    """,
    """
    CREATE TABLE IF NOT EXISTS sales (
        id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        listing_id              UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
        seller_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        status                  TEXT NOT NULL DEFAULT 'listed'
                                CHECK (status IN (
                                    'draft','listed','paid_held','shipped',
                                    'released','cancelled','disputed'
                                )),
        amount_cents            INT NOT NULL CHECK (amount_cents > 0),
        currency                TEXT NOT NULL DEFAULT 'usd',
        stripe_session_id       TEXT,
        stripe_payment_intent_id TEXT,
        stripe_charge_id        TEXT,
        stripe_transfer_id      TEXT,
        connect_account_id      TEXT,
        checkout_url            TEXT,
        transfer_group          TEXT,
        shipped_at              TIMESTAMPTZ,
        released_at             TIMESTAMPTZ,
        cancelled_at            TIMESTAMPTZ,
        created_at              TIMESTAMPTZ DEFAULT NOW(),
        updated_at              TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sales_seller ON sales(seller_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_sales_listing ON sales(listing_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sales_session ON sales(stripe_session_id)",
    "CREATE INDEX IF NOT EXISTS idx_sales_pi ON sales(stripe_payment_intent_id)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_sales_open_listing
        ON sales(listing_id)
        WHERE status NOT IN ('cancelled', 'released', 'disputed')
    """,
)


async def ensure_schema() -> None:
    for stmt in SCHEMA_STATEMENTS:
        await db.execute(stmt)


# ── Stripe adapter ────────────────────────────────────────────────────────────

def _web_url() -> str:
    return os.environ.get("WEB_URL", "http://localhost:3000").rstrip("/")


def stripe_configured() -> bool:
    return bool(os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY"))


def _secret_key() -> str:
    key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""
    if not key:
        raise SaleError(
            "STRIPE_NOT_CONFIGURED",
            "Stripe is not configured. Pull credentials with `stripe projects env --pull`.",
            status=503,
        )
    return key


def _client():
    from stripe import StripeClient
    return StripeClient(_secret_key())


class StripeGateway:
    """Thin StripeClient wrapper. Tests inject a fake with the same methods."""

    def create_express_account(self, *, user_id: str, email: Optional[str], name: Optional[str]) -> Any:
        client = _client()
        params: dict[str, Any] = {
            "country": os.environ.get("STRIPE_CONNECT_COUNTRY", "US"),
            "controller": {
                "fees": {"payer": "application"},
                "losses": {"payments": "application"},
                "stripe_dashboard": {"type": "express"},
            },
            "capabilities": {"transfers": {"requested": True}},
            "metadata": {"agora_user_id": user_id},
            "business_profile": {
                "product_description": "Physical goods sold through Agora close-tool",
            },
        }
        if email:
            params["email"] = email
        if name:
            params["business_profile"]["name"] = name
        try:
            return client.v1.accounts.create(params)
        except Exception:
            # Fallback for accounts that still expect legacy Express `type`.
            legacy = {
                "type": "express",
                "country": params["country"],
                "capabilities": {"transfers": {"requested": True}},
                "metadata": params["metadata"],
            }
            if email:
                legacy["email"] = email
            return client.v1.accounts.create(legacy)

    def create_account_link(self, account_id: str, *, refresh_url: str, return_url: str) -> Any:
        client = _client()
        return client.v1.account_links.create({
            "account": account_id,
            "refresh_url": refresh_url,
            "return_url": return_url,
            "type": "account_onboarding",
        })

    def retrieve_account(self, account_id: str) -> Any:
        return _client().v1.accounts.retrieve(account_id)

    def account_ready(self, account_id: str) -> bool:
        acct = self.retrieve_account(account_id)
        payouts = bool(getattr(acct, "payouts_enabled", False))
        transfers = None
        caps = getattr(acct, "capabilities", None)
        if caps is not None:
            transfers = getattr(caps, "transfers", None)
            if isinstance(caps, dict):
                transfers = caps.get("transfers")
        return payouts or transfers == "active"

    def create_checkout_session(
        self,
        *,
        sale_id: str,
        title: str,
        description: str,
        amount_cents: int,
        currency: str,
        photo_urls: list[str],
    ) -> Any:
        client = _client()
        product_data: dict[str, Any] = {"name": title[:200]}
        if description:
            product_data["description"] = description[:500]
        if photo_urls:
            product_data["images"] = photo_urls[:8]
        suffix = "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(8))
        params = {
            "mode": "payment",
            "line_items": [{
                "quantity": 1,
                "price_data": {
                    "currency": currency,
                    "unit_amount": amount_cents,
                    "product_data": product_data,
                },
            }],
            "success_url": f"{_web_url()}/?paid=1&session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{_web_url()}/?cancelled=1",
            "payment_intent_data": {
                "transfer_group": transfer_group_for(sale_id),
                "metadata": {"sale_id": sale_id, "agora": "close"},
            },
            "metadata": {"sale_id": sale_id, "agora": "close"},
            "integration_identifier": f"agora_close_{suffix}",
        }
        try:
            return client.v1.checkout.sessions.create(params)
        except Exception:
            params.pop("integration_identifier", None)
            return client.v1.checkout.sessions.create(params)

    def expire_checkout_session(self, session_id: str) -> None:
        try:
            _client().v1.checkout.sessions.expire(session_id)
        except Exception:
            pass

    def create_transfer(
        self,
        *,
        amount_cents: int,
        currency: str,
        destination: str,
        transfer_group: str,
        source_transaction: Optional[str],
        sale_id: str,
    ) -> Any:
        params: dict[str, Any] = {
            "amount": amount_cents,
            "currency": currency,
            "destination": destination,
            "transfer_group": transfer_group,
            "metadata": {"sale_id": sale_id, "agora": "close"},
        }
        if source_transaction:
            params["source_transaction"] = source_transaction
        return _client().v1.transfers.create(params)

    def construct_event(self, payload: bytes, sig: str) -> Any:
        import stripe
        secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        if not secret:
            raise SaleError(
                "STRIPE_WEBHOOK_NOT_CONFIGURED",
                "STRIPE_WEBHOOK_SECRET is not set",
                status=503,
            )
        return stripe.Webhook.construct_event(payload, sig, secret)


_gateway = StripeGateway()


def set_gateway(gateway: Any) -> None:
    """Tests replace the live Stripe adapter."""
    global _gateway
    _gateway = gateway


# ── Persistence helpers ───────────────────────────────────────────────────────

def _row_to_sale(row) -> SaleState:
    return SaleState(
        id=str(row["id"]),
        listing_id=str(row["listing_id"]),
        seller_id=str(row["seller_id"]),
        status=row["status"],
        amount_cents=int(row["amount_cents"]),
        currency=row["currency"] or "usd",
        stripe_session_id=row["stripe_session_id"],
        stripe_payment_intent_id=row["stripe_payment_intent_id"],
        stripe_charge_id=row["stripe_charge_id"],
        stripe_transfer_id=row["stripe_transfer_id"],
        connect_account_id=row["connect_account_id"],
        checkout_url=row["checkout_url"],
        transfer_group=row["transfer_group"],
    )


async def _sale_row(sale_id: UUID | str):
    return await db.fetchrow("SELECT * FROM sales WHERE id=$1", sale_id)


async def latest_sale_for_listing(listing_id: UUID | str):
    return await db.fetchrow(
        "SELECT * FROM sales WHERE listing_id=$1 ORDER BY created_at DESC LIMIT 1",
        listing_id,
    )


async def open_sale_for_listing(listing_id: UUID | str):
    return await db.fetchrow(
        """SELECT * FROM sales
           WHERE listing_id=$1 AND status NOT IN ('cancelled','released','disputed')
           ORDER BY created_at DESC LIMIT 1""",
        listing_id,
    )


def dollars_to_cents(amount: Decimal | float | int) -> int:
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1")))


async def _persist(sale: SaleState, **extra) -> None:
    sets = ["status=$2", "stripe_session_id=$3", "stripe_payment_intent_id=$4",
            "stripe_charge_id=$5", "stripe_transfer_id=$6", "connect_account_id=$7",
            "checkout_url=$8", "transfer_group=$9", "updated_at=NOW()"]
    args: list[Any] = [
        sale.id, sale.status, sale.stripe_session_id, sale.stripe_payment_intent_id,
        sale.stripe_charge_id, sale.stripe_transfer_id, sale.connect_account_id,
        sale.checkout_url, sale.transfer_group or transfer_group_for(sale.id),
    ]
    if extra.get("shipped"):
        sets.append("shipped_at=NOW()")
    if extra.get("released"):
        sets.append("released_at=NOW()")
    if extra.get("cancelled"):
        sets.append("cancelled_at=NOW()")
    await db.execute(
        f"UPDATE sales SET {', '.join(sets)} WHERE id=$1",
        *args,
    )


def sale_public(row, *, listing: Optional[dict] = None, photos: Optional[list[str]] = None) -> dict:
    status = row["status"] if not isinstance(row, SaleState) else row.status
    sale_id = str(row["id"]) if not isinstance(row, SaleState) else row.id
    listing_id = str(row["listing_id"]) if not isinstance(row, SaleState) else row.listing_id
    checkout = row["checkout_url"] if not isinstance(row, SaleState) else row.checkout_url
    amount = row["amount_cents"] if not isinstance(row, SaleState) else row.amount_cents
    currency = (row["currency"] if not isinstance(row, SaleState) else row.currency) or "usd"
    out = {
        "id": sale_id,
        "listing_id": listing_id,
        "status": status,
        "amount_cents": int(amount),
        "amount": round(int(amount) / 100, 2),
        "currency": currency,
        "checkout_url": checkout,
        "stripe_session_id": row["stripe_session_id"] if not isinstance(row, SaleState) else row.stripe_session_id,
        "stripe_payment_intent_id": row["stripe_payment_intent_id"] if not isinstance(row, SaleState) else row.stripe_payment_intent_id,
        "stripe_transfer_id": row["stripe_transfer_id"] if not isinstance(row, SaleState) else row.stripe_transfer_id,
        "connect_account_id": row["connect_account_id"] if not isinstance(row, SaleState) else row.connect_account_id,
        "valid_actions": list(VALID_ACTIONS.get(status, [])),
        "state": {
            "valid_actions": list(VALID_ACTIONS.get(status, [])),
            "hold": status == "paid_held",
            "released": status == "released",
            "frozen": status == "disputed",
        },
    }
    if listing:
        out["item"] = {
            "id": str(listing["id"]),
            "title": listing["title"],
            "description": listing["description"],
            "price": float(listing["price"]),
            "min_price": float(listing["min_price"]) if listing.get("min_price") is not None else None,
            "photos": photos or [],
            "listing_status": listing["status"],
        }
    return out


def item_public(listing, sale_row, photos: list[str]) -> dict:
    sale = sale_public(sale_row) if sale_row else None
    status = sale["status"] if sale else "listed"
    actions = list(VALID_ACTIONS.get(status, ["mint_pay_link"]))
    if sale is None:
        actions = ["mint_pay_link"]
    return {
        "id": str(listing["id"]),
        "title": listing["title"],
        "description": listing["description"],
        "price": float(listing["price"]),
        "min_price": float(listing["min_price"]) if listing.get("min_price") is not None else None,
        "currency": listing.get("currency") or "usd",
        "photos": photos,
        "listing_status": listing["status"],
        "sale_status": status if sale else None,
        "checkout_url": sale["checkout_url"] if sale else None,
        "sale": sale,
        "valid_actions": actions,
        "created_at": listing["created_at"].isoformat() if listing.get("created_at") else None,
        "updated_at": listing["updated_at"].isoformat() if listing.get("updated_at") else None,
    }


async def _photos(listing_id) -> list[str]:
    rows = await db.fetch(
        "SELECT url FROM listing_photos WHERE listing_id=$1 ORDER BY position",
        listing_id,
    )
    return [r["url"] for r in rows]


async def _listing(listing_id):
    return await db.fetchrow("SELECT * FROM listings WHERE id=$1", listing_id)


# ── Seller inventory ──────────────────────────────────────────────────────────

async def create_item(
    *,
    seller_id,
    title: str,
    description: str,
    price,
    min_price=None,
    photo_urls: Optional[list[str]] = None,
    condition: str = "good",
    category_id: str = "other",
    listed_by: str = "agent",
    auto_pay_link: bool = True,
) -> dict:
    photo_urls = photo_urls or []
    desc = (description or "").strip()
    if len(desc) < 10:
        desc = f"{title.strip()}. Physical item listed for sale."
    user = await db.fetchrow("SELECT * FROM users WHERE id=$1", seller_id)
    lat = float(user["default_lat"]) if user and user.get("default_lat") is not None else 0.0
    lng = float(user["default_lng"]) if user and user.get("default_lng") is not None else 0.0
    loc = (user["default_location"] if user and user.get("default_location") else "unspecified")

    embedding = None
    try:
        from ai.embed import embed_text
        vec = await embed_text(f"{title} {desc} {category_id}")
        embedding = "[" + ",".join(str(x) for x in vec) + "]"
    except Exception as e:
        print(f"[items] embed skipped: {e}")

    listing = await db.fetchrow(
        """
        INSERT INTO listings
            (seller_id, title, description, category_id, condition, attributes,
             price, price_negotiable, min_price, lat, lng, location_text,
             listed_by, embedding, status)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,'active')
        RETURNING *
        """,
        seller_id, title.strip(), desc, category_id, condition, {},
        float(price), False,
        float(min_price) if min_price is not None else None,
        lat, lng, loc, listed_by, embedding,
    )
    if photo_urls:
        await db.executemany(
            "INSERT INTO listing_photos (listing_id, url, position) VALUES ($1,$2,$3)",
            [(listing["id"], url, i) for i, url in enumerate(photo_urls)],
        )

    sale = await create_sale_for_listing(listing, seller_id)
    if auto_pay_link and stripe_configured():
        try:
            sale = await mint_pay_link(listing["id"], seller_id)
        except SaleError as e:
            print(f"[items] pay link skipped: {e}")

    photos = await _photos(listing["id"])
    return item_public(listing, sale, photos)


async def create_sale_for_listing(listing, seller_id) -> Any:
    existing = await open_sale_for_listing(listing["id"])
    if existing:
        return existing
    cents = dollars_to_cents(listing["price"])
    currency = (listing.get("currency") or "usd").lower()
    row = await db.fetchrow(
        """
        INSERT INTO sales (listing_id, seller_id, status, amount_cents, currency, transfer_group)
        VALUES ($1,$2,'listed',$3,$4,$5)
        RETURNING *
        """,
        listing["id"], seller_id, cents, currency, None,
    )
    # transfer_group needs the sale id
    await db.execute(
        "UPDATE sales SET transfer_group=$1 WHERE id=$2",
        transfer_group_for(str(row["id"])), row["id"],
    )
    return await _sale_row(row["id"])


async def list_items(seller_id, status: str = "all") -> list[dict]:
    rows = await db.fetch(
        """
        SELECT * FROM listings
        WHERE seller_id=$1 AND status <> 'removed'
        ORDER BY updated_at DESC
        LIMIT 100
        """,
        seller_id,
    )
    items = []
    for listing in rows:
        sale = await latest_sale_for_listing(listing["id"])
        if status not in ("all", "", None):
            sale_status = sale["status"] if sale else None
            if status != sale_status and status != listing["status"]:
                continue
        photos = await _photos(listing["id"])
        items.append(item_public(listing, sale, photos))
    return items


async def get_item(listing_id, seller_id) -> dict:
    listing = await _listing(listing_id)
    if not listing:
        raise SaleError("LISTING_NOT_FOUND", "No item with that ID", status=404)
    if str(listing["seller_id"]) != str(seller_id):
        raise SaleError("NOT_YOUR_ITEM", "Only the seller can view this inventory item", status=403)
    sale = await latest_sale_for_listing(listing_id)
    return item_public(listing, sale, await _photos(listing_id))


async def mint_pay_link(listing_id, seller_id) -> Any:
    listing = await _listing(listing_id)
    if not listing:
        raise SaleError("LISTING_NOT_FOUND", "No item with that ID", status=404)
    if str(listing["seller_id"]) != str(seller_id):
        raise SaleError("NOT_YOUR_ITEM", "Only the seller can mint a pay link", status=403)
    if listing["status"] == "removed":
        raise SaleError("ITEM_REMOVED", "This item was taken down", status=409)

    sale_row = await open_sale_for_listing(listing_id) or await create_sale_for_listing(listing, seller_id)
    sale = _row_to_sale(sale_row)
    if sale.status not in ("listed", "draft"):
        if sale.checkout_url and sale.status == "paid_held":
            raise SaleError(
                "ALREADY_PAID",
                "Buyer already paid — funds are held. Mark shipped to release.",
                status=409,
                checkout_url=sale.checkout_url,
                status_name=sale.status,
            )
        raise SaleError(
            "PAY_LINK_UNAVAILABLE",
            f"Cannot mint a pay link while sale is '{sale.status}'",
            status=409,
            status_name=sale.status,
        )

    if sale.status == "draft":
        sale = apply_event(sale, "list")

    photos = await _photos(listing_id)
    session = _gateway.create_checkout_session(
        sale_id=sale.id,
        title=listing["title"],
        description=listing["description"],
        amount_cents=sale.amount_cents,
        currency=sale.currency,
        photo_urls=photos,
    )
    session_id = getattr(session, "id", None) or session["id"]
    checkout_url = getattr(session, "url", None) or session["url"]
    pi = getattr(session, "payment_intent", None)
    if hasattr(pi, "id"):
        pi = pi.id

    sale = replace(
        sale,
        status="listed",
        stripe_session_id=session_id,
        checkout_url=checkout_url,
        stripe_payment_intent_id=pi if isinstance(pi, str) else None,
        transfer_group=transfer_group_for(sale.id),
    )
    await _persist(sale)
    return await _sale_row(sale.id)


async def mark_shipped(listing_id, seller_id) -> dict:
    listing = await _listing(listing_id)
    if not listing:
        raise SaleError("LISTING_NOT_FOUND", "No item with that ID", status=404)
    if str(listing["seller_id"]) != str(seller_id):
        raise SaleError("NOT_YOUR_ITEM", "Only the seller can mark this shipped", status=403)

    sale_row = await open_sale_for_listing(listing_id) or await latest_sale_for_listing(listing_id)
    if not sale_row:
        raise SaleError("SALE_NOT_FOUND", "No sale on this item", status=404)
    sale = _row_to_sale(sale_row)

    if sale.status == "released":
        return item_public(listing, sale_row, await _photos(listing_id))
    if sale.status == "shipped" and sale.stripe_transfer_id:
        released = apply_event(sale, "release", transfer_id=sale.stripe_transfer_id)
        await _persist(released, released=True)
        await db.execute("UPDATE listings SET status='sold' WHERE id=$1", listing_id)
        return item_public(await _listing(listing_id), await _sale_row(released.id), await _photos(listing_id))
    if sale.status == "shipped":
        # Retry release if transfer never completed.
        user = await db.fetchrow("SELECT * FROM users WHERE id=$1", seller_id)
        account_id = (user or {}).get("stripe_account_id") or sale.connect_account_id
        ready = bool((user or {}).get("stripe_payouts_enabled"))
        if account_id and not ready:
            try:
                ready = _gateway.account_ready(account_id)
            except Exception:
                ready = False
        if not account_id or not ready:
            onboarding = await start_onboarding(seller_id)
            raise SaleError(
                "CONNECT_ONBOARDING_REQUIRED",
                "Complete Stripe Express onboarding to receive this payout",
                status=409,
                onboarding_url=onboarding.get("onboarding_url"),
            )
        released = close_sale_on_ship(
            replace(sale, status="paid_held"),  # allow retry through the same closer
            connect_account_id=account_id,
            connect_ready=True,
            stripe=_gateway,
        )
        # closer expected paid_held; we already shipped — just transfer + release
        # Re-run from shipped via apply_event release after transfer.
        # The line above rewinds to paid_held so close_sale_on_ship can run.
        await _persist(released, shipped=True, released=True)
        await db.execute("UPDATE listings SET status='sold' WHERE id=$1", listing_id)
        await events_bus.emit(str(seller_id), "sale_released", {
            "sale_id": released.id,
            "listing_id": str(listing_id),
            "transfer_id": released.stripe_transfer_id,
        })
        return item_public(await _listing(listing_id), await _sale_row(released.id), await _photos(listing_id))

    user = await db.fetchrow("SELECT * FROM users WHERE id=$1", seller_id)
    account_id = (user or {}).get("stripe_account_id") or sale.connect_account_id
    ready = bool((user or {}).get("stripe_payouts_enabled"))
    if account_id:
        try:
            ready = ready or _gateway.account_ready(account_id)
            if ready:
                await db.execute(
                    "UPDATE users SET stripe_payouts_enabled=TRUE WHERE id=$1",
                    seller_id,
                )
        except Exception as e:
            print(f"[connect] account lookup failed: {e}")

    if not account_id or not ready:
        onboarding = await start_onboarding(seller_id)
        raise SaleError(
            "CONNECT_ONBOARDING_REQUIRED",
            "Complete Stripe Express onboarding to receive this payout. "
            "Funds stay held until you finish onboarding and retry mark-shipped.",
            status=409,
            onboarding_url=onboarding.get("onboarding_url"),
            connect_account_id=onboarding.get("account_id"),
        )

    released = close_sale_on_ship(
        sale,
        connect_account_id=account_id,
        connect_ready=True,
        stripe=_gateway,
    )
    await _persist(released, shipped=True, released=True)
    await db.execute("UPDATE listings SET status='sold' WHERE id=$1", listing_id)
    await events_bus.emit(str(seller_id), "sale_released", {
        "sale_id": released.id,
        "listing_id": str(listing_id),
        "listing_title": listing["title"],
        "transfer_id": released.stripe_transfer_id,
        "amount": released.amount_cents / 100,
    })
    return item_public(await _listing(listing_id), await _sale_row(released.id), await _photos(listing_id))


async def cancel_item(listing_id, seller_id) -> dict:
    listing = await _listing(listing_id)
    if not listing:
        raise SaleError("LISTING_NOT_FOUND", "No item with that ID", status=404)
    if str(listing["seller_id"]) != str(seller_id):
        raise SaleError("NOT_YOUR_ITEM", "Only the seller can cancel this sale", status=403)
    sale_row = await open_sale_for_listing(listing_id)
    if not sale_row:
        await db.execute("UPDATE listings SET status='removed' WHERE id=$1", listing_id)
        return item_public(await _listing(listing_id), None, await _photos(listing_id))
    sale = apply_event(_row_to_sale(sale_row), "cancel")
    if sale_row["stripe_session_id"] and stripe_configured():
        _gateway.expire_checkout_session(sale_row["stripe_session_id"])
    await _persist(sale, cancelled=True)
    await db.execute("UPDATE listings SET status='removed' WHERE id=$1", listing_id)
    return item_public(await _listing(listing_id), await _sale_row(sale.id), await _photos(listing_id))


# ── Connect onboarding ────────────────────────────────────────────────────────

async def connect_status(seller_id) -> dict:
    user = await db.fetchrow("SELECT * FROM users WHERE id=$1", seller_id)
    account_id = (user or {}).get("stripe_account_id")
    ready = bool((user or {}).get("stripe_payouts_enabled"))
    details = bool((user or {}).get("stripe_details_submitted"))
    if account_id and stripe_configured():
        try:
            acct = _gateway.retrieve_account(account_id)
            ready = bool(getattr(acct, "payouts_enabled", ready))
            details = bool(getattr(acct, "details_submitted", details))
            await db.execute(
                """UPDATE users SET stripe_payouts_enabled=$1, stripe_details_submitted=$2
                   WHERE id=$3""",
                ready, details, seller_id,
            )
        except Exception as e:
            print(f"[connect] status refresh failed: {e}")
    return {
        "account_id": account_id,
        "payouts_enabled": ready,
        "details_submitted": details,
        "required_for": "payout",
        "onboarding_required": not ready,
        "note": (
            "Connect Express is only required when a paid sale is about to clear "
            "(mark shipped / payout). You can list and share a pay link first."
        ),
    }


async def start_onboarding(seller_id) -> dict:
    user = await db.fetchrow("SELECT * FROM users WHERE id=$1", seller_id)
    if not user:
        raise SaleError("USER_NOT_FOUND", "No seller with that ID", status=404)
    account_id = user.get("stripe_account_id")
    if not account_id:
        acct = _gateway.create_express_account(
            user_id=str(seller_id),
            email=user.get("email"),
            name=user.get("display_name"),
        )
        account_id = getattr(acct, "id", None) or acct["id"]
        await db.execute(
            "UPDATE users SET stripe_account_id=$1 WHERE id=$2",
            account_id, seller_id,
        )
    refresh = os.environ.get("STRIPE_CONNECT_REFRESH_URL") or f"{_web_url()}/connect/refresh"
    return_url = os.environ.get("STRIPE_CONNECT_RETURN_URL") or f"{_web_url()}/connect/return"
    link = _gateway.create_account_link(
        account_id, refresh_url=refresh, return_url=return_url,
    )
    url = getattr(link, "url", None) or link["url"]
    return {
        "account_id": account_id,
        "onboarding_url": url,
        "required_for": "payout",
        "note": "Open this URL once as the seller. Retry mark-shipped after Stripe redirects back.",
    }


# ── Webhooks ──────────────────────────────────────────────────────────────────

def construct_webhook_event(payload: bytes, sig: str) -> Any:
    return _gateway.construct_event(payload, sig)


async def handle_webhook(event: Any) -> dict:
    etype = event["type"] if isinstance(event, dict) else event.type
    data = event["data"]["object"] if isinstance(event, dict) else event.data.object
    if etype in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return await _on_checkout_paid(data)
    if etype == "charge.dispute.created":
        return await _on_dispute(data)
    if etype == "account.updated":
        return await _on_account_updated(data)
    return {"ignored": etype}


def _obj_get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


async def _on_checkout_paid(session) -> dict:
    sale_id = None
    metadata = _obj_get(session, "metadata") or {}
    if isinstance(metadata, dict):
        sale_id = metadata.get("sale_id")
    else:
        sale_id = getattr(metadata, "sale_id", None)
    session_id = _obj_get(session, "id")
    if not sale_id:
        row = await db.fetchrow("SELECT * FROM sales WHERE stripe_session_id=$1", session_id)
    else:
        row = await db.fetchrow("SELECT * FROM sales WHERE id=$1", sale_id)
    if not row:
        return {"ok": False, "reason": "sale_not_found"}
    if row["status"] in ("paid_held", "shipped", "released"):
        return {"ok": True, "already": row["status"]}

    pi = _obj_get(session, "payment_intent")
    if hasattr(pi, "id"):
        pi = pi.id
    charge_id = _obj_get(session, "payment_intent")
    # Prefer payment_intent id; charge is filled if expanded.
    latest_charge = None
    if isinstance(session, dict):
        latest_charge = (session.get("payment_intent") and None)
    payment_status = _obj_get(session, "payment_status")
    if payment_status and payment_status not in ("paid", "no_payment_required"):
        return {"ok": False, "reason": f"payment_status={payment_status}"}

    sale = apply_event(
        _row_to_sale(row),
        "pay",
        session_id=session_id,
        payment_intent_id=pi if isinstance(pi, str) else None,
        charge_id=latest_charge if isinstance(latest_charge, str) else None,
    )
    # Try to resolve the charge id so source_transaction works on release.
    if sale.stripe_payment_intent_id and stripe_configured() and not sale.stripe_charge_id:
        try:
            pi_obj = _client().v1.payment_intents.retrieve(
                sale.stripe_payment_intent_id,
                {"expand": ["latest_charge"]},
            )
            lc = getattr(pi_obj, "latest_charge", None)
            if hasattr(lc, "id"):
                sale = replace(sale, stripe_charge_id=lc.id)
            elif isinstance(lc, str):
                sale = replace(sale, stripe_charge_id=lc)
        except Exception as e:
            print(f"[sales] charge lookup skipped: {e}")

    await _persist(sale)
    await db.execute(
        "UPDATE listings SET status='pending' WHERE id=$1 AND status='active'",
        row["listing_id"],
    )
    await events_bus.emit(str(row["seller_id"]), "sale_paid_held", {
        "sale_id": sale.id,
        "listing_id": str(row["listing_id"]),
        "amount": sale.amount_cents / 100,
    })
    return {"ok": True, "status": "paid_held", "sale_id": sale.id}


async def _on_dispute(charge) -> dict:
    pi = _obj_get(charge, "payment_intent")
    if hasattr(pi, "id"):
        pi = pi.id
    charge_id = _obj_get(charge, "id")
    row = None
    if isinstance(pi, str):
        row = await db.fetchrow("SELECT * FROM sales WHERE stripe_payment_intent_id=$1", pi)
    if not row and charge_id:
        row = await db.fetchrow("SELECT * FROM sales WHERE stripe_charge_id=$1", charge_id)
    if not row:
        return {"ok": False, "reason": "sale_not_found"}
    try:
        sale = apply_event(_row_to_sale(row), "dispute")
    except InvalidSaleTransition:
        return {"ok": True, "already": row["status"]}
    await _persist(sale)
    await events_bus.emit(str(row["seller_id"]), "sale_disputed", {
        "sale_id": sale.id,
        "listing_id": str(row["listing_id"]),
        "note": "Payout frozen (dispute stub — no court UI).",
    })
    return {"ok": True, "status": "disputed"}


async def _on_account_updated(account) -> dict:
    account_id = _obj_get(account, "id")
    payouts = bool(_obj_get(account, "payouts_enabled"))
    details = bool(_obj_get(account, "details_submitted"))
    await db.execute(
        """UPDATE users SET stripe_payouts_enabled=$1, stripe_details_submitted=$2
           WHERE stripe_account_id=$3""",
        payouts, details, account_id,
    )
    return {"ok": True, "account_id": account_id, "payouts_enabled": payouts}


def llm_public_status() -> dict:
    from ai.config import llm_settings
    s = llm_settings()
    return {
        "paid": s["paid"],
        "base_url": s["base_url"],
        "model": s["model"] or None,
        "vision_model": s["vision_model"] or None,
        "using_openrouter": s["using_openrouter"],
        "free_tier_note": s["free_tier_note"] if not s["paid"] else None,
    }
