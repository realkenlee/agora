"""Hold → ship → release state machine. Stripe is mocked."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.sale_state import (
    InvalidSaleTransition,
    SALE_STATUSES,
    SaleError,
    SaleState,
    TRANSITIONS,
    apply_event,
    close_sale_on_ship,
    transfer_group_for,
)


def _sale(**overrides) -> SaleState:
    base = dict(
        id="sale-1",
        listing_id="listing-1",
        seller_id="seller-1",
        status="listed",
        amount_cents=5500,
        currency="usd",
        transfer_group="agora_sale_sale-1",
        stripe_charge_id="ch_held_1",
    )
    base.update(overrides)
    return SaleState(**base)


class FakeStripe:
    def __init__(self, *, fail: bool = False):
        self.transfers: list[dict] = []
        self.fail = fail

    def create_transfer(self, **kwargs):
        if self.fail:
            raise RuntimeError("stripe down")
        self.transfers.append(kwargs)
        return SimpleNamespace(id=f"tr_test_{len(self.transfers)}")


def test_happy_path_hold_ship_release():
    sale = _sale()
    held = apply_event(
        sale,
        "pay",
        session_id="cs_test_1",
        payment_intent_id="pi_test_1",
        charge_id="ch_held_1",
    )
    assert held.status == "paid_held"
    assert held.stripe_payment_intent_id == "pi_test_1"

    stripe = FakeStripe()
    released = close_sale_on_ship(
        held,
        connect_account_id="acct_seller",
        connect_ready=True,
        stripe=stripe,
    )
    assert released.status == "released"
    assert released.stripe_transfer_id == "tr_test_1"
    assert released.connect_account_id == "acct_seller"
    assert len(stripe.transfers) == 1
    xfer = stripe.transfers[0]
    assert xfer["amount_cents"] == 5500
    assert xfer["destination"] == "acct_seller"
    assert xfer["source_transaction"] == "ch_held_1"
    assert xfer["transfer_group"] == transfer_group_for("sale-1")


def test_cannot_ship_before_pay():
    sale = _sale(status="listed")
    with pytest.raises(InvalidSaleTransition) as exc:
        close_sale_on_ship(
            sale,
            connect_account_id="acct_seller",
            connect_ready=True,
            stripe=FakeStripe(),
        )
    assert exc.value.context["current"] == "listed"
    assert exc.value.context["target"] == "shipped"


def test_cannot_release_without_ship():
    held = apply_event(_sale(), "pay", payment_intent_id="pi_1")
    with pytest.raises(InvalidSaleTransition):
        apply_event(held, "release", transfer_id="tr_skip")


def test_connect_required_at_payout_not_at_list():
    """Seller can list without Connect; payout is what requires Express."""
    listed = _sale(status="listed", connect_account_id=None)
    held = apply_event(listed, "pay", payment_intent_id="pi_1")
    with pytest.raises(SaleError) as exc:
        close_sale_on_ship(
            held,
            connect_account_id=None,
            connect_ready=False,
            stripe=FakeStripe(),
        )
    assert exc.value.code == "CONNECT_ONBOARDING_REQUIRED"
    assert exc.value.status == 409


def test_connect_account_not_ready_blocks_release():
    held = apply_event(_sale(), "pay", payment_intent_id="pi_1")
    with pytest.raises(SaleError) as exc:
        close_sale_on_ship(
            held,
            connect_account_id="acct_incomplete",
            connect_ready=False,
            stripe=FakeStripe(),
        )
    assert exc.value.code == "CONNECT_ONBOARDING_REQUIRED"


def test_dispute_freeze_blocks_payout():
    held = apply_event(_sale(), "pay", payment_intent_id="pi_1")
    frozen = apply_event(held, "dispute")
    assert frozen.status == "disputed"
    with pytest.raises(SaleError) as exc:
        close_sale_on_ship(
            frozen,
            connect_account_id="acct_seller",
            connect_ready=True,
            stripe=FakeStripe(),
        )
    assert exc.value.code == "SALE_FROZEN"
    # No transfer attempted after freeze
    stripe = FakeStripe()
    with pytest.raises(SaleError):
        close_sale_on_ship(
            frozen,
            connect_account_id="acct_seller",
            connect_ready=True,
            stripe=stripe,
        )
    assert stripe.transfers == []


def test_cancel_from_listed_not_from_released():
    listed = _sale()
    cancelled = apply_event(listed, "cancel")
    assert cancelled.status == "cancelled"
    released = apply_event(
        apply_event(apply_event(_sale(), "pay"), "ship"),
        "release",
        transfer_id="tr_1",
    )
    with pytest.raises(InvalidSaleTransition):
        apply_event(released, "cancel")


def test_unknown_event_rejected():
    with pytest.raises(SaleError) as exc:
        apply_event(_sale(), "refund_court")
    assert exc.value.code == "UNKNOWN_SALE_EVENT"


def test_transition_table_covers_close_path():
    assert "paid_held" in TRANSITIONS["listed"]
    assert "shipped" in TRANSITIONS["paid_held"]
    assert "released" in TRANSITIONS["shipped"]
    for status in SALE_STATUSES:
        assert status in TRANSITIONS


def test_no_double_pay():
    held = apply_event(_sale(), "pay", payment_intent_id="pi_1")
    with pytest.raises(InvalidSaleTransition):
        apply_event(held, "pay", payment_intent_id="pi_2")
