"""The 3c.2 spread correction: the pure rules, with no file or network access.

Approved 2026-11-20 (docs/state.md, 3c.2, "Fit and out-of-sample validation").
The stored bar spread is the bar's MINIMUM tick spread (3c.0), which understates
what a trade faces. The correction measures, per instrument and server hour, how
far the spread in force at a bar boundary sits above that minimum, at a
pessimistic percentile, so that a backtest can charge more than the minimum.

Units throughout: times are whole microseconds since the epoch, spreads whole
points. Percentages are exact fractions. Nothing here uses floating point, so
the same inputs always give the same table, to the last digit.

Used by the cost model (applying a fitted table) and by the fitting tool
(fit_spread_correction.py, producing one). Moved into the package 2026-11-20.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal, TypeVar

PERCENTILE = 90
GAP_US = 5 * 60 * 1_000_000  # no tick in the 5 minutes before -> a gap
MIN_FIT_BARS = 200  # fewer fit bars in a cell -> use the instrument-wide value
CELL_FAIL_BELOW = Fraction(85, 100)
INSTRUMENT_MIN_COVERAGE = Fraction(88, 100)
INSTRUMENT_MIN_CELLS_PASSING = Fraction(90, 100)
OVER_PESSIMISTIC_ABOVE = Fraction(97, 100)
MIN_TEST_BARS = 100  # fewer test bars in a cell -> reported, not judged
MAX_UNJUDGED_CELLS = 2  # more unjudged cells than this -> the instrument is flagged
INTEGRITY_MAX_MISMATCH = Fraction(1, 100)  # of measured bars

Form = Literal["points", "percentage"]
FORMS: tuple[Form, ...] = ("points", "percentage")
T = TypeVar("T", int, Fraction)


def nearest_rank(values: Sequence[T], pct: int) -> T:
    """The `pct`th percentile by nearest rank: sort, then take the value at
    rank ceil(pct/100 * N), counting from 1. Always a value that was observed;
    never an interpolation between two."""
    if not 1 <= pct <= 100:  # noqa: PLR2004 -- the definition of a percentile
        raise ValueError(f"percentile must be 1-100, got {pct}")
    if not values:
        raise ValueError("no values to take a percentile of")
    rank = -(-pct * len(values) // 100)  # ceiling division, in whole numbers
    return sorted(values)[rank - 1]


def boundary_spread(
    times: Sequence[int], spreads: Sequence[int], boundary: int, gap: int
) -> tuple[int, bool] | None:
    """The spread in force at `boundary`, and whether the gap rule was used.

    Normally the last tick at or before the boundary. If there is no tick in
    [boundary - gap, boundary) -- the quote before is stale, as at a session
    open -- the first tick at or after the boundary instead. None if the gap
    rule finds nothing after. `times` must be sorted.
    """
    gap_start = bisect_left(times, boundary - gap)
    at_boundary = bisect_left(times, boundary)
    if at_boundary > gap_start:  # a tick within the gap window: no gap
        return spreads[bisect_right(times, boundary) - 1], False
    if at_boundary == len(times):
        return None
    return spreads[at_boundary], True


def bar_minimum(times: Sequence[int], spreads: Sequence[int], start: int, end: int) -> int | None:
    """The smallest tick spread in [start, end), or None if there are no ticks."""
    lo, hi = bisect_left(times, start), bisect_left(times, end)
    return min(spreads[lo:hi]) if hi > lo else None


def excess_points(boundary: int, minimum: int) -> int:
    return boundary - minimum


def excess_ratio(boundary: int, minimum: int) -> Fraction | None:
    """How far above the minimum, as a fraction of it. None for a zero minimum,
    which has no ratio."""
    return Fraction(boundary - minimum, minimum) if minimum else None


def charge(minimum: int, correction: int | Fraction, form: str) -> int | Fraction:
    """The charged spread, in points: max(minimum, minimum with the correction).
    A negative correction never charges below the stored minimum. Percentage
    charges stay exact fractions of a point."""
    lift = max(correction, 0)
    if form == "points":
        return minimum + lift
    if form == "percentage":
        return minimum * (1 + lift)
    raise ValueError(f"unknown correction form {form!r}")


def covered(boundary: int, minimum: int, correction: int | Fraction, form: str) -> bool:
    """Whether the charged spread is at least the boundary spread."""
    return boundary <= charge(minimum, correction, form)


def _excesses(observations: Sequence[tuple[int, int]], form: str) -> list:
    if form == "points":
        return [excess_points(b, m) for b, m in observations]
    if form == "percentage":
        ratios = (excess_ratio(b, m) for b, m in observations)
        return [r for r in ratios if r is not None]
    raise ValueError(f"unknown correction form {form!r}")


def fit_correction(observations: Sequence[tuple[int, int]], form: str) -> int | Fraction | None:
    """The PERCENTILE correction of (boundary, minimum) pairs, or None if the
    form has nothing to fit (every minimum zero, under percentage)."""
    excesses = _excesses(observations, form)
    return nearest_rank(excesses, PERCENTILE) if excesses else None


def fit_table(
    cells: Mapping[int, Sequence[tuple[int, int]]], bar_counts: Mapping[int, int], form: str
) -> tuple[dict[int, int | Fraction], set[int]]:
    """A correction per server hour, and the hours that fell back.

    A cell with fewer than MIN_FIT_BARS bars, or with nothing to fit, gets the
    instrument-wide correction -- the same percentile over every cell pooled.
    """
    pooled = [obs for hour in sorted(cells) for obs in cells[hour]]
    instrument_wide = fit_correction(pooled, form)
    if instrument_wide is None:
        raise ValueError(f"nothing to fit for the {form} form in any cell")
    table: dict[int, int | Fraction] = {}
    fallbacks: set[int] = set()
    for hour in sorted(cells):
        own = fit_correction(cells[hour], form) if bar_counts[hour] >= MIN_FIT_BARS else None
        if own is None:
            table[hour] = instrument_wide
            fallbacks.add(hour)
        else:
            table[hour] = own
    return table, fallbacks


def _share(n_covered: int, n: int) -> Fraction:
    if n == 0:
        raise ValueError("no observations to judge")
    return Fraction(n_covered, n)


def cell_fails(n_covered: int, n: int) -> bool:
    return _share(n_covered, n) < CELL_FAIL_BELOW


def over_pessimistic(n_covered: int, n: int) -> bool:
    return _share(n_covered, n) > OVER_PESSIMISTIC_ABOVE


def instrument_passes(cells_passed: int, cells_judged: int, n_covered: int, n: int) -> bool:
    """At least 90% of JUDGED cells pass -- fitted or fallback alike (operator
    decision 7) -- and coverage over every test observation is at least 88%."""
    if cells_judged == 0:
        raise ValueError("no judged cells: every cell is under the test-bar minimum")
    return (
        Fraction(cells_passed, cells_judged) >= INSTRUMENT_MIN_CELLS_PASSING
        and _share(n_covered, n) >= INSTRUMENT_MIN_COVERAGE
    )


def choose_form(
    points_pass: bool, percent_pass: bool, points_overcharge: Fraction, percent_overcharge: Fraction
) -> Form | None:
    """The form for an instrument: the only one that passes; if both, the one
    with the lower mean over-charge on the test period (points on a tie); if
    neither, None.

    Amended 2026-11-20, AFTER results (docs/state.md): it compared drift, the
    range of single-year coverage. The criteria guard only against undercharging,
    and coverage saturates near 100%, so a heavily overcharging form looked
    stable. Overcharging is not safe: it hides real edges.
    """
    if points_pass and percent_pass:
        return "percentage" if percent_overcharge < points_overcharge else "points"
    if points_pass:
        return "points"
    if percent_pass:
        return "percentage"
    return None


def score(
    observations: Mapping[int, Sequence[tuple[int, int]]],
    table: Mapping[int, int | Fraction],
    form: str,
) -> dict[int, tuple[int, int]]:
    """(covered, total) per hour. Every hour must have a correction in `table`;
    fit_table gives hours the fit never saw the fallback."""
    return {
        hour: (sum(covered(b, m, table[hour], form) for b, m in obs), len(obs))
        for hour, obs in sorted(observations.items())
    }


@dataclass(frozen=True)
class Verdict:
    passes: bool
    judged: list[int]
    failed: list[int]
    unjudged: list[int]
    over_pessimistic: list[int]
    fallback_judged: list[int]
    overall: tuple[int, int]
    too_many_unjudged: bool


def judge(
    scores: Mapping[int, tuple[int, int]], test_bars: Mapping[int, int], fallbacks: set[int]
) -> Verdict:
    """The pre-registered criteria, applied to one instrument's table.

    Cells with fewer than MIN_TEST_BARS test bars are unjudged; every other
    cell is judged, fallback or not. Overall coverage counts every observation.
    """
    hours = sorted(scores)
    judged = [h for h in hours if test_bars[h] >= MIN_TEST_BARS]
    unjudged = [h for h in hours if test_bars[h] < MIN_TEST_BARS]
    failed = [h for h in judged if cell_fails(*scores[h])]
    overall = (sum(c for c, _ in scores.values()), sum(n for _, n in scores.values()))
    return Verdict(
        passes=instrument_passes(len(judged) - len(failed), len(judged), *overall),
        judged=judged,
        failed=failed,
        unjudged=unjudged,
        over_pessimistic=[h for h in judged if over_pessimistic(*scores[h])],
        fallback_judged=[h for h in judged if h in fallbacks],
        overall=overall,
        too_many_unjudged=len(unjudged) > MAX_UNJUDGED_CELLS,
    )


def integrity_ok(mismatches: int, measured: int) -> bool:
    """Definition 5: stop if more than 1% of bars WITH ticks disagree with
    their tick minimum. Bars without ticks are unmeasurable, not counted here."""
    return Fraction(mismatches, measured) <= INTEGRITY_MAX_MISMATCH


def prefer_hourly(hourly_failed: int, constant_failed: int) -> bool:
    """The per-hour table earns its place only with strictly fewer failing cells."""
    return hourly_failed < constant_failed


def coverage_range(scores: Sequence[tuple[int, int]]) -> Fraction:
    """Best minus worst overall coverage across the single-year fits."""
    if len(scores) < 2:  # noqa: PLR2004 -- a range needs two
        raise ValueError("a range needs at least two years")
    shares = [Fraction(c, n) for c, n in scores]
    return max(shares) - min(shares)


def mean_overcharge(
    observations: Mapping[int, Sequence[tuple[int, int]]],
    table: Mapping[int, int | Fraction],
    form: str,
) -> Fraction:
    """Mean of (charged - actual spread), in points, over every observation in
    every hour. Undercharges count negative. Exact: no rounding."""
    total, n = Fraction(0), 0
    for hour, obs in observations.items():
        for b, m in obs:
            total += Fraction(charge(m, table[hour], form)) - b
            n += 1
    if n == 0:
        raise ValueError("no observations to average")
    return total / n


def charged_points(minimum: int, correction: int | Fraction, form: str) -> int:
    """The charged spread in WHOLE points: the exact charge, rounded UP --
    against the trader -- when a percentage makes it fractional."""
    exact = Fraction(charge(minimum, correction, form))
    return -(-exact.numerator // exact.denominator)  # ceiling, in whole numbers


HOURS = range(24)


def fit_entry(
    cells: Mapping[int, Sequence[tuple[int, int]]],
    bar_counts: Mapping[int, int],
    form: str,
    structure: str,
) -> tuple[dict[int, int | Fraction], set[int]]:
    """A correction for EVERY server hour 0-23, and the hours that fell back.

    `per_hour`: fit_table over all 24 hours; an hour with no data or too few
    bars takes the instrument-wide value. `constant`: the instrument-wide value
    everywhere, with no fallbacks (none is needed).
    """
    if structure == "per_hour":
        return fit_table(
            {h: cells.get(h, []) for h in HOURS}, {h: bar_counts.get(h, 0) for h in HOURS}, form
        )
    if structure == "constant":
        pooled = [obs for hour in sorted(cells) for obs in cells[hour]]
        value = fit_correction(pooled, form)
        if value is None:
            raise ValueError(f"nothing to fit for the {form} form")
        return dict.fromkeys(HOURS, value), set()
    raise ValueError(f"unknown correction structure {structure!r}")
