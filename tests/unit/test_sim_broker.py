"""Tests for SimBroker. See docs/trading-engine-architecture.md §2.7, §2.8
and Appendix B.6.

The rule under test throughout: an order decided at one bar's close fills
at the NEXT bar's open, where "next bar" is the next bar that exists.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from engine.brokers.base import BrokerOrderRef
from engine.brokers.sim import SimBroker, SimRejectionError
from engine.core.portfolio import BothDirectionsError, ExitPrices, Portfolio
from engine.core.types import Bar, Order, PositionMode
from engine.costs.zero import ZeroCostModel

SYMBOL = "XAUUSD"
CONTRACT_SIZES = {SYMBOL: Decimal(100), "EURUSD": Decimal(100000)}
_BAR_WIDTH = timedelta(minutes=15)


def _broker(mode: PositionMode = "netting") -> tuple[SimBroker, Portfolio]:
    portfolio = Portfolio(
        starting_balance=Decimal(0), contract_sizes=CONTRACT_SIZES, position_mode=mode
    )
    return (
        SimBroker(cost_model=ZeroCostModel(), portfolio=portfolio, position_mode=mode),
        portfolio,
    )


def _bar(ts_open: datetime, open_price: str, close_price: str, symbol: str = SYMBOL) -> Bar:
    prices = [Decimal(open_price), Decimal(close_price)]
    return Bar(
        symbol=symbol,
        ts_open=ts_open,
        ts_close=ts_open + _BAR_WIDTH,
        open=prices[0],
        high=max(prices),
        low=min(prices),
        close=prices[1],
        volume=Decimal(1),
        is_final=True,
        spread=Decimal("0.20"),
    )


def _order(side: str = "buy", quantity: str = "1", symbol: str = SYMBOL, suffix: str = "") -> Order:
    return Order(
        client_order_id=f"test-order{suffix}",
        symbol=symbol,
        side=side,  # type: ignore[arg-type]
        quantity=Decimal(quantity),
        order_type="market",
        limit_price=None,
        stop_price=None,
        intent_id=f"test-intent{suffix}",
    )


class TestFillTiming:
    def test_submitting_does_not_fill(self) -> None:
        """The decision bar's close is not a tradeable price. Nothing is
        filled until a later bar exists."""
        broker, portfolio = _broker()
        broker.submit(_order())

        assert broker.fills() == []
        assert portfolio.position_quantity(SYMBOL) == Decimal(0)
        assert len(broker.pending_orders()) == 1

    def test_fill_happens_at_the_next_bars_open(self) -> None:
        broker, portfolio = _broker()
        decision_bar = _bar(datetime(2026, 1, 5, 12, 0, tzinfo=UTC), "2000.00", "2005.00")
        next_bar = _bar(decision_bar.ts_close, "2007.00", "2011.00")

        broker.submit(_order())
        fills = broker.fill_pending(next_bar)

        assert len(fills) == 1
        assert fills[0].price == Decimal("2007.00")  # next bar's OPEN, not 2005.00
        assert fills[0].ts == next_bar.ts_open
        assert portfolio.position_quantity(SYMBOL) == Decimal(1)
        assert broker.pending_orders() == []

    def test_next_bar_means_the_next_bar_that_exists_not_the_next_clock_slot(self) -> None:
        """Friday's last M15 bar is followed in stored data by Monday's
        first. Nothing fills a weekend, because no weekend bar exists
        (Appendix B.6) -- and this class does no clock arithmetic that
        could believe otherwise."""
        broker, _ = _broker()
        friday_close = datetime(2026, 1, 9, 21, 45, tzinfo=UTC)
        monday_open = datetime(2026, 1, 12, 1, 0, tzinfo=UTC)

        broker.submit(_order())
        fills = broker.fill_pending(_bar(monday_open, "2042.00", "2044.00"))

        assert len(fills) == 1
        assert fills[0].price == Decimal("2042.00")
        assert fills[0].ts == monday_open
        assert fills[0].ts - friday_close == timedelta(days=2, hours=3, minutes=15)

    def test_a_bar_for_another_symbol_does_not_fill_the_order(self) -> None:
        broker, _ = _broker()
        broker.submit(_order(symbol=SYMBOL))

        fills = broker.fill_pending(
            _bar(datetime(2026, 1, 5, 12, 15, tzinfo=UTC), "1.1000", "1.1010", symbol="EURUSD")
        )

        assert fills == []
        assert len(broker.pending_orders()) == 1

    def test_an_order_decided_on_the_last_bar_is_reported_not_lost(self) -> None:
        broker, _ = _broker()
        broker.submit(_order())

        assert len(broker.pending_orders()) == 1
        assert broker.fills() == []


class TestFillDirection:
    def test_a_buy_fills_with_positive_quantity(self) -> None:
        broker, portfolio = _broker()
        broker.submit(_order(side="buy", quantity="2"))
        fills = broker.fill_pending(_bar(datetime(2026, 1, 5, 12, 15, tzinfo=UTC), "2000", "2001"))

        assert fills[0].quantity == Decimal(2)
        assert portfolio.position_quantity(SYMBOL) == Decimal(2)

    def test_a_sell_fills_with_negative_quantity(self) -> None:
        """`Fill` has no `side` field (§2.1), so direction lives in the
        sign, and `Portfolio` reads it from there."""
        broker, portfolio = _broker()
        broker.submit(_order(side="sell", quantity="2"))
        fills = broker.fill_pending(_bar(datetime(2026, 1, 5, 12, 15, tzinfo=UTC), "2000", "2001"))

        assert fills[0].quantity == Decimal(-2)
        assert portfolio.position_quantity(SYMBOL) == Decimal(-2)


class TestIdempotency:
    def test_resubmitting_the_same_client_order_id_queues_one_order(self) -> None:
        """§5.2: a process that dies between submitting and recording the
        response retries on restart with the same id. The retry must be a
        no-op, not a second position."""
        broker, portfolio = _broker()
        order = _order()
        broker.submit(order)
        broker.submit(order)

        fills = broker.fill_pending(_bar(datetime(2026, 1, 5, 12, 15, tzinfo=UTC), "2000", "2001"))

        assert len(fills) == 1
        assert portfolio.position_quantity(SYMBOL) == Decimal(1)

    def test_resubmitting_after_the_fill_does_not_reopen_it(self) -> None:
        broker, portfolio = _broker()
        order = _order()
        broker.submit(order)
        broker.fill_pending(_bar(datetime(2026, 1, 5, 12, 15, tzinfo=UTC), "2000", "2001"))
        broker.submit(order)
        later = broker.fill_pending(_bar(datetime(2026, 1, 5, 12, 30, tzinfo=UTC), "2001", "2002"))

        assert later == []
        assert portfolio.position_quantity(SYMBOL) == Decimal(1)

    def test_submit_returns_a_ref_carrying_the_client_order_id(self) -> None:
        broker, _ = _broker()
        ref = broker.submit(_order())

        assert ref == BrokerOrderRef(client_order_id="test-order")


class TestCancel:
    def test_cancelling_a_pending_order_stops_it_filling(self) -> None:
        broker, portfolio = _broker()
        ref = broker.submit(_order())
        broker.cancel(ref)
        fills = broker.fill_pending(_bar(datetime(2026, 1, 5, 12, 15, tzinfo=UTC), "2000", "2001"))

        assert fills == []
        assert portfolio.position_quantity(SYMBOL) == Decimal(0)

    def test_cancelling_an_unknown_order_is_harmless(self) -> None:
        broker, _ = _broker()
        broker.cancel(BrokerOrderRef(client_order_id="never-submitted"))

        assert broker.pending_orders() == []


class TestZeroCostModel:
    def test_no_fees_are_charged(self) -> None:
        broker, portfolio = _broker()
        broker.submit(_order())
        fills = broker.fill_pending(_bar(datetime(2026, 1, 5, 12, 15, tzinfo=UTC), "2000", "2001"))

        assert fills[0].fees == Decimal(0)
        assert portfolio.realised_pnl == Decimal(0)

    def test_buy_and_sell_fill_at_the_same_price(self) -> None:
        """No spread means no cost of crossing. That is the point of this
        model and the reason §2.8 forbids using it for evaluation."""
        broker, _ = _broker()
        bar = _bar(datetime(2026, 1, 5, 12, 15, tzinfo=UTC), "2000.00", "2010.00")
        broker.submit(_order(side="buy", suffix="-b"))
        broker.submit(_order(side="sell", suffix="-s"))
        fills = broker.fill_pending(bar)

        assert [fill.price for fill in fills] == [Decimal("2000.00"), Decimal("2000.00")]


class TestBrokerProtocolSurface:
    def test_positions_and_account_report_the_shared_ledger(self) -> None:
        broker, portfolio = _broker()
        broker.submit(_order(quantity="2"))
        broker.fill_pending(_bar(datetime(2026, 1, 5, 12, 15, tzinfo=UTC), "2000.00", "2005.00"))
        portfolio.mark(SYMBOL, ExitPrices.unadjusted(Decimal("2005.00")))

        positions = broker.positions()
        assert len(positions) == 1
        assert positions[0].quantity == Decimal(2)
        # 2 lots x 100 x (2005.00 - 2000.00) = 1000.00 unrealised
        assert broker.account().balance == Decimal(0)
        assert broker.account().equity == Decimal("1000.00")

    @pytest.mark.parametrize("symbol", ["XAUUSD", "EURUSD"])
    def test_market_is_open_whenever_a_bar_exists(self, symbol: str) -> None:
        broker, _ = _broker()
        assert broker.is_market_open(symbol) is True


# --- position modes (spec v3.12, §2.7 and §2.10; phase PC.1) -----------------


def _mode_order(
    side: str,
    quantity: str,
    n: int,
    *,
    closes: str | None = None,
    stop_loss: Decimal | None = None,
) -> Order:
    return Order(
        client_order_id=f"mode-{n}",
        symbol=SYMBOL,
        side=side,  # type: ignore[arg-type]
        quantity=Decimal(quantity),
        order_type="market",
        limit_price=None,
        stop_price=None,
        intent_id=f"mode-intent-{n}",
        closes_ticket=closes,
        stop_loss=stop_loss,
    )


_T0 = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def _next_bar(k: int) -> Bar:
    return _bar(_T0 + k * _BAR_WIDTH, "2000.00", "2000.00")


class TestHedgingSimBroker:
    """SimBroker behaves as a hedging account does (§2.7): every opening
    fill is a new ticket, a close names its ticket, and an opposite order
    that names none opens an opposite position -- which the ledger refuses
    to hold."""

    def test_opening_orders_get_new_tickets_in_sequence(self) -> None:
        broker, portfolio = _broker("hedging")
        broker.submit(_mode_order("buy", "0.30", 0))
        broker.submit(_mode_order("buy", "0.20", 1))
        fills = broker.fill_pending(_next_bar(1))

        assert [f.ticket for f in fills] == ["1", "2"]
        assert [t.ticket for t in portfolio.tickets(SYMBOL)] == ["1", "2"]

    def test_ticket_numbers_are_never_reused(self) -> None:
        broker, _ = _broker("hedging")
        broker.submit(_mode_order("buy", "0.10", 0))
        broker.fill_pending(_next_bar(1))
        broker.submit(_mode_order("sell", "0.10", 1, closes="1"))
        broker.fill_pending(_next_bar(2))
        broker.submit(_mode_order("buy", "0.10", 2))

        assert [f.ticket for f in broker.fill_pending(_next_bar(3))] == ["2"]

    def test_a_close_fills_against_the_ticket_it_names(self) -> None:
        broker, portfolio = _broker("hedging")
        broker.submit(_mode_order("buy", "0.30", 0))
        broker.submit(_mode_order("buy", "0.20", 1))
        broker.fill_pending(_next_bar(1))
        broker.submit(_mode_order("sell", "0.20", 2, closes="2"))
        (fill,) = broker.fill_pending(_next_bar(2))

        assert fill.ticket == "2"
        assert fill.quantity == Decimal("-0.20")
        assert [t.ticket for t in portfolio.tickets(SYMBOL)] == ["1"]

    def test_an_opposite_order_naming_no_ticket_is_caught_by_the_ledger(self) -> None:
        """Exactly what MT5 would do with it -- open a short beside the
        long -- so an engine that forgets to name tickets shows up as a
        broken invariant rather than being netted for it."""
        broker, _ = _broker("hedging")
        broker.submit(_mode_order("buy", "0.10", 0))
        broker.fill_pending(_next_bar(1))
        broker.submit(_mode_order("sell", "0.10", 1))

        with pytest.raises(BothDirectionsError):
            broker.fill_pending(_next_bar(2))

    def test_closing_a_ticket_that_is_not_open_is_rejected(self) -> None:
        broker, _ = _broker("hedging")
        broker.submit(_mode_order("sell", "0.10", 0, closes="7"))
        with pytest.raises(SimRejectionError, match="not open"):
            broker.fill_pending(_next_bar(1))

    def test_a_close_in_the_tickets_own_direction_is_rejected(self) -> None:
        broker, _ = _broker("hedging")
        broker.submit(_mode_order("buy", "0.10", 0))
        broker.fill_pending(_next_bar(1))
        broker.submit(_mode_order("buy", "0.10", 1, closes="1"))
        with pytest.raises(SimRejectionError, match="direction"):
            broker.fill_pending(_next_bar(2))

    def test_closing_more_than_the_ticket_holds_is_rejected(self) -> None:
        broker, _ = _broker("hedging")
        broker.submit(_mode_order("buy", "0.10", 0))
        broker.fill_pending(_next_bar(1))
        broker.submit(_mode_order("sell", "0.20", 1, closes="1"))
        with pytest.raises(SimRejectionError, match="holds"):
            broker.fill_pending(_next_bar(2))

    def test_positions_lists_every_ticket(self) -> None:
        broker, _ = _broker("hedging")
        broker.submit(_mode_order("buy", "0.30", 0))
        broker.submit(_mode_order("buy", "0.20", 1))
        broker.fill_pending(_next_bar(1))

        assert sorted(p.ticket for p in broker.positions()) == ["1", "2"]


class TestNettingSimBroker:
    def test_a_netting_fill_names_the_symbol_as_its_ticket(self) -> None:
        broker, _ = _broker("netting")
        broker.submit(_mode_order("buy", "0.10", 0))
        (fill,) = broker.fill_pending(_next_bar(1))
        assert fill.ticket == SYMBOL

    def test_an_order_naming_a_ticket_is_refused_under_netting(self) -> None:
        broker, _ = _broker("netting")
        broker.submit(_mode_order("sell", "0.10", 0, closes="1"))
        with pytest.raises(SimRejectionError, match="netting"):
            broker.fill_pending(_next_bar(1))


class TestBrokerMode:
    @pytest.mark.parametrize("mode", ["netting", "hedging"])
    def test_the_broker_reports_its_mode(self, mode: PositionMode) -> None:
        broker, _ = _broker(mode)
        assert broker.position_mode == mode

    def test_a_broker_and_ledger_in_different_modes_are_refused(self) -> None:
        portfolio = Portfolio(
            starting_balance=Decimal(0), contract_sizes=CONTRACT_SIZES, position_mode="netting"
        )
        with pytest.raises(ValueError, match="position mode"):
            SimBroker(cost_model=ZeroCostModel(), portfolio=portfolio, position_mode="hedging")

    def test_an_order_carrying_a_stop_loss_is_refused_until_stops_are_built(self) -> None:
        """Stop execution is PC.3. Accepting the field and ignoring it would
        run straight through the stop."""
        broker, _ = _broker("hedging")
        with pytest.raises(NotImplementedError, match=r"PC.3"):
            broker.submit(_mode_order("buy", "0.10", 0, stop_loss=Decimal("1990.00")))


# --- the opening part of each fill (spec v3.12, §2.8; phase PC.2) ------------


class _OpeningAsFee(ZeroCostModel):
    """Charges the opening quantity itself as the fee, so each fill's `fees`
    shows what the broker said opened."""

    def fees(self, order: Order, fill_price: Decimal, opening_quantity: Decimal) -> Decimal:  # noqa: ARG002
        return opening_quantity


def _fee_broker(mode: PositionMode) -> SimBroker:
    portfolio = Portfolio(
        starting_balance=Decimal(0), contract_sizes=CONTRACT_SIZES, position_mode=mode
    )
    return SimBroker(cost_model=_OpeningAsFee(), portfolio=portfolio, position_mode=mode)


def _opening_after(mode: PositionMode, held: str, side: str, lots: str) -> Decimal:
    """Hold `held` lots (signed; one opening order), then fill `side lots`
    -- naming the ticket under hedging if it reduces -- and return the
    opening quantity the broker reported for that second fill."""
    broker = _fee_broker(mode)
    if Decimal(held) != 0:
        broker.submit(_mode_order("buy" if Decimal(held) > 0 else "sell", held.lstrip("-"), 0))
        broker.fill_pending(_next_bar(1))
    reduces = Decimal(held) != 0 and (Decimal(held) > 0) != (side == "buy")
    closes = "1" if mode == "hedging" and reduces else None
    broker.submit(_mode_order(side, lots, 1, closes=closes))
    (fill,) = broker.fill_pending(_next_bar(2))
    return fill.fees


class TestOpeningQuantityHedging:
    def test_an_order_naming_no_ticket_opens_all_of_it(self) -> None:
        assert _opening_after("hedging", "0", "buy", "0.30") == Decimal("0.30")

    def test_an_add_is_a_new_ticket_and_opens_all_of_it(self) -> None:
        assert _opening_after("hedging", "0.30", "buy", "0.20") == Decimal("0.20")

    def test_a_close_opens_nothing(self) -> None:
        assert _opening_after("hedging", "0.30", "sell", "0.10") == Decimal(0)


class TestOpeningQuantityNetting:
    def test_from_flat_all_of_it_opens(self) -> None:
        assert _opening_after("netting", "0", "sell", "0.30") == Decimal("0.30")

    def test_an_add_opens_all_of_it(self) -> None:
        assert _opening_after("netting", "0.30", "buy", "0.20") == Decimal("0.20")

    def test_a_reduction_opens_nothing(self) -> None:
        assert _opening_after("netting", "0.30", "sell", "0.10") == Decimal(0)

    def test_an_exact_close_opens_nothing(self) -> None:
        assert _opening_after("netting", "-0.30", "buy", "0.30") == Decimal(0)

    def test_a_flip_opens_only_the_part_beyond_flat(self) -> None:
        # 0.30 long, sell 0.50: 0.30 closes, 0.20 opens short
        assert _opening_after("netting", "0.30", "sell", "0.50") == Decimal("0.20")
