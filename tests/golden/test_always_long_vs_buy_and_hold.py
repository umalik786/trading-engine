"""Phase 2 exit criterion: AlwaysLong matches buy-and-hold, to the cent.

Spec §9: "If `AlwaysLong` doesn't reproduce buy-and-hold exactly, your
accounting is wrong, and every result the system ever produces afterwards
will be wrong in the same invisible way."

The expected figure is supplied by the operator and computed
independently -- by hand, in a spreadsheet, from the price series. The
engine never computes a buy-and-hold benchmark of its own, and no code in
this repository does either. A benchmark produced by the same code being
tested would agree with it whatever either of them did.

HOW TO ADD A CASE
-----------------
Put the CSV in `tests/golden/fixtures/`, then add one `Case(...)` to
`CASES` below. Nothing else in this file changes.

    Case(
        fixture="xauusd_handmade.csv",   # file in tests/golden/fixtures/
        symbol="XAUUSD",                 # key in config/instruments.yaml
        lots=Decimal("1"),
        expected_pnl=Decimal("250.00"),  # your figure, computed independently
    )

The CSV header is, exactly:

    ts_open,ts_close,open,high,low,close,volume

with ISO-8601 timestamps carrying an offset ("2026-01-05T13:45:00Z") and
prices written as plain decimal text.

WHAT THE ENGINE WILL DO
-----------------------
So that your figure and its figure are answers to the same question:

- The strategy is asked for a target on every bar, including the first.
- The order that opens the position is decided at the FIRST bar's close
  and filled at the SECOND bar's open. There is no way to be in the
  market for the first bar -- a decision taken at a bar's close cannot be
  filled at that same bar's open, which has already happened.
- Nothing ever closes the position. The run ends with it still open,
  valued at the LAST bar's close.
- So the figure to compute independently is

      lots x contract_size x (last bar's close - second bar's open)

  and `ZeroCostModel` means no spread, commission or financing is taken
  off it.
- A weekend in the fixture changes nothing in that arithmetic. No bar
  exists for Saturday or Sunday and none is invented; the position is
  simply held across the gap (Appendix B.6).

`expected_pnl` is compared with `==`, not a tolerance. Both sides are
`Decimal`, so "to the cent" is meant literally.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest
from harness import FIXTURE_DIR, INSTRUMENTS_CONFIG, load_bars_from_csv, run_backtest

from engine.core.instruments import load_contract_sizes
from engine.strategies.reference.always_long import AlwaysLong


@dataclass(frozen=True)
class Case:
    fixture: str
    symbol: str
    lots: Decimal
    expected_pnl: Decimal


CASES: list[Case] = [
    # Operator: add cases here. See the module docstring above.
]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.fixture)
def test_always_long_matches_buy_and_hold(case: Case) -> None:
    bars = load_bars_from_csv(FIXTURE_DIR / case.fixture, case.symbol)
    result = run_backtest(
        bars,
        AlwaysLong(symbol=case.symbol, quantity=case.lots),
        contract_sizes=load_contract_sizes(INSTRUMENTS_CONFIG),
    )

    assert len(result.orders) == 1, (
        "AlwaysLong holds one constant target, so it must produce exactly one "
        f"order across the whole run -- got {len(result.orders)}.{result.describe()}"
    )
    assert len(result.fills) == 1, (
        f"the single order must fill exactly once.{result.describe()}"
    )
    assert result.total_pnl == case.expected_pnl, (
        f"expected {case.expected_pnl}, engine reported {result.total_pnl}, "
        f"difference {result.total_pnl - case.expected_pnl}.{result.describe()}"
    )


def test_exit_criterion_has_a_registered_fixture() -> None:
    """Fails until a case exists, because until one does, the phase 2 exit
    criterion has not been measured -- and a test suite that is green
    because it asserted nothing is the failure mode §9 warns about."""
    assert CASES, (
        "No fixture registered, so AlwaysLong has never been compared against "
        "buy-and-hold and phase 2 is not complete. Add a Case to CASES in "
        "tests/golden/test_always_long_vs_buy_and_hold.py -- the module "
        "docstring says how."
    )
