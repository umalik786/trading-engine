"""Phase 3c.2 exit criterion: AlwaysLong and AlwaysShort with spread, the
spread CORRECTION, commission, financing and slippage, against figures
computed by hand before the engine's are seen.

The 3a/3b and 3c.1 golden tests are left untouched as regression checks:
their profiles name no correction, so their figures must not move.

THE RULES (approved 2026-11-20, docs/state.md "Wiring the correction")
---------------------------------------------------------------------
- The stored bar spread is the bar's MINIMUM (3c.0). The CHARGED spread is
      max(minimum, minimum + correction)
  where the correction, in points (1 point = 0.01 for XAUUSD), is looked up
  by the SERVER HOUR of the bar's open: UTC+2 in New York winter, UTC+3 in
  New York summer -- the US calendar, not the European one.
- Everything that used the bar's spread before now uses the charged spread:
  the buy's spread at the fill, the slippage (0.3 x the FILL bar's charged
  spread), and a short's valuation (last close + the LAST bar's charged
  spread). A long is still valued at the last close as quoted.
- Fill prices go on the 0.01 grid against the trader: a buy rounds UP, a
  sell rounds DOWN.
- Commission 3.50 per lot per side, once. Financing as in 3c.1: long -83.0,
  short +12.5 points per lot per night, contract size 100, triple on
  THURSDAY; the rollover is at server midnight.

THE TEST TABLE (hand-made, spread_correction_test_table.json)
-------------------------------------------------------------
    server hour  0 -> +5     server hour  2 -> -4 (floored: charge = minimum)
    server hour  1 -> +11    server hour 23 -> +30
    every other hour -> +7
Table cutoff 2025-03-01 00:00 UTC, before every bar in the fixture.

THE FIXTURE (xauusd_m15_2025-03-12T2045_2025-03-19.csv, 377 bars)
-----------------------------------------------------------------
New York moved to summer time on 9 March 2025, Europe not until 30 March,
so in this week the server is UTC+3 and a European-calendar clock would
wrongly say UTC+2.

                 UTC              open      close     stored spread
    deciding     Wed 12 Mar 20:45 2933.21   2932.56   0.65
    fill         Wed 12 Mar 22:00 2934.97   2935.09   0.27
    last         Tue 18 Mar 23:45 3033.62   3031.57   0.24

HOW TO FILL IN A FIGURE
-----------------------
Replace `expected_pnl=None` with your own `Decimal("...")`. Until then each
case fails with a message saying so; the structural assertions still run.
The engine's own figure is deliberately not shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal

import pytest
from harness import FIXTURE_DIR, INSTRUMENTS_CONFIG, load_bars_from_csv, run_backtest

from engine.core.clock import DstSwitchedServerClock
from engine.core.instruments import load_contract_sizes, load_instrument_specs
from engine.costs.configured import ConfiguredCostModel
from engine.costs.correction_table import load_correction_table
from engine.costs.profile import load_cost_profile
from engine.strategies.reference.always_long import AlwaysLong
from engine.strategies.reference.always_short import AlwaysShort

FIXTURE = "xauusd_m15_2025-03-12T2045_2025-03-19.csv"
COST_PROFILE = FIXTURE_DIR / "cost_test_profile_correction.yaml"
TABLE = FIXTURE_DIR / "spread_correction_test_table.json"
SYMBOL = "XAUUSD"
LOTS = Decimal("1")
POINT = Decimal("0.01")


@dataclass(frozen=True)
class Case:
    direction: str  # "long" | "short"
    expected_pnl: Decimal | None  # None until the operator computes it


CASES = [
    Case(direction="long", expected_pnl=None),
    Case(direction="short", expected_pnl=None),
]


def _profile():
    with pytest.warns(UserWarning, match="verification is incomplete"):
        return load_cost_profile(COST_PROFILE)


def _model() -> ConfiguredCostModel:
    return ConfiguredCostModel(
        _profile(), load_instrument_specs(INSTRUMENTS_CONFIG), load_correction_table(TABLE)
    )


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
        cost_model=_model(),
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.direction)
def test_reference_strategy_matches_the_hand_computed_figure(case: Case) -> None:
    result = _run(case.direction)
    expected_side = "buy" if case.direction == "long" else "sell"

    # Structural assertions only -- none prints a price or P&L.
    assert len(result.orders) == 1, f"expected one order, got {len(result.orders)}"
    assert result.orders[0].side == expected_side
    assert len(result.fills) == 1, f"expected one fill, got {len(result.fills)}"
    assert result.fills[0].fees == Decimal("3.50"), "commission must be 3.50, in Fill.fees"
    assert result.realised_pnl == Decimal("-3.50")
    assert result.financing_accrued != Decimal(0), "financing should have accrued"
    assert result.fills[0].price % POINT == 0, "the fill must land on the 0.01 price grid"
    assert result.unfilled_orders == ()

    if case.expected_pnl is None:
        pytest.fail(
            f"No hand-computed figure for the {case.direction} case yet, so the phase "
            "3c.2 exit criterion has not been measured. The structural assertions "
            "passed. The engine's own figure is deliberately NOT shown: the bars, the "
            "table and the rules are in the module docstring."
        )

    assert result.total_pnl == case.expected_pnl, (
        f"expected {case.expected_pnl}, engine reported {result.total_pnl}, "
        f"difference {result.total_pnl - case.expected_pnl}.{result.describe()}"
    )


def test_the_fixture_can_catch_each_correction_bug() -> None:
    """What makes this fixture worth using, checked in code with no amounts
    printed. Each bug the breaks will introduce must change a charged spread
    that a figure depends on."""
    bars = load_bars_from_csv(FIXTURE_DIR / FIXTURE, SYMBOL)
    fill, last = bars[1], bars[-1]
    table = load_correction_table(TABLE).instruments[SYMBOL]
    us = DstSwitchedServerClock(*_offsets(), "America/New_York")
    eu = DstSwitchedServerClock(*_offsets(), "Europe/Prague")

    def charged(bar, hour):
        return bar.spread + max(Decimal(table.value(hour)), Decimal(0)) * POINT

    def hour(clock, moment):
        return clock.to_server_naive(moment).hour

    # Every check below fails with a message only, never with the amounts it
    # compared: a printed price would give away part of a hand figure.
    def require(condition: bool, message: str) -> None:
        if not condition:
            pytest.fail(message, pytrace=False)

    # The European calendar must move both the fill (long) and the last bar (short).
    for name, bar in (("fill", fill), ("last", last)):
        require(hour(us, bar.ts_open) != hour(eu, bar.ts_open), f"{name}: calendars agree")
        require(
            charged(bar, hour(us, bar.ts_open)) != charged(bar, hour(eu, bar.ts_open)),
            f"{name}: the European calendar would charge the same spread",
        )

    # Filing the last bar under its CLOSE hour instead of its open must move the short.
    require(
        charged(last, hour(us, last.ts_close)) != charged(last, hour(us, last.ts_open)),
        "last bar: its close hour and open hour charge the same spread",
    )

    # The last bar's correction is negative, so dropping the floor moves the short.
    require(table.value(hour(us, last.ts_open)) < 0, "last bar's correction is not negative")

    # The fill's correction is positive, so the long sees the correction at all.
    require(table.value(hour(us, fill.ts_open)) > 0, "fill's correction is not positive")

    # With the charged spread, slippage rounding against the trader must still
    # differ from rounding to nearest, for the buy and the sell. The third
    # decimal of both fills is (3 x charged spread in points) mod 10, and only
    # 1-4 separates the two roundings on both sides.
    multiple = _profile().instruments[SYMBOL].slippage.value
    spread = charged(fill, hour(us, fill.ts_open))
    raw_buy = fill.open + spread + multiple * spread
    raw_sell = fill.open - multiple * spread
    for side, raw, adverse in (("buy", raw_buy, ROUND_CEILING), ("sell", raw_sell, ROUND_FLOOR)):
        require(
            raw.quantize(POINT, rounding=adverse) != raw.quantize(POINT, rounding=ROUND_HALF_EVEN),
            f"{side}: rounding against the trader and to nearest agree",
        )

    # No zero spreads, so the fallback is never reached (and never corrected).
    require(all(bar.spread > 0 for bar in bars), "the fixture contains a zero spread")


def _offsets():
    from datetime import timedelta  # noqa: PLC0415

    return timedelta(hours=2), timedelta(hours=3)
