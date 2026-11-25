"""Phase 3 exit (3c.4): everything on, the production configuration, three
instruments in one run, against figures computed by hand before the
engine's are seen.

Decisions: operator, 2026-11-23 (docs/state.md, 3c.4).

WHAT IS LOADED
--------------
- Cost profile: config/cost_ftmo_demo.yaml, AS SHIPPED. Commission verified
  2026-11-24 (EURUSD 2.50 per lot per side; XAGUSD 0.0007% of notional per
  side; NAS100 0). Slippage 0.5 x the charged spread: still a placeholder.
- Instruments: config/instruments.yaml, as shipped.
  Both files are pinned by SHA-256 below: the hand figures were computed
  for these exact files, so a later edit (fresh swap readings, say) stops
  this test with that message rather than with a P&L mismatch.
- Spread correction: a REAL fitted table, cutoff 2025-01-01
  (spread_correction_ftmo_fit_until_2025-01-01.json, a byte copy of the file
  fit_spread_correction.py --fit-until 2025-01-01 wrote on 2026-11-25 at
  commit af2a154; its own provenance block names the inputs' SHA-256).
  Checked against the validated fit to end-2024 before use: every value of
  all five instruments identical, built from identical observations.
- Sizer: EquitySizer, weights only, the 3c.3 sizing file (its risk fraction
  is unused by weight targets).
- Strategy: ConstantWeights, weight +1 in each of the three (long basket)
  or -1 (short basket). Starting balance 100,000.00.

THE BARS (three fixtures, one per instrument, merged)
----------------------------------------------------
Real FTMO M15 bars, 2026-08-25 21:00 UTC to 2026-08-31 01:00 UTC
(exclusive). New York summer time, so the server is UTC+3 throughout.
The span starts at the daily break: EURUSD trades, XAGUSD and NAS100 do not
until 22:00. So EURUSD decides alone, fills at 21:15 and is marked at every
close before XAGUSD and NAS100 decide on their first bar.

    bar (UTC open)        open      close     stored spread
    EURUSD decides 21:00  1.16706   1.16718   0.00021
    EURUSD fills   21:15  1.16710   1.16709   0.00030
    EURUSD marked  22:00  1.16701   1.16745   0.00001  (its mark when the others decide)
    EURUSD last    31 Aug 00:45  1.15910  1.15921  0.00000  (a genuine zero)
    NAS100 decides 22:00  29231.94  29223.94  1.53
    NAS100 fills   22:15  29224.04  29220.54  1.53
    NAS100 last    31 Aug 00:45  29334.33  29301.83  1.75
    XAGUSD decides 22:00  68.837    68.827    0.060
    XAGUSD fills   22:15  68.832    68.886    0.059
    XAGUSD last    31 Aug 00:45  66.681  66.395  0.053

Rollovers at server midnight, 21:00 UTC, labelled by the server day ending:
Wed 26, Thu 27, Fri 28 charged; Sat 29 and Sun 30 free. Triple: Wednesday
for EURUSD and XAGUSD, Friday for NAS100.

SAME-TIMESTAMP PROCESSING ORDER: by time, then EURUSD, NAS100, XAGUSD
(alphabetical). At 22:00, EURUSD's bar is processed first, so NAS100 and
XAGUSD are sized from equity with EURUSD marked at 22:15. XAGUSD's order is
not filled when NAS100 is sized, and the other way round, so neither sees
the other.

HOW TO FILL IN A FIGURE
-----------------------
Replace each None in CASES with your own Decimal. Until every one is in,
each case fails with a message saying so; the structural assertions still
run. The engine's own figures are deliberately not shown.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal
from fractions import Fraction
from types import SimpleNamespace

import pytest
from harness import (
    FIXTURE_DIR,
    INSTRUMENTS_CONFIG,
    REPO_ROOT,
    load_bars_from_csv,
    merge_bars,
    run_backtest,
)

from engine.core.instruments import load_contract_sizes, load_instrument_specs
from engine.core.venue import load_venue_config
from engine.costs.configured import ConfiguredCostModel, build_server_clock
from engine.costs.correction_table import load_correction_table
from engine.costs.profile import load_cost_profile
from engine.costs.spread_correction import charge
from engine.sizing.equity import EquitySizer, load_sizing_config
from engine.strategies.reference.constant_weights import ConstantWeights

ORDER = ("EURUSD", "NAS100", "XAGUSD")  # same-timestamp processing order
SPAN = "2026-08-25T2100_2026-08-31T0100"
PROFILE = REPO_ROOT / "config" / "cost_ftmo_demo.yaml"
# The venue's position mode (PC.1): FTMO is hedging; read, not assumed.
VENUE_FILE = REPO_ROOT / "config" / "venue_ftmo_demo.yaml"
TABLE = FIXTURE_DIR / "spread_correction_ftmo_fit_until_2025-01-01.json"
SIZING = FIXTURE_DIR / "sizing_test.yaml"
STARTING_BALANCE = Decimal("100000.00")
WEIGHT = Decimal(1)

# The files the hand figures were computed for.
PINNED_SHA256 = {
    PROFILE: "3b4ea5708ddd657140b2b72d31b825bd13fd6357e2ffdf6ee2abcc800c8b10e5",
    INSTRUMENTS_CONFIG: "368249e215f71b21a73dd00c32adb98b00a66adf074dea73fc508ce121bb12b2",
    TABLE: "4e709df3d36333747b9b3a108946a3648268736747fd08fe41a8b5609290c6e4",
}

EURUSD_DECIDES = datetime(2026, 8, 25, 21, 0, tzinfo=UTC)
OTHERS_DECIDE = datetime(2026, 8, 25, 22, 0, tzinfo=UTC)
BAR = timedelta(minutes=15)


def _none() -> dict[str, Decimal | None]:
    return dict.fromkeys(ORDER)


@dataclass(frozen=True)
class Case:
    direction: str  # "long" | "short"
    lots: dict[str, Decimal | None] = field(default_factory=_none)  # signed
    pnl: dict[str, Decimal | None] = field(default_factory=_none)  # USD, per leg
    total: Decimal | None = None


# The operator's hand figures, computed before the engine's were seen
# (2026-11-25). For reference, the operator's equity at the NAS100/XAGUSD
# sizing: long 99944.325, short 99929.875.
CASES = [
    Case(
        direction="long",
        lots={"EURUSD": Decimal("0.85"), "NAS100": Decimal("3.41"), "XAGUSD": Decimal("0.29")},
        pnl={
            "EURUSD": Decimal("-793.475"),
            "NAS100": Decimal("137.151905"),
            "XAGUSD": Decimal("-3845.9551876"),
        },
        total=Decimal("-4502.2782826"),
    ),
    Case(
        direction="short",
        lots={
            "EURUSD": Decimal("-0.85"),
            "NAS100": Decimal("-3.41"),
            "XAGUSD": Decimal("-0.29"),
        },
        pnl={
            "EURUSD": Decimal("639.54"),
            "NAS100": Decimal("-273.2433"),
            "XAGUSD": Decimal("3320.30937285"),
        },
        total=Decimal("3686.60607285"),
    ),
]


def _profile():
    with pytest.warns(UserWarning, match="verification is incomplete"):
        return load_cost_profile(PROFILE)


def _specs():
    return load_instrument_specs(INSTRUMENTS_CONFIG)


def _model() -> ConfiguredCostModel:
    return ConfiguredCostModel(_profile(), _specs(), load_correction_table(TABLE))


def _series():
    return {
        symbol: load_bars_from_csv(FIXTURE_DIR / f"{symbol.lower()}_m15_{SPAN}.csv", symbol)
        for symbol in ORDER
    }


def _run(sign: int, sizer=None):
    return run_backtest(
        merge_bars(_series(), order=ORDER),
        ConstantWeights(dict.fromkeys(ORDER, sign * WEIGHT)),
        position_mode=load_venue_config(VENUE_FILE).position_mode,
        contract_sizes=load_contract_sizes(INSTRUMENTS_CONFIG),
        starting_balance=STARTING_BALANCE,
        cost_model=_model(),
        sizer=sizer or EquitySizer(load_sizing_config(SIZING)),
        instruments=_specs(),
    )


def test_the_configuration_is_the_one_the_figures_were_computed_for() -> None:
    for path, pinned in PINNED_SHA256.items():
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == pinned, (
            f"{path.name} has changed since the hand figures were computed (SHA-256 "
            f"{actual}, pinned {pinned}). The figures belong to the pinned file: "
            "recompute them for the new one, or restore it."
        )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.direction)
def test_the_basket_matches_the_hand_computed_figures(case: Case) -> None:
    sign = 1 if case.direction == "long" else -1
    result = _run(sign)
    side = "buy" if sign > 0 else "sell"

    # Structural assertions only -- none prints a price, a size or an amount.
    assert sorted(o.symbol for o in result.orders) == sorted(ORDER), "one order per symbol"
    assert all(o.side == side for o in result.orders)
    assert len(result.fills) == 3, f"expected three fills, got {len(result.fills)}"
    assert result.unfilled_orders == ()
    fill_at = {f.symbol: f.ts for f in result.fills}
    assert fill_at == {
        "EURUSD": EURUSD_DECIDES + BAR,
        "NAS100": OTHERS_DECIDE + BAR,
        "XAGUSD": OTHERS_DECIDE + BAR,
    }
    fees = {f.symbol: f.fees for f in result.fills}
    lots = {f.symbol: f.quantity for f in result.fills}
    assert fees["NAS100"] == 0, "NAS100 commission is 0"
    assert fees["EURUSD"] == abs(lots["EURUSD"]) * Decimal("2.50"), "EURUSD: 2.50 per lot"
    assert fees["XAGUSD"] > 0, "XAGUSD commission is a percentage of notional"
    assert {n.kind for n in result.sizing_notes} <= {"no_bar_yet"}, "no cap, no minimum"
    assert {n.symbol for n in result.sizing_notes} == {"NAS100", "XAGUSD"}
    # The last wait is on EURUSD's 22:00 bar (closing 22:15), processed
    # before NAS100's and XAGUSD's bars of the same instant.
    assert all(n.ts <= OTHERS_DECIDE + BAR for n in result.sizing_notes)
    assert set(result.pnl_by_symbol) == set(ORDER)
    assert sum(result.pnl_by_symbol.values()) == result.total_pnl
    assert result.financing_accrued != 0, "financing should have accrued"

    missing = [
        name
        for name, value in (
            *((f"lots {s}", v) for s, v in case.lots.items()),
            *((f"P&L {s}", v) for s, v in case.pnl.items()),
            ("total", case.total),
        )
        if value is None
    ]
    if missing:
        pytest.fail(
            f"No hand-computed figure yet for the {case.direction} basket: "
            f"{', '.join(missing)}. The phase 3 exit criterion has not been measured. "
            "The structural assertions passed. The engine's own figures are "
            "deliberately NOT shown."
        )

    report = result.describe()
    for symbol in ORDER:
        assert lots[symbol] == case.lots[symbol], (
            f"{symbol} lots: expected {case.lots[symbol]}, engine {lots[symbol]}{report}"
        )
    for symbol in ORDER:
        engine_leg = result.pnl_by_symbol[symbol]
        assert engine_leg == case.pnl[symbol], (
            f"{symbol} P&L: expected {case.pnl[symbol]}, engine {engine_leg}, "
            f"difference {engine_leg - case.pnl[symbol]}{report}"
        )
    assert result.total_pnl == case.total, (
        f"total: expected {case.total}, engine {result.total_pnl}{report}"
    )


# --- the fixture guard --------------------------------------------------------


class _FirstSizings:
    """EquitySizer, keeping what each symbol's FIRST sizing was given, so the
    guard can ask what a different input would have sized. Records only;
    sizes exactly as EquitySizer does."""

    def __init__(self) -> None:
        self._inner = EquitySizer(load_sizing_config(SIZING))
        self.notes = self._inner.notes
        self.first: dict = {}

    def size(self, target, portfolio, features, context):
        if context.committed == 0 and target.symbol not in self.first:
            self.first[target.symbol] = (target, portfolio.equity, portfolio.balance, context)
        return self._inner.size(target, portfolio, features, context)


def _resize(target, equity, context):
    sizer = EquitySizer(load_sizing_config(SIZING))
    return sizer.size(target, SimpleNamespace(equity=equity), {}, context)


def test_the_fixture_can_catch_each_planned_break() -> None:  # noqa: PLR0915 -- one guard
    """What makes this fixture worth using, checked in code with no amounts
    printed: each planned break must move a figure the operator computes."""

    def require(condition: bool, message: str) -> None:
        if not condition:
            pytest.fail(message, pytrace=False)

    profile = _profile()
    table = load_correction_table(TABLE)
    specs = _specs()
    clock = build_server_clock(profile.server_clock)
    series = _series()
    slip = {s: profile.instruments[s].slippage.value for s in ORDER}
    first = {s: series[s][0] for s in ORDER}
    fill = {s: series[s][1] for s in ORDER}
    last = {s: series[s][-1] for s in ORDER}

    def charged(bar, row: str | None = None) -> Decimal:
        """The charged spread with `row`'s table entry (default: the bar's own)."""
        point = specs[bar.symbol].point
        entry = table.instruments[row or bar.symbol]
        hour = clock.to_server_naive(bar.ts_open).hour
        exact = Fraction(charge(int(bar.spread / point), entry.value(hour), entry.form))
        return Decimal(-(-exact.numerator // exact.denominator)) * point

    def grid(price, symbol, rounding):
        point = specs[symbol].point
        return (price / point).to_integral_value(rounding=rounding) * point

    def buy(bar, spread, rounding=ROUND_CEILING):
        return grid(bar.open + spread + slip[bar.symbol] * spread, bar.symbol, rounding)

    def sell(bar, spread, rounding=ROUND_FLOOR):
        return grid(bar.open - slip[bar.symbol] * spread, bar.symbol, rounding)

    # The run's shape: EURUSD alone first; the other two together, after
    # EURUSD has filled and with an EURUSD bar at that instant (processed
    # first, so marked before they decide).
    require(first["EURUSD"].ts_open == EURUSD_DECIDES, "EURUSD does not decide first")
    require(
        first["NAS100"].ts_open == first["XAGUSD"].ts_open == OTHERS_DECIDE,
        "NAS100 and XAGUSD do not decide together at 22:00",
    )
    require(fill["EURUSD"].ts_close <= OTHERS_DECIDE, "EURUSD has not filled by then")
    require(
        any(b.ts_open == OTHERS_DECIDE for b in series["EURUSD"]),
        "no EURUSD bar at 22:00 to mark it before the others decide",
    )
    require(ORDER.index("EURUSD") == 0, "EURUSD is not processed first at a shared time")
    require(
        all(b.ts_open >= table.fit_until for s in ORDER for b in series[s]),
        "a bar opens before the table's cutoff",
    )
    require(
        all(b.spread > 0 for s in ("NAS100", "XAGUSD") for b in series[s]),
        "a NAS100 or XAGUSD zero spread (missing data: the fallback, uncorrected)",
    )

    # Breaks 3 (another instrument's contract size) and 4 (balance, not equity).
    for sign, name in ((1, "long"), (-1, "short")):
        recorder = _FirstSizings()
        _run(sign, sizer=recorder)
        require(set(recorder.first) == set(ORDER), f"{name}: a symbol was never sized")
        for symbol, (target, equity, _balance, context) in recorder.first.items():
            sized = _resize(target, equity, context)
            for other in ORDER:
                if other == symbol:
                    continue
                wrong = context.spec.model_copy(
                    update={"contract_size": specs[other].contract_size}
                )
                swapped = _resize(
                    target, equity, type(context)(context.bar, context.committed, wrong)
                )
                require(swapped != sized, f"{name}: {symbol} sized alike with {other}'s size")
        target, equity, balance, context = recorder.first["NAS100"]
        require(
            _resize(target, balance, context) != _resize(target, equity, context),
            f"{name}: NAS100 sizes alike from balance and from equity",
        )

    # Break 1: a correction row from another symbol. The long pays the fill
    # bar's charged spread; the short is valued with the last bar's.
    for symbol in ORDER:
        for other in ORDER:
            if other == symbol:
                continue
            require(
                buy(fill[symbol], charged(fill[symbol], other))
                != buy(fill[symbol], charged(fill[symbol])),
                f"long: {symbol}'s fill price is alike with {other}'s row",
            )
            require(
                charged(last[symbol], other) != charged(last[symbol]),
                f"short: {symbol}'s last-bar spread is alike with {other}'s row",
            )

    # Break 2: another instrument's swap settings (rates and triple day).
    # Every leg is held across a Wednesday- and a Friday-labelled rollover,
    # and the charge per lot differs under every other instrument's settings.
    def per_lot(symbol, settings_of, held_sign):
        rates = profile.financing.instruments[settings_of]
        spec = specs[symbol]
        rate = rates.long_rate if held_sign > 0 else rates.short_rate
        nights = 0
        for instant in clock.rollover_instants(fill[symbol].ts_open, last[symbol].ts_close):
            if instant <= fill[symbol].ts_open:
                continue
            day = clock.server_date_ending(instant).strftime("%A")
            if day not in ("Saturday", "Sunday"):
                nights += 3 if day == rates.triple_weekday else 1
        return nights * rate * spec.point * spec.contract_size

    for symbol in ORDER:
        days = {
            clock.server_date_ending(i).strftime("%A")
            for i in clock.rollover_instants(fill[symbol].ts_open, last[symbol].ts_close)
        }
        require({"Wednesday", "Friday"} <= days, f"{symbol} is not held over Wed and Fri")
        for other in ORDER:
            for held_sign, name in ((1, "long"), (-1, "short")):
                if other != symbol:
                    require(
                        per_lot(symbol, other, held_sign) != per_lot(symbol, symbol, held_sign),
                        f"{name}: {symbol}'s swap is alike with {other}'s settings",
                    )

    # Break 5: XAGUSD's percentage charge rounded to nearest instead of up.
    # Its exact charge must be fractional with a remainder under a half (so
    # nearest rounds down) at the fill bar (long) and the last bar (short).
    xag, xag_point = table.instruments["XAGUSD"], specs["XAGUSD"].point

    def exact_xag(bar) -> Fraction:
        hour = clock.to_server_naive(bar.ts_open).hour
        return Fraction(charge(int(bar.spread / xag_point), xag.value(hour), xag.form))

    def nearest_xag(bar) -> Decimal:
        return Decimal(round(exact_xag(bar))) * xag_point

    for bar, name in ((fill["XAGUSD"], "fill"), (last["XAGUSD"], "last")):
        exact = exact_xag(bar)
        remainder = exact - (exact.numerator // exact.denominator)
        require(0 < remainder < Fraction(1, 2), f"XAGUSD {name}: up and nearest agree")
    require(
        buy(fill["XAGUSD"], nearest_xag(fill["XAGUSD"]))
        != buy(fill["XAGUSD"], charged(fill["XAGUSD"])),
        "long: XAGUSD's fill price is alike rounded to nearest",
    )
    require(
        nearest_xag(last["XAGUSD"]) != charged(last["XAGUSD"]),
        "short: XAGUSD's last-bar spread is alike rounded to nearest",
    )

    # Break 6: EURUSD's genuine zero treated as missing (the fallback).
    # The short only: EURUSD's fill falls in the rollover hour, where its
    # ticks show no zeros, so the long cannot see this break.
    eurusd = profile.instruments["EURUSD"]
    require(last["EURUSD"].spread == 0, "EURUSD's last bar is not a zero spread")
    require(
        any(w.contains(last["EURUSD"].ts_open.date()) for w in eurusd.zero_spread_genuine),
        "EURUSD's last-bar zero is not declared genuine",
    )
    require(
        charged(last["EURUSD"]) != eurusd.fallback_spread,
        "short: EURUSD's corrected zero equals the fallback",
    )

    # Slippage rounding against the trader, not to nearest: at least one
    # fill per direction must tell them apart.
    require(
        any(
            buy(fill[s], charged(fill[s])) != buy(fill[s], charged(fill[s]), ROUND_HALF_EVEN)
            for s in ORDER
        ),
        "long: no fill tells slippage rounding from nearest",
    )
    require(
        any(
            sell(fill[s], charged(fill[s])) != sell(fill[s], charged(fill[s]), ROUND_HALF_EVEN)
            for s in ORDER
        ),
        "short: no fill tells slippage rounding from nearest",
    )
