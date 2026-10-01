"""How a target position becomes an order -- and when it must not.

A target says where to be. The order is the difference between that and
where the engine already is. "Already is" has to include orders that have
been submitted and have not filled yet, or the same gap gets ordered twice.

With a single instrument the fault is invisible, because every bar fills
the previous bar's order before the strategy is asked again. It appears as
soon as two instruments interleave: a bar for EURUSD cannot fill a pending
XAUUSD order, so if the strategy is asked for its XAUUSD target while that
order is still queued, an engine counting only filled lots sees a flat
book and orders the whole position a second time -- under a new
client_order_id, so §5.2 idempotency does not catch it either. Both fill.
The position is double the intended size.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from harness import run_backtest

from engine.core.types import Bar
from engine.strategies.reference.always_long import AlwaysLong

CONTRACT_SIZES = {"XAUUSD": Decimal(100), "EURUSD": Decimal(100000)}
_BASE_TS = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
_BAR_WIDTH = timedelta(minutes=15)


def _bar(symbol: str, index: int, price: str) -> Bar:
    ts_open = _BASE_TS + index * _BAR_WIDTH
    value = Decimal(price)
    return Bar(
        symbol=symbol,
        ts_open=ts_open,
        ts_close=ts_open + _BAR_WIDTH,
        open=value,
        high=value,
        low=value,
        close=value,
        volume=Decimal(1),
        is_final=True,
        spread=Decimal("0.20"),
    )


def _interleaved_bars() -> list[Bar]:
    """Two instruments arriving alternately, as two feeds merged by time
    would deliver them."""
    return [
        _bar("XAUUSD", 0, "2000.00"),
        _bar("EURUSD", 1, "1.1000"),
        _bar("XAUUSD", 2, "2010.00"),
        _bar("EURUSD", 3, "1.1010"),
        _bar("XAUUSD", 4, "2020.00"),
        _bar("EURUSD", 5, "1.1020"),
    ]


def test_a_pending_order_is_not_ordered_again_when_another_symbols_bar_intervenes() -> None:
    result = run_backtest(
        _interleaved_bars(),
        AlwaysLong(symbol="XAUUSD", quantity=Decimal(1)),
        contract_sizes=CONTRACT_SIZES,
    )

    assert len(result.orders) == 1, result.describe()
    assert len(result.fills) == 1, result.describe()


def test_the_resulting_position_is_the_size_that_was_asked_for() -> None:
    """The assertion that matters. Ordering twice is only a counting
    nuisance; filling twice is a position of double the intended size,
    carrying double the intended risk."""
    result = run_backtest(
        _interleaved_bars(),
        AlwaysLong(symbol="XAUUSD", quantity=Decimal(1)),
        contract_sizes=CONTRACT_SIZES,
    )

    assert sum(fill.quantity for fill in result.fills) == Decimal(1), result.describe()


def test_nothing_is_left_queued_at_the_end_of_the_run() -> None:
    result = run_backtest(
        _interleaved_bars(),
        AlwaysLong(symbol="XAUUSD", quantity=Decimal(1)),
        contract_sizes=CONTRACT_SIZES,
    )

    assert result.unfilled_orders == (), result.describe()
