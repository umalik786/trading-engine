"""Tests for the position book's order plans (spec v3.12, §2.10; PC.1).

Each plan is written as (side, lots, ticket closed) in submission order;
`None` means the order opens. The hedging book used throughout holds two
long tickets in XAUUSD: "1", 0.30 lots, opened first, and "2", 0.20 lots,
opened an hour later -- 0.50 lots in all.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from engine.core.portfolio import Portfolio
from engine.core.positions import PlanError, PositionBook
from engine.core.types import Fill, Order, PositionMode, TargetPosition

SYMBOL = "XAUUSD"
_TS = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
INTENT = "Scripted:XAUUSD:2026-01-05T13:00:00+00:00:0"


def _fill(quantity: str, ticket: str, ts: datetime) -> Fill:
    return Fill(
        order_id="o",
        client_order_id="c",
        symbol=SYMBOL,
        quantity=Decimal(quantity),
        price=Decimal("2000.00"),
        fees=Decimal(0),
        ts=ts,
        ticket=ticket,
    )


def _book(mode: PositionMode, *held: tuple[str, str]) -> PositionBook:
    """`held`: (signed lots, ticket) per opening fill, oldest first, an
    hour apart. Under netting every ticket is the symbol."""
    portfolio = Portfolio(
        starting_balance=Decimal(0), contract_sizes={SYMBOL: Decimal(100)}, position_mode=mode
    )
    for hour, (lots, ticket) in enumerate(held):
        portfolio.apply_fill(
            _fill(lots, SYMBOL if mode == "netting" else ticket, _TS + timedelta(hours=hour))
        )
    return PositionBook(portfolio, mode)


def _two_longs() -> PositionBook:
    return _book("hedging", ("0.30", "1"), ("0.20", "2"))


def _pending(side: str, lots: str, closes: str | None = None, n: int = 0) -> Order:
    return Order(
        client_order_id=f"earlier:{n}",
        symbol=SYMBOL,
        side=side,  # type: ignore[arg-type]
        quantity=Decimal(lots),
        order_type="market",
        limit_price=None,
        stop_price=None,
        intent_id="earlier",
        closes_ticket=closes,
    )


def _plan(book: PositionBook, target: str, pending: Sequence[Order] = ()) -> list[tuple]:
    orders = book.plan(SYMBOL, Decimal(target), pending_orders=pending, intent_id=INTENT)
    return [(o.side, o.quantity, o.closes_ticket) for o in orders]


D = Decimal


class TestNetting:
    def test_from_flat_one_order(self) -> None:
        assert _plan(_book("netting"), "0.50") == [("buy", D("0.50"), None)]

    def test_an_increase_is_one_order_for_the_difference(self) -> None:
        book = _book("netting", ("0.30", ""), ("0.20", ""))
        assert _plan(book, "0.80") == [("buy", D("0.30"), None)]

    def test_a_reduction_is_one_order_for_the_difference(self) -> None:
        book = _book("netting", ("0.30", ""), ("0.20", ""))
        assert _plan(book, "0.10") == [("sell", D("0.40"), None)]

    def test_a_flip_is_one_order_through_zero(self) -> None:
        book = _book("netting", ("0.30", ""), ("0.20", ""))
        # 0.50 long to 0.20 short: sell 0.70 in one order
        assert _plan(book, "-0.20") == [("sell", D("0.70"), None)]

    def test_already_there_plans_nothing(self) -> None:
        book = _book("netting", ("0.30", ""), ("0.20", ""))
        assert _plan(book, "0.50") == []

    def test_a_pending_order_counts_as_held(self) -> None:
        book = _book("netting", ("0.30", ""), ("0.20", ""))
        assert _plan(book, "0", [_pending("sell", "0.50")]) == []


class TestHedging:
    def test_from_flat_one_opening_order(self) -> None:
        assert _plan(_book("hedging"), "0.50") == [("buy", D("0.50"), None)]

    def test_an_increase_opens_a_new_ticket_for_the_difference(self) -> None:
        assert _plan(_two_longs(), "0.80") == [("buy", D("0.30"), None)]

    def test_a_reduction_closes_oldest_first_the_last_one_partly(self) -> None:
        # 0.50 to 0.10: close 0.40 -- all of ticket 1 (0.30), then 0.10 of ticket 2
        assert _plan(_two_longs(), "0.10") == [
            ("sell", D("0.30"), "1"),
            ("sell", D("0.10"), "2"),
        ]

    def test_a_small_reduction_takes_part_of_the_oldest_ticket_only(self) -> None:
        assert _plan(_two_longs(), "0.40") == [("sell", D("0.10"), "1")]

    def test_to_flat_closes_every_ticket(self) -> None:
        assert _plan(_two_longs(), "0") == [
            ("sell", D("0.30"), "1"),
            ("sell", D("0.20"), "2"),
        ]

    def test_a_flip_closes_every_ticket_then_opens_the_other_way(self) -> None:
        assert _plan(_two_longs(), "-0.20") == [
            ("sell", D("0.30"), "1"),
            ("sell", D("0.20"), "2"),
            ("sell", D("0.20"), None),
        ]

    def test_a_short_book_is_reduced_by_buys_naming_its_tickets(self) -> None:
        book = _book("hedging", ("-0.30", "1"), ("-0.20", "2"))
        assert _plan(book, "-0.10") == [
            ("buy", D("0.30"), "1"),
            ("buy", D("0.10"), "2"),
        ]

    def test_already_there_plans_nothing(self) -> None:
        assert _plan(_two_longs(), "0.50") == []

    def test_a_pending_close_uses_up_its_ticket(self) -> None:
        """Ticket 1 is already being closed, so the 0.20 held-and-committed
        is ticket 2; reducing to 0.10 closes 0.10 of ticket 2."""
        pending = [_pending("sell", "0.30", closes="1")]
        assert _plan(_two_longs(), "0.10", pending) == [("sell", D("0.10"), "2")]

    def test_a_pending_opening_order_counts_as_committed(self) -> None:
        pending = [_pending("buy", "0.20")]
        assert _plan(_two_longs(), "0.70", pending) == []

    def test_a_reduction_into_lots_not_yet_filled_is_refused(self) -> None:
        """0.50 held plus 0.20 ordered, target 0.10: closing 0.60 would
        need 0.10 of lots that have no ticket yet. Refused, not guessed."""
        with pytest.raises(PlanError, match="no ticket"):
            _plan(_two_longs(), "0.10", [_pending("buy", "0.20")])


class TestPlanIdentifiers:
    def test_every_order_of_one_intent_shares_its_intent_id(self) -> None:
        orders = _two_longs().plan(SYMBOL, Decimal("-0.20"), pending_orders=(), intent_id=INTENT)
        assert {o.intent_id for o in orders} == {INTENT}

    def test_client_order_ids_count_the_orders_in_plan_order(self) -> None:
        orders = _two_longs().plan(SYMBOL, Decimal("-0.20"), pending_orders=(), intent_id=INTENT)
        assert [o.client_order_id for o in orders] == [
            f"{INTENT}:0",
            f"{INTENT}:1",
            f"{INTENT}:2",
        ]

    def test_plans_are_market_orders_for_the_symbol(self) -> None:
        orders = _two_longs().plan(SYMBOL, Decimal("0"), pending_orders=(), intent_id=INTENT)
        assert {(o.symbol, o.order_type) for o in orders} == {(SYMBOL, "market")}


class TestBook:
    @pytest.mark.parametrize("mode", ["netting", "hedging"])
    def test_net_quantity_is_the_signed_total_under_either_mode(self, mode: PositionMode) -> None:
        book = _book(mode, ("0.30", "1"), ("0.20", "2"))
        assert book.net_quantity(SYMBOL) == Decimal("0.50")

    def test_the_book_and_the_ledger_must_agree_on_the_mode(self) -> None:
        portfolio = Portfolio(
            starting_balance=Decimal(0),
            contract_sizes={SYMBOL: Decimal(100)},
            position_mode="hedging",
        )
        with pytest.raises(ValueError, match="position mode"):
            PositionBook(portfolio, "netting")


# --- rebalancing (decision 2; spec §2.10; phase PC.2) -------------------------


def _weight_target(weight: str, stop: str | None = None, reason: str = "r") -> TargetPosition:
    return TargetPosition(
        symbol=SYMBOL,
        quantity=None,
        weight=Decimal(weight),
        stop_price=Decimal(stop) if stop else None,
        take_profit=None,
        reason=reason,
        confidence=None,
    )


def _quantity_target(lots: str) -> TargetPosition:
    return TargetPosition(
        symbol=SYMBOL,
        quantity=Decimal(lots),
        weight=None,
        stop_price=None,
        take_profit=None,
        reason="r",
        confidence=None,
    )


class TestRebalancing:
    """A weight target identical to the one that sized the position -- same
    weight, same stop -- is held while anything is held or ordered; any
    change is re-sized. A quantity target always plans the difference."""

    def test_nothing_recorded_is_not_held(self) -> None:
        assert _two_longs().holds(_weight_target("1"), Decimal("0.50")) is False

    def test_the_identical_target_is_held(self) -> None:
        book = _two_longs()
        book.record_sizing(_weight_target("1", stop="1990"))
        assert book.holds(_weight_target("1", stop="1990"), Decimal("0.50")) is True

    def test_only_weight_and_stop_count_toward_identical(self) -> None:
        book = _two_longs()
        book.record_sizing(_weight_target("1", reason="first"))
        assert book.holds(_weight_target("1", reason="restated"), Decimal("0.50")) is True

    def test_a_changed_weight_in_the_same_direction_is_resized(self) -> None:
        book = _two_longs()
        book.record_sizing(_weight_target("1"))
        assert book.holds(_weight_target("0.5"), Decimal("0.50")) is False

    def test_a_changed_stop_is_resized(self) -> None:
        book = _two_longs()
        book.record_sizing(_weight_target("1", stop="1990"))
        assert book.holds(_weight_target("1", stop="1980"), Decimal("0.50")) is False

    def test_the_identical_target_over_nothing_committed_is_sized_again(self) -> None:
        """A target that sized to nothing (below the volume minimum, say) is
        asked again on the next bar, as before PC.2: equity may have grown.
        (A stop-out is different: it consumes its target, PC.3.)"""
        book = _book("hedging")
        book.record_sizing(_weight_target("1"))
        assert book.holds(_weight_target("1"), Decimal(0)) is False

    def test_a_quantity_target_is_never_held(self) -> None:
        book = _two_longs()
        book.record_sizing(_quantity_target("0.50"))
        assert book.holds(_quantity_target("0.50"), Decimal("0.50")) is False

    def test_the_record_is_per_symbol(self) -> None:
        book = _two_longs()
        book.record_sizing(_weight_target("1"))
        other = TargetPosition(
            symbol="EURUSD",
            quantity=None,
            weight=Decimal(1),
            stop_price=None,
            take_profit=None,
            reason="r",
            confidence=None,
        )
        assert book.holds(other, Decimal("0.50")) is False
