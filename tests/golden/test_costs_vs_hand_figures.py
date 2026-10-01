"""Phase 3a exit criterion: AlwaysLong and AlwaysShort with spread and
commission, against figures computed by hand.

Spec §9 phase 3: "`AlwaysLong` matches buy-and-hold minus a cost figure you
can derive by hand." This is that test, extended to the short side, because
a cost model that only adjusts buys passes the long and overstates every
short.

THE FIXTURE IS CHOSEN SO THE WRONG-BAR BUG CANNOT HIDE
------------------------------------------------------
The 02:45 window used in phase 2 cannot be used here. In it the deciding
bar and the fill bar happen to carry the same spread, 0.29, so taking the
spread from the wrong one of the two changes nothing. That is the phase 2
lesson repeating one layer down: the fixture that caught the fill-PRICE
bug cannot catch the fill-SPREAD bug.

The 21:45 window has three different spreads where it matters:

    deciding bar   2025-02-05 21:45   close 2865.18   spread 0.64
    fill bar       2025-02-05 23:00   open  2867.50   spread 0.27
    last bar       2025-02-11 23:45   close 2898.59   spread 0.23

Those four numbers, the 3.50 commission and the contract size of 100 are
everything a hand figure needs.

So a spread taken from the deciding bar instead of the fill bar moves the
long's figure by 0.37 a lot, which is 37.00 on one lot of XAUUSD -- far too
large to mistake for anything else.

The fill bar is 23:00 rather than 22:00 because the 21:45 bar is the last
before gold's daily session break. The order fills at the next bar that
EXISTS, an hour and a quarter later (Appendix B.6), so this window
exercises the session gap as well as the spread.

COST PROFILE
------------
`fixtures/cost_test_profile.yaml`: bid basis, commission 3.50 per lot per
side, slippage zero. The bid basis is an assumption OF THIS TEST, chosen so
a figure can be computed by hand. It is not a claim about FTMO, whose
`chart_mode` has never been captured -- see `config/cost_ftmo_demo.yaml`.

WHAT THE ENGINE WILL DO
-----------------------
- The order is decided at the FIRST bar's close and fills at the SECOND
  bar's open, using the SECOND bar's spread.
- On a bid basis a buy pays the spread at the fill and a sell does not.
- Nothing closes the position. It is valued at the last bar's close: a long
  at that close as quoted, a short at that close PLUS the last bar's
  spread, because closing a short means buying at the ask.
- Commission is charged once, on the one fill, at 3.50 per lot. It lands in
  `Fill.fees` and reduces realised P&L, where the spread instead sits
  inside the fill price.
- So the long's spread cost comes from the FILL bar and the short's from
  the LAST bar. The two are deliberately not symmetric.

HOW TO FILL IN A FIGURE
-----------------------
Replace `expected_pnl=None` with your own `Decimal("...")`. Until then
each case fails with a message saying so -- the structural assertions
above it still run, so the mechanics are checked while the figure is
outstanding.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest
from harness import FIXTURE_DIR, INSTRUMENTS_CONFIG, load_bars_from_csv, run_backtest

from engine.core.instruments import load_contract_sizes
from engine.costs.configured import ConfiguredCostModel
from engine.costs.profile import load_cost_profile
from engine.strategies.reference.always_long import AlwaysLong
from engine.strategies.reference.always_short import AlwaysShort

FIXTURE = "xauusd_m15_2025-02-05T2145_2025-02-12.csv"
COST_PROFILE = FIXTURE_DIR / "cost_test_profile.yaml"
SYMBOL = "XAUUSD"
LOTS = Decimal("1")


@dataclass(frozen=True)
class Case:
    direction: str  # "long" | "short"
    expected_pnl: Decimal | None  # None until the operator computes it


CASES = [
    Case(direction="long", expected_pnl=Decimal("3078.5")),
    Case(direction="short", expected_pnl=Decimal("-3135.5")),
]


def _run(direction: str):
    bars = load_bars_from_csv(FIXTURE_DIR / FIXTURE, SYMBOL)
    strategy = (
        AlwaysLong(symbol=SYMBOL, quantity=LOTS)
        if direction == "long"
        else AlwaysShort(symbol=SYMBOL, quantity=LOTS)
    )
    with pytest.warns(UserWarning, match="verification is incomplete"):
        profile = load_cost_profile(COST_PROFILE)
    contract_sizes = load_contract_sizes(INSTRUMENTS_CONFIG)
    return run_backtest(
        bars,
        strategy,
        contract_sizes=contract_sizes,
        cost_model=ConfiguredCostModel(profile, contract_sizes),
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.direction)
def test_reference_strategy_matches_the_hand_computed_figure(case: Case) -> None:
    result = _run(case.direction)
    expected_side = "buy" if case.direction == "long" else "sell"

    # No result.describe() anywhere in this file, on purpose: it prints
    # total and unrealised P&L and the fill price, and these figures are
    # meant to be computed blind. Each message below carries only what is
    # structural, or what the profile already fixes.
    assert len(result.orders) == 1, (
        "a constant target must produce exactly one order across the run -- "
        f"got {len(result.orders)}"
    )
    assert result.orders[0].side == expected_side, (
        f"expected a {expected_side}, got {result.orders[0].side!r}"
    )
    assert len(result.fills) == 1, (
        f"the single order must fill exactly once -- got {len(result.fills)}"
    )
    assert result.fills[0].fees == Decimal("3.50"), (
        "commission is 3.50 per lot per side on one lot, and it belongs in "
        f"Fill.fees rather than in the price -- got {result.fills[0].fees}"
    )
    assert result.realised_pnl == Decimal("-3.50"), (
        "the only realised amount is the commission, because nothing has "
        f"been closed -- got {result.realised_pnl}"
    )
    assert result.unfilled_orders == (), (
        f"{len(result.unfilled_orders)} order(s) never filled"
    )

    if case.expected_pnl is None:
        pytest.fail(
            f"No hand-computed figure for the {case.direction} case yet, so the "
            "phase 3a exit criterion has not been measured. The structural "
            "assertions above it passed: one order, correct side, one fill, "
            "3.50 commission.\n\n"
            "The engine's own figure is deliberately NOT shown here. A figure "
            "computed after reading the engine's is not an independent check "
            "of it -- it is a transcription. Work yours out from the fixture, "
            "set expected_pnl in CASES, and let the comparison fail or pass on "
            "its own.\n\n"
            "The bars you need are in the module docstring above."
        )

    assert result.total_pnl == case.expected_pnl, (
        f"expected {case.expected_pnl}, engine reported {result.total_pnl}, "
        f"difference {result.total_pnl - case.expected_pnl}.{result.describe()}"
    )


def test_the_fixture_can_distinguish_the_fill_bar_from_the_deciding_bar() -> None:
    """Guards the property that makes this fixture worth using. If a future
    re-export produced a window whose deciding and fill bars shared a
    spread, every test above would still pass while quietly losing the
    ability to catch a spread taken from the wrong bar."""
    bars = load_bars_from_csv(FIXTURE_DIR / FIXTURE, SYMBOL)
    deciding, fill, last = bars[0], bars[1], bars[-1]

    assert deciding.spread != fill.spread, (
        f"deciding bar and fill bar share a spread of {fill.spread}, so this "
        "fixture cannot catch a spread taken from the deciding bar"
    )
    assert fill.spread != last.spread, (
        f"fill bar and last bar share a spread of {fill.spread}, so this "
        "fixture cannot separate the long's cost from the short's"
    )
    assert fill.open != deciding.close, (
        "fill bar's open equals the deciding bar's close, so this fixture "
        "cannot catch a fill taken at the deciding bar's close"
    )
