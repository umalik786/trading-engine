"""AlwaysShort against the mirror of buy-and-hold, to the cent.

The sell-side counterpart of `test_always_long_vs_buy_and_hold.py`. §7.1
lists no short reference strategy, so until now nothing had taken a sell
order through the engine end to end: `Order.side` of "sell", a negative
`Fill.quantity`, a negative position and cost, and unrealised P&L moving
against the mark instead of with it.

As with the long test, the expected figure is supplied by the operator and
computed independently. Nothing in this repository computes a benchmark of
its own.

HOW TO ADD A CASE
-----------------
Add one `Case(...)` to `CASES` below. The existing fixtures in
`tests/golden/fixtures/` can be reused as they are -- a fixture is a price
series and knows nothing about which direction is being traded.

    Case(
        fixture="xauusd_m15_2025-02-05T0245_2025-02-12.csv",
        symbol="XAUUSD",
        lots=Decimal("1"),
        expected_pnl=Decimal("YOUR_FIGURE"),  # your figure, computed independently
    )

WHAT THE ENGINE WILL DO
-----------------------
Identical to the long case except for the sign:

- The order that opens the position is decided at the FIRST bar's close
  and filled at the SECOND bar's open.
- Nothing ever closes it. The run ends with it open, valued at the LAST
  bar's close.
- So the figure to compute independently is

      lots x contract_size x (second bar's open - last bar's close)

  which is the long figure with the subtraction the other way round, and
  `ZeroCostModel` means nothing is taken off it. On a week where the long
  made money the short loses the same amount, so `expected_pnl` here will
  usually be negative.

ONE NOTE ON FIXTURE CHOICE. The 00:00-start fixture cannot tell filling at
the next bar's open from filling at the deciding bar's close, because in
that week bar 2's open equals bar 1's close. That is a property of the
price series, so it is just as true here as it was for the long test. The
02:45-start fixture does distinguish them -- and because the sign is
flipped, a look-ahead engine would err in the opposite direction on the
short, which is worth knowing when reading a failure message.

`expected_pnl` is compared with `==`, not a tolerance.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest
from harness import FIXTURE_DIR, INSTRUMENTS_CONFIG, load_bars_from_csv, run_backtest

from engine.core.instruments import load_contract_sizes
from engine.strategies.reference.always_short import AlwaysShort


@dataclass(frozen=True)
class Case:
    fixture: str
    symbol: str
    lots: Decimal
    expected_pnl: Decimal


CASES: list[Case] = [
    # Operator: add cases here. See the module docstring above.

    Case(
        fixture="xauusd_m15_2025-02-05T0245_2025-02-12.csv",
        symbol="XAUUSD",
        lots=Decimal("1"),
        expected_pnl=Decimal("-4740"),
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.fixture)
def test_always_short_matches_the_mirror_of_buy_and_hold(case: Case) -> None:
    bars = load_bars_from_csv(FIXTURE_DIR / case.fixture, case.symbol)
    result = run_backtest(
        bars,
        AlwaysShort(symbol=case.symbol, quantity=case.lots),
        contract_sizes=load_contract_sizes(INSTRUMENTS_CONFIG),
    )

    assert len(result.orders) == 1, (
        "AlwaysShort holds one constant target, so it must produce exactly one "
        f"order across the whole run -- got {len(result.orders)}.{result.describe()}"
    )
    assert result.orders[0].side == "sell", (
        f"the one order must be a sell, got {result.orders[0].side!r}.{result.describe()}"
    )
    assert len(result.fills) == 1, (
        f"the single order must fill exactly once.{result.describe()}"
    )
    assert result.fills[0].quantity < 0, (
        "a sell fills with negative quantity -- Fill has no side field, so the sign "
        f"is where direction lives.{result.describe()}"
    )
    assert result.total_pnl == case.expected_pnl, (
        f"expected {case.expected_pnl}, engine reported {result.total_pnl}, "
        f"difference {result.total_pnl - case.expected_pnl}.{result.describe()}"
    )


def test_short_side_has_a_registered_fixture() -> None:
    """Fails until a case exists. The sell side is not demonstrated by the
    unit tests above it: those prove the strategy returns a negative
    target, not that the engine accounts for a short correctly."""
    assert CASES, (
        "No fixture registered, so AlwaysShort has never been compared against "
        "an independently computed figure, and the sell side has not been "
        "measured end to end. Add a Case to CASES in "
        "tests/golden/test_always_short_vs_buy_and_hold.py -- the module "
        "docstring says how."
    )
