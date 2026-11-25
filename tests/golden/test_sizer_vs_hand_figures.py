"""Phase 3c.3 exit criterion: the sizer's lot sizes, then AlwaysLong and
AlwaysShort sized by weight and by stop, against figures computed by hand
before the engine's are seen.

The earlier golden tests are untouched regression checks: they use
FixedQuantitySizer, whose behaviour has not changed.

THE RULES (approved 2026-11-23, docs/state.md, 3c.3)
---------------------------------------------------
"close" is the DECIDING bar's close; "equity" is equity marked at that close.
    weight w, no stop:  |w| x equity / (contract size x close)
    a stop:             risk fraction x equity / (contract size x |close - stop|)
                        (the weight then gives only the direction)
then: round TOWARD ZERO to a whole number of steps; below the minimum -> 0;
above the maximum -> the maximum; apply the sign. The position is sized once,
on entry, and then held.

THE TEST INSTRUMENT AND CONFIG (fixtures/instruments_sizer_test.yaml,
fixtures/sizing_test.yaml) -- test data, chosen to separate the bugs
---------------------------------------------------------------------
    XAUUSD contract size 100, point 0.01
    volume minimum 0.20, step 0.05, maximum 3.00
    risk fraction 0.04
    starting balance 100,000.00 (so equity at the first decision is 100,000.00)

THE BARS AND COSTS: the 3c.2 golden fixture, profile and table, unchanged
-------------------------------------------------------------------------
    deciding  Wed 12 Mar 2025 20:45 UTC  open 2933.21  close 2932.56
    fill      Wed 12 Mar 2025 22:00 UTC  open 2934.97
    last      Tue 18 Mar 2025 23:45 UTC  close 3031.57
Every cost rule is 3c.2's. Your 3c.2 working gives each run's prices; the
lots scale the money: commission 3.50 per lot, financing per lot.

HOW TO FILL IN A FIGURE
-----------------------
Replace each `expected=None` with your own `Decimal("...")`: lots for L1-L8,
total P&L for the four runs. Until then each case fails with a message
saying so, and the engine's own figure is deliberately not shown.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from math import floor

import pytest
from harness import FIXTURE_DIR, load_bars_from_csv, run_backtest

from engine.core.instruments import load_instrument_specs
from engine.core.portfolio import Position
from engine.core.types import TargetPosition
from engine.costs.configured import ConfiguredCostModel
from engine.costs.correction_table import load_correction_table
from engine.costs.profile import load_cost_profile
from engine.sizing.base import SizingContext
from engine.sizing.equity import EquitySizer, load_sizing_config
from engine.strategies.reference.always_long import AlwaysLong
from engine.strategies.reference.always_short import AlwaysShort

FIXTURE = "xauusd_m15_2025-03-12T2045_2025-03-19.csv"
INSTRUMENTS = FIXTURE_DIR / "instruments_sizer_test.yaml"
SIZING = FIXTURE_DIR / "sizing_test.yaml"
COST_PROFILE = FIXTURE_DIR / "cost_test_profile_correction.yaml"
TABLE = FIXTURE_DIR / "spread_correction_test_table.json"
SYMBOL = "XAUUSD"
BALANCE = Decimal("100000.00")
POINT = Decimal("0.01")

WEIGHT = Decimal("2.3")
LONG_STOP = Decimal("2918")
SHORT_STOP = Decimal("3066")


# --- the lot-size table: L1-L8 -------------------------------------------------


@dataclass(frozen=True)
class LotCase:
    name: str
    weight: Decimal  # signed
    stop: Decimal | None
    expected: Decimal | None  # signed lots; None until the operator computes it
    equity: Decimal = BALANCE
    balance: Decimal = BALANCE
    note: str = field(default="", compare=False)


LOT_CASES = [
    LotCase("L1", WEIGHT, None, Decimal("0.75"), note="weight 2.3, long, from flat"),
    LotCase("L2", -WEIGHT, None, Decimal("-0.75"), note="weight 2.3, short, from flat"),
    LotCase("L3", Decimal(1), LONG_STOP, Decimal("2.70"), note="stop 2918, long"),
    LotCase("L4", Decimal(-1), SHORT_STOP, Decimal("-0.25"), note="stop 3066, short"),
    LotCase("L5", Decimal("0.4"), None, Decimal("0"), note="weight 0.4: below the minimum"),
    LotCase("L6", Decimal(10), None, Decimal("3.00"), note="weight 10: above the maximum"),
    LotCase(
        "L7",
        WEIGHT,
        None,
        Decimal("0.85"),
        equity=Decimal("108750.00"),
        balance=Decimal("100000.00"),
        note="weight 2.3, equity 108,750.00 with balance 100,000.00 (a position open elsewhere)",
    ),
    LotCase(
        "L8", Decimal("3.372444"), None, Decimal("1.15"), note="weight 3.372444: exactly on a step"
    ),
]


class Book:
    """Balance and equity set directly, as if a position were open in
    another instrument; nothing is held in XAUUSD itself."""

    def __init__(self, equity: Decimal, balance: Decimal) -> None:
        self._equity, self._balance = equity, balance

    @property
    def balance(self) -> Decimal:
        return self._balance

    @property
    def equity(self) -> Decimal:
        return self._equity

    def position_quantity(self, symbol: str) -> Decimal:  # noqa: ARG002
        return Decimal(0)

    def positions(self) -> Mapping[str, Position]:
        return {}


def _target(weight: Decimal, stop: Decimal | None) -> TargetPosition:
    return TargetPosition(
        symbol=SYMBOL,
        quantity=None,
        weight=weight,
        stop_price=stop,
        take_profit=None,
        reason="3c.3 golden",
        confidence=None,
    )


def _deciding_bar():
    return load_bars_from_csv(FIXTURE_DIR / FIXTURE, SYMBOL)[0]


def _spec():
    return load_instrument_specs(INSTRUMENTS)[SYMBOL]


@pytest.mark.parametrize("case", LOT_CASES, ids=lambda case: case.name)
def test_lot_size_matches_the_hand_computed_figure(case: LotCase) -> None:
    sizer = EquitySizer(load_sizing_config(SIZING))
    lots = sizer.size(
        _target(case.weight, case.stop),
        Book(case.equity, case.balance),
        {},
        SizingContext(bar=_deciding_bar(), committed=Decimal(0), spec=_spec()),
    )
    if case.expected is None:
        pytest.fail(
            f"No hand-computed lot size for {case.name} ({case.note}) yet. The engine's "
            "own figure is deliberately NOT shown.",
            pytrace=False,
        )
    assert lots == case.expected, f"{case.name}: expected {case.expected}, sizer gave {lots}"


# --- the four runs --------------------------------------------------------------


@dataclass(frozen=True)
class RunCase:
    name: str
    lots_case: str  # the L-case whose decision this run makes
    expected_pnl: Decimal | None  # None until the operator computes it


RUN_CASES = [
    RunCase("long-weight", "L1", Decimal("6831.375")),
    RunCase("short-weight", "L2", Decimal("-7218.375")),
    RunCase("long-stop", "L3", Decimal("24592.95")),
    RunCase("short-stop", "L4", Decimal("-2406.125")),
]


def _strategy(name: str):
    weight = Decimal(1) if "stop" in name else WEIGHT
    stop = {"long-stop": LONG_STOP, "short-stop": SHORT_STOP}.get(name)
    cls = AlwaysLong if name.startswith("long") else AlwaysShort
    return cls(SYMBOL, weight=weight, stop_price=stop)


def _model() -> ConfiguredCostModel:
    with pytest.warns(UserWarning, match="verification is incomplete"):
        profile = load_cost_profile(COST_PROFILE)
    return ConfiguredCostModel(
        profile, load_instrument_specs(INSTRUMENTS), load_correction_table(TABLE)
    )


def _run(name: str):
    specs = load_instrument_specs(INSTRUMENTS)
    return run_backtest(
        load_bars_from_csv(FIXTURE_DIR / FIXTURE, SYMBOL),
        _strategy(name),
        position_mode="hedging",
        contract_sizes={s: spec.contract_size for s, spec in specs.items()},
        instruments=specs,
        starting_balance=BALANCE,
        cost_model=_model(),
        sizer=EquitySizer(load_sizing_config(SIZING)),
    )


@pytest.mark.parametrize("case", RUN_CASES, ids=lambda case: case.name)
def test_reference_strategy_matches_the_hand_computed_figure(case: RunCase) -> None:
    result = _run(case.name)
    expected_side = "buy" if case.name.startswith("long") else "sell"

    # Structural assertions only -- none prints a lot size, price or P&L.
    assert len(result.orders) == 1, "expected exactly one order: sized once, then held"
    assert result.orders[0].side == expected_side
    assert len(result.fills) == 1, "expected exactly one fill"
    fill = result.fills[0]
    assert fill.fees == Decimal("3.50") * abs(fill.quantity), "commission is 3.50 per lot"
    assert result.realised_pnl == -fill.fees
    assert fill.price % POINT == 0, "the fill must land on the 0.01 price grid"
    assert result.sizing_notes == (), "nothing in these runs should be capped or declined"
    assert result.unfilled_orders == ()

    lots_case = next(c for c in LOT_CASES if c.name == case.lots_case)
    if lots_case.expected is not None:
        assert fill.quantity == lots_case.expected, (
            f"the run's size differs from {lots_case.name}'s hand figure"
        )
    if case.expected_pnl is None:
        pytest.fail(
            f"No hand-computed figure for {case.name} yet. The structural assertions "
            "passed. The engine's own figure is deliberately NOT shown.",
            pytrace=False,
        )
    assert result.total_pnl == case.expected_pnl, (
        f"expected {case.expected_pnl}, engine reported {result.total_pnl}, "
        f"difference {result.total_pnl - case.expected_pnl}.{result.describe()}"
    )


# --- the fixture can catch each planned break -----------------------------------


def test_the_fixture_can_catch_each_sizer_bug() -> None:
    """Each break the operator's figures must catch changes at least one of
    them. Checked in code; every failure is a message only, never an amount."""

    def require(condition: bool, message: str) -> None:
        if not condition:
            pytest.fail(message, pytrace=False)

    bar = _deciding_bar()
    spec = _spec()
    risk = Fraction(load_sizing_config(SIZING).risk_fraction)
    step, low, high = (
        Fraction(spec.volume_step),
        Fraction(spec.volume_min),
        Fraction(spec.volume_max),
    )
    size = Fraction(spec.contract_size)

    def raw(case: LotCase, price) -> Fraction:
        if case.stop is None:
            return abs(Fraction(case.weight)) * Fraction(case.equity) / (size * Fraction(price))
        return risk * Fraction(case.equity) / (size * abs(Fraction(price) - Fraction(case.stop)))

    def down(x: Fraction, unit: Fraction = step) -> Fraction:
        return floor(x / unit) * unit

    def nearest(x: Fraction) -> Fraction:
        return round(x / step) * step  # exact: Fraction rounds half to even

    cases = {c.name: c for c in LOT_CASES}

    # L1-L4 must size inside the limits, or a run would trade nothing (or be capped).
    for name in ("L1", "L2", "L3", "L4"):
        r = down(raw(cases[name], bar.close))
        require(low <= r <= high, f"{name}: does not size inside the volume limits")

    # Rounding to nearest instead of down: moves the weight runs and both stops.
    for name in ("L1", "L3", "L4"):
        r = raw(cases[name], bar.close)
        require(down(r) != nearest(r), f"{name}: rounding down and to nearest agree")

    # Rounding to the minimum instead of the step: moves the weight runs and both stops.
    for name in ("L1", "L3", "L4"):
        r = raw(cases[name], bar.close)
        require(down(r) != down(r, low), f"{name}: rounding to the step and to the minimum agree")

    # The deciding bar's open instead of its close: moves both stop runs.
    for name in ("L3", "L4"):
        require(
            down(raw(cases[name], bar.close)) != down(raw(cases[name], bar.open)),
            f"{name}: the deciding bar's open and close give the same size",
        )

    # Both stops lie beyond every price the held position sees, so the run
    # never stops on them: long against the bid low, short against the ask high.
    bars = load_bars_from_csv(FIXTURE_DIR / FIXTURE, SYMBOL)
    model = _model()
    require(
        all(model.executable_price("sell", b, b.low) > LONG_STOP for b in bars[1:]),
        "the long stop is reached in the fixture",
    )
    require(
        all(model.executable_price("buy", b, b.high) < SHORT_STOP for b in bars[1:]),
        "the short stop is reached in the fixture",
    )

    # L5: on the step but below the minimum, and not zero -- so ignoring the
    # minimum would order something.
    r5 = down(raw(cases["L5"], bar.close))
    require(0 < r5 < low, "L5: does not land between zero and the minimum")

    # L6: above the maximum, so removing the cap moves it.
    require(down(raw(cases["L6"], bar.close)) > high, "L6: not above the maximum")

    # L7: equity and balance give different sizes.
    l7 = cases["L7"]
    with_balance = LotCase("L7b", l7.weight, None, None, equity=l7.balance)
    require(
        down(raw(l7, bar.close)) != down(raw(with_balance, bar.close)),
        "L7: equity and balance give the same size",
    )

    # L8: exactly on a step before rounding.
    require(raw(cases["L8"], bar.close) % step == 0, "L8: not exactly on a step")
