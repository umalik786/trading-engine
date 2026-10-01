"""AlwaysFlat: exactly zero P&L, zero orders. See spec §7.1.

Unlike the AlwaysLong criterion next door, the expected result here needs
no fixture and no independent calculation, because it is zero by
definition and cannot be anything else. The prices below move violently
on purpose: if the engine opened a position nobody asked for, valued
something that was never held, or carried state between runs, a large
number would appear where zero belongs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from harness import run_backtest

from engine.core.types import Bar
from engine.strategies.reference.always_flat import AlwaysFlat

SYMBOL = "XAUUSD"
CONTRACT_SIZES = {SYMBOL: Decimal(100)}
STARTING_BALANCE = Decimal("100000.00")
_BASE_TS = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
_BAR_WIDTH = timedelta(minutes=15)

# A crash and a spike, so any phantom position is worth a lot of money.
_CLOSES = ["2000.00", "2400.00", "1600.00", "2500.00", "1500.00", "2050.00"]


def _bars() -> list[Bar]:
    bars = []
    for index, close in enumerate(_CLOSES):
        ts_open = _BASE_TS + index * _BAR_WIDTH
        price = Decimal(close)
        bars.append(
            Bar(
                symbol=SYMBOL,
                ts_open=ts_open,
                ts_close=ts_open + _BAR_WIDTH,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=Decimal(1),
                is_final=True,
                spread=Decimal("0.20"),
            )
        )
    return bars


def test_always_flat_places_no_orders() -> None:
    result = run_backtest(
        _bars(),
        AlwaysFlat(symbol=SYMBOL),
        contract_sizes=CONTRACT_SIZES,
        starting_balance=STARTING_BALANCE,
    )
    assert result.orders == (), result.describe()
    assert result.fills == (), result.describe()
    assert result.unfilled_orders == (), result.describe()


def test_always_flat_earns_and_loses_nothing() -> None:
    result = run_backtest(
        _bars(),
        AlwaysFlat(symbol=SYMBOL),
        contract_sizes=CONTRACT_SIZES,
        starting_balance=STARTING_BALANCE,
    )
    assert result.total_pnl == Decimal(0), result.describe()
    assert result.realised_pnl == Decimal(0), result.describe()
    assert result.unrealised_pnl == Decimal(0), result.describe()
    assert result.final_equity == STARTING_BALANCE, result.describe()


def test_two_runs_of_always_flat_do_not_share_state() -> None:
    """State leakage is one of the two faults §7.1 gives this strategy to
    catch. If anything in the ledger, the broker or the strategy were
    class-level rather than per-instance, the second run would start with
    the first run's book."""
    first = run_backtest(
        _bars(),
        AlwaysFlat(symbol=SYMBOL),
        contract_sizes=CONTRACT_SIZES,
        starting_balance=STARTING_BALANCE,
    )
    second = run_backtest(
        _bars(),
        AlwaysFlat(symbol=SYMBOL),
        contract_sizes=CONTRACT_SIZES,
        starting_balance=STARTING_BALANCE,
    )
    assert first.final_equity == second.final_equity == STARTING_BALANCE
