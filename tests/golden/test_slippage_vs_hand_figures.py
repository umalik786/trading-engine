"""Phase 3c.1 exit criterion: AlwaysLong and AlwaysShort with spread,
commission, financing AND slippage, against figures computed by hand.

The 3a/3b golden test (test_costs_vs_hand_figures.py) is left untouched as a
regression check: its profile carries zero slippage, so its figures must not
move. This file uses cost_test_profile_slippage.yaml, identical to the 3a/3b
profile except for its name and a slippage block, so the only thing that can
move a figure here relative to 3a/3b is slippage.

THE RULES (operator decisions 2026-11-19, spec v3.11 §2.8)
----------------------------------------------------------
- Slippage = 0.3 x the spread the fill is charged -- the FILL bar's spread.
- Always against the trader: a buy fills higher, a sell lower.
- On a bid basis a sell pays no spread, but it STILL pays slippage, scaled by
  the fill bar's spread.
- The fill price is then put on the 0.01 price grid, rounded against the
  trader: a buy rounds UP, a sell rounds DOWN -- never to nearest.
- Slippage is paid on the fill ONLY. The open position is valued exactly as
  in 3a/3b: a long at the last close as quoted, a short at the last close
  plus the last bar's spread. Neither valuation includes slippage.
- Everything else -- commission 3.50 once, six nights of financing -- is as in
  3a/3b.

THE FIXTURE, AND WHY IT CAN CATCH THE BUGS
------------------------------------------
Same 21:45 window as 3a/3b:

    deciding bar   2025-02-05 21:45   close 2865.18   spread 0.64
    fill bar       2025-02-05 23:00   open  2867.50   spread 0.27
    last bar       2025-02-11 23:45   close 2898.59   spread 0.23

Its three spreads all differ, so slippage taken from the wrong bar gives a
different amount. At a multiple of 0.3 both fills land off the price grid
where rounding against the trader and rounding to nearest disagree. Both
properties are guarded by the last test in this file.

HOW TO FILL IN A FIGURE
-----------------------
Replace `expected_pnl=None` with your own `Decimal("...")`. Until then each
case fails with a message saying so; the structural assertions above it
still run. The engine's own figure is deliberately not shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal

import pytest
from harness import FIXTURE_DIR, INSTRUMENTS_CONFIG, load_bars_from_csv, run_backtest

from engine.core.instruments import load_contract_sizes, load_instrument_specs
from engine.costs.configured import ConfiguredCostModel
from engine.costs.profile import load_cost_profile
from engine.strategies.reference.always_long import AlwaysLong
from engine.strategies.reference.always_short import AlwaysShort

FIXTURE = "xauusd_m15_2025-02-05T2145_2025-02-12.csv"
COST_PROFILE = FIXTURE_DIR / "cost_test_profile_slippage.yaml"
SYMBOL = "XAUUSD"
LOTS = Decimal("1")
PRICE_GRID = Decimal("0.01")


@dataclass(frozen=True)
class Case:
    direction: str  # "long" | "short"
    expected_pnl: Decimal | None  # None until the operator computes it


CASES = [
    # Operator's hand figures, 2026-11-19, computed before the engine's
    # figure was seen. The 3a/3b figures were 2580.50 and -3060.50.
    Case(direction="long", expected_pnl=Decimal("2571.50")),
    Case(direction="short", expected_pnl=Decimal("-3069.50")),
]


def _profile():
    with pytest.warns(UserWarning, match="verification is incomplete"):
        return load_cost_profile(COST_PROFILE)


def _run(direction: str):
    bars = load_bars_from_csv(FIXTURE_DIR / FIXTURE, SYMBOL)
    strategy = (
        AlwaysLong(symbol=SYMBOL, quantity=LOTS)
        if direction == "long"
        else AlwaysShort(symbol=SYMBOL, quantity=LOTS)
    )
    return run_backtest(
        bars,
        strategy,
        contract_sizes=load_contract_sizes(INSTRUMENTS_CONFIG),
        cost_model=ConfiguredCostModel(_profile(), load_instrument_specs(INSTRUMENTS_CONFIG)),
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.direction)
def test_reference_strategy_matches_the_hand_computed_figure(case: Case) -> None:
    result = _run(case.direction)
    expected_side = "buy" if case.direction == "long" else "sell"

    # Structural assertions only, and none that print a price or P&L while a
    # figure is outstanding -- those are meant to be computed blind.
    assert len(result.orders) == 1, f"expected one order, got {len(result.orders)}"
    assert result.orders[0].side == expected_side, (
        f"expected a {expected_side}, got {result.orders[0].side!r}"
    )
    assert len(result.fills) == 1, f"expected one fill, got {len(result.fills)}"
    assert result.fills[0].fees == Decimal("3.50"), "commission must be 3.50, in Fill.fees"
    assert result.realised_pnl == Decimal("-3.50"), (
        "the only realised amount is the commission; financing sits on the open position"
    )
    assert result.financing_accrued != Decimal(0), "six nights of financing should have accrued"
    assert result.fills[0].price % PRICE_GRID == 0, "the fill must land on the 0.01 price grid"
    assert result.unfilled_orders == (), f"{len(result.unfilled_orders)} order(s) never filled"

    if case.expected_pnl is None:
        pytest.fail(
            f"No hand-computed figure for the {case.direction} case yet, so the "
            "phase 3c.1 exit criterion has not been measured. The structural "
            "assertions above passed: one order, correct side, one fill on the "
            "price grid, 3.50 commission, financing accrued.\n\n"
            "The engine's own figure is deliberately NOT shown here: a figure "
            "computed after reading the engine's is a transcription, not a check. "
            "The bars and rules you need are in the module docstring."
        )

    assert result.total_pnl == case.expected_pnl, (
        f"expected {case.expected_pnl}, engine reported {result.total_pnl}, "
        f"difference {result.total_pnl - case.expected_pnl}.{result.describe()}"
    )


def test_the_fixture_can_catch_each_slippage_bug() -> None:
    """Guards what makes this fixture worth using. Checked in code, with no
    amounts printed, so it gives nothing away before the hand figures."""
    bars = load_bars_from_csv(FIXTURE_DIR / FIXTURE, SYMBOL)
    deciding, fill, last = bars[0], bars[1], bars[-1]
    multiple = _profile().instruments[SYMBOL].slippage.value

    # Slippage taken from the wrong bar must give a different amount.
    amounts = {multiple * b.spread for b in (deciding, fill, last)}
    assert len(amounts) == 3, "deciding, fill and last bars give the same slippage"

    # Rounding against the trader must differ from rounding to nearest, both sides.
    raw_buy = fill.open + fill.spread + multiple * fill.spread
    raw_sell = fill.open - multiple * fill.spread
    for raw, adverse in ((raw_buy, ROUND_CEILING), (raw_sell, ROUND_FLOOR)):
        against = raw.quantize(PRICE_GRID, rounding=adverse)
        nearest = raw.quantize(PRICE_GRID, rounding=ROUND_HALF_EVEN)
        assert against != nearest, (
            "on this fixture rounding against the trader and rounding to nearest "
            "agree, so the rounding rule would go untested"
        )
