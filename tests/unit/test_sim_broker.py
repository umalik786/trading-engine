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
from engine.brokers.sim import SimBroker
from engine.core.portfolio import Portfolio
from engine.core.types import Bar, Order
from engine.costs.zero import ZeroCostModel

SYMBOL = "XAUUSD"
CONTRACT_SIZES = {SYMBOL: Decimal(100), "EURUSD": Decimal(100000)}
_BAR_WIDTH = timedelta(minutes=15)


def _broker() -> tuple[SimBroker, Portfolio]:
    portfolio = Portfolio(starting_balance=Decimal(0), contract_sizes=CONTRACT_SIZES)
    return SimBroker(cost_model=ZeroCostModel(), portfolio=portfolio), portfolio


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
        portfolio.mark(SYMBOL, Decimal("2005.00"))

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
