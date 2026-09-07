"""
Pure close-tool state machine: hold → ship → release.

No DB or Stripe imports — unit tests run this file alone.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Optional


SALE_STATUSES = (
    "draft",
    "listed",
    "paid_held",
    "shipped",
    "released",
    "cancelled",
    "disputed",
)

TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"listed", "cancelled"}),
    "listed": frozenset({"paid_held", "cancelled"}),
    "paid_held": frozenset({"shipped", "cancelled", "disputed"}),
    "shipped": frozenset({"released", "disputed"}),
    "released": frozenset({"disputed"}),
    "cancelled": frozenset(),
    "disputed": frozenset(),
}

VALID_ACTIONS: dict[str, list[str]] = {
    "draft": ["list", "cancel"],
    "listed": ["mint_pay_link", "cancel"],
    "paid_held": ["mark_shipped", "cancel"],
    "shipped": ["retry_release"],
    "released": [],
    "cancelled": ["mint_pay_link"],
    "disputed": [],
}


class SaleError(Exception):
    def __init__(self, code: str, detail: str, status: int = 400, **context: Any):
        self.code = code
        self.detail = detail
        self.status = status
        self.context = context
        super().__init__(detail)


class InvalidSaleTransition(SaleError):
    def __init__(self, current: str, target: str):
        super().__init__(
            "INVALID_SALE_TRANSITION",
            f"Cannot move sale from '{current}' to '{target}'",
            status=409,
            current=current,
            target=target,
            allowed=sorted(TRANSITIONS.get(current, frozenset())),
        )


@dataclass
class SaleState:
    id: str
    listing_id: str
    seller_id: str
    status: str
    amount_cents: int
    currency: str = "usd"
    stripe_session_id: Optional[str] = None
    stripe_payment_intent_id: Optional[str] = None
    stripe_charge_id: Optional[str] = None
    stripe_transfer_id: Optional[str] = None
    connect_account_id: Optional[str] = None
    checkout_url: Optional[str] = None
    transfer_group: Optional[str] = None

    @property
    def frozen(self) -> bool:
        return self.status == "disputed"


def transfer_group_for(sale_id: str) -> str:
    return f"agora_sale_{sale_id}"


def assert_transition(current: str, target: str) -> None:
    if target not in TRANSITIONS.get(current, frozenset()):
        raise InvalidSaleTransition(current, target)


def apply_event(sale: SaleState, event: str, **payload: Any) -> SaleState:
    """Pure state machine. Used by tests and by the Stripe/DB adapters."""
    updates: dict[str, Any] = {}
    if event == "list":
        assert_transition(sale.status, "listed")
        updates["status"] = "listed"
    elif event == "pay":
        assert_transition(sale.status, "paid_held")
        updates["status"] = "paid_held"
        if payload.get("session_id"):
            updates["stripe_session_id"] = payload["session_id"]
        if payload.get("payment_intent_id"):
            updates["stripe_payment_intent_id"] = payload["payment_intent_id"]
        if payload.get("charge_id"):
            updates["stripe_charge_id"] = payload["charge_id"]
    elif event == "ship":
        assert_transition(sale.status, "shipped")
        updates["status"] = "shipped"
    elif event == "release":
        assert_transition(sale.status, "released")
        updates["status"] = "released"
        if payload.get("transfer_id"):
            updates["stripe_transfer_id"] = payload["transfer_id"]
        if payload.get("connect_account_id"):
            updates["connect_account_id"] = payload["connect_account_id"]
    elif event == "cancel":
        assert_transition(sale.status, "cancelled")
        updates["status"] = "cancelled"
    elif event == "dispute":
        assert_transition(sale.status, "disputed")
        updates["status"] = "disputed"
    else:
        raise SaleError("UNKNOWN_SALE_EVENT", f"Unknown sale event '{event}'")
    return replace(sale, **updates)


def close_sale_on_ship(
    sale: SaleState,
    *,
    connect_account_id: Optional[str],
    connect_ready: bool,
    stripe: Any,
) -> SaleState:
    """
    paid_held → shipped → Transfer → released.

    Connect Express is required at payout, not at list time.
    """
    if sale.status == "disputed" or sale.frozen:
        raise SaleError(
            "SALE_FROZEN",
            "Dispute freeze — payout is blocked until the dispute is resolved",
            status=409,
            status_name=sale.status,
        )
    if sale.status != "paid_held":
        raise InvalidSaleTransition(sale.status, "shipped")
    if not connect_account_id or not connect_ready:
        raise SaleError(
            "CONNECT_ONBOARDING_REQUIRED",
            "Complete Stripe Express onboarding to receive this payout",
            status=409,
            connect_ready=bool(connect_ready),
            has_account=bool(connect_account_id),
        )

    shipped = apply_event(sale, "ship")
    transfer = stripe.create_transfer(
        amount_cents=shipped.amount_cents,
        currency=shipped.currency,
        destination=connect_account_id,
        transfer_group=shipped.transfer_group or transfer_group_for(shipped.id),
        source_transaction=shipped.stripe_charge_id,
        sale_id=shipped.id,
    )
    transfer_id = getattr(transfer, "id", None) or transfer["id"]
    return apply_event(
        shipped,
        "release",
        transfer_id=transfer_id,
        connect_account_id=connect_account_id,
    )
