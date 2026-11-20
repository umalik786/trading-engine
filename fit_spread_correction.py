"""
3c.2 spread correction -- joins the monthly tick sample to the M15 bars.

READ ONLY on market data. Reads C:/trading/data/raw/<INSTRUMENT>/ticks_monthly/
and .../M15/; writes only under C:/trading/runtime/spread_correction/.

WHAT IT BUILDS. For every M15 bar inside a sampled week, two observations,
both against the bar's stored spread (its minimum tick spread, 3c.0): the
spread in force at the bar's OPEN (where a fill is charged) and at its CLOSE
(where a position is valued). The rules -- last tick at or before the boundary,
or the first at or after it when the 5 minutes before held no tick -- are in
spread_correction.py and its tests. Each observation is labelled with the
server hour of its bar's start (+2/+3, US calendar) and with its split: FIT
(bars before 2025-01-01 UTC) or TEST (from then on).

DATA INTEGRITY. Each bar's stored spread is compared with the minimum tick
spread in [open, open + 15 min). It also checks the bar and tick clocks
agree: a bar matched to the wrong hour of ticks would disagree.

TWO MODES.
  --handcheck  writes the operator's hand-check files for one cell (XAUUSD,
               server hour 14) WITHOUT computing that cell's percentile or
               coverage, so the hand figures come first.
  (default)    the fit and the out-of-sample validation, all five instruments,
               under the criteria fixed before any result (docs/state.md, 3c.2).
               Writes the report and a JSON record with provenance.

This run VALIDATES THE METHOD. It does not produce the tables backtests use:
those are re-fitted on data before each backtest's start only.

Run with:  uv run python fit_spread_correction.py [--handcheck]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from itertools import pairwise
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import yaml

from engine.core.clock import DstSwitchedServerClock
from spread_correction import (
    FORMS,
    GAP_US,
    MIN_FIT_BARS,
    MIN_TEST_BARS,
    PERCENTILE,
    Verdict,
    bar_minimum,
    boundary_spread,
    charge,
    choose_form,
    coverage_range,
    covered,
    fit_correction,
    fit_table,
    integrity_ok,
    judge,
    prefer_hourly,
    score,
)

DATA = Path("C:/trading/data/raw")
OUT = Path("C:/trading/runtime/spread_correction")
INSTRUMENTS_YAML = Path(__file__).resolve().parent / "config" / "instruments.yaml"
SERVER_CLOCK = DstSwitchedServerClock(timedelta(hours=2), timedelta(hours=3), "America/New_York")
TEST_FROM = datetime(2025, 1, 1, tzinfo=UTC)
BAR = timedelta(minutes=15)
_SUNDAY = 6  # date.weekday(): Monday 0 ... Sunday 6

HANDCHECK_INSTRUMENT, HANDCHECK_HOUR = "XAUUSD", 14
# The operator's hand figures for that cell, worked before the fit ran (2026-11-20).
OPERATOR_V, OPERATOR_COVERED, HANDCHECK_BOUNDARIES = 14, 12, 12
_DAYS_SHOWN = 12


@dataclass(frozen=True)
class Observation:
    bar_open: datetime
    server_hour: int
    split: str  # "fit" or "test"
    kind: str  # "open" or "close"
    boundary: int  # spread in force, points
    minimum: int  # the bar's stored spread, points
    gap_rule: bool


@dataclass
class WeekTicks:
    times: list[int]
    spreads: list[int]
    bids: list[Decimal]
    asks: list[Decimal]


def to_us(t: datetime) -> int:
    return (t - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(microseconds=1)


def point_digits(instrument: str) -> int:
    spec = yaml.safe_load(INSTRUMENTS_YAML.read_text(encoding="utf-8"))
    point = Decimal(spec["instruments"][instrument]["point"])
    return -point.as_tuple().exponent


def sampled_weeks(instrument: str) -> list[tuple[datetime, datetime]]:
    path = DATA / instrument / "ticks_monthly" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return [
        (datetime.fromisoformat(w["start_utc"]), datetime.fromisoformat(w["end_utc"]))
        for w in manifest["weeks"]
    ]


def load_week_ticks(
    instrument: str, start: datetime, end: datetime, digits: int, with_prices: bool
) -> WeekTicks:
    """Every tick of the week, in time order, with its spread in whole points.
    The cast to whole points is checked: a spread that is not an exact number
    of points raises rather than being rounded. Bid and ask are kept only if
    asked for (the hand-check export prints them; the fit does not need them)."""
    tables = []
    day = start
    while day < end:
        path = DATA / instrument / "ticks_monthly" / f"{day.date().isoformat()}.parquet"
        if path.exists():
            tables.append(pq.read_table(path, columns=["time", "bid", "ask"]))
        day += timedelta(days=1)
    if not tables:
        return WeekTicks([], [], [], [])
    t = pa.concat_tables(tables)
    scaled = pc.multiply(pc.subtract(t["ask"], t["bid"]), pa.scalar(Decimal(10**digits)))
    spreads = pc.cast(scaled, pa.int64()).to_pylist()  # safe cast: exact or error
    times = pc.cast(t["time"], pa.int64()).to_pylist()  # microseconds since epoch
    if any(b < a for a, b in pairwise(times)):
        raise ValueError(f"{instrument} ticks out of order in week {start:%Y-%m-%d}")
    if not with_prices:
        return WeekTicks(times, spreads, [], [])
    return WeekTicks(times, spreads, t["bid"].to_pylist(), t["ask"].to_pylist())


_bar_years: dict[tuple[str, int], list[dict]] = {}


def load_week_bars(instrument: str, start: datetime, end: datetime) -> list[tuple[datetime, int]]:
    years = sorted({start.year, (end - timedelta(microseconds=1)).year})
    bars = []
    for year in years:
        if (instrument, year) not in _bar_years:
            path = DATA / instrument / "M15" / f"{year}.parquet"
            _bar_years[instrument, year] = pq.read_table(
                path, columns=["time", "spread"]
            ).to_pylist()
        bars += [
            (row["time"], row["spread"])
            for row in _bar_years[instrument, year]
            if start <= row["time"] < end
        ]
    return bars


def server_hour(utc: datetime) -> int:
    return (utc + SERVER_CLOCK.utc_offset(utc)).hour


@dataclass
class InstrumentData:
    observations: list[Observation]
    bars: int  # every bar inside a sampled week
    bars_without_ticks: int  # excluded: nothing to measure (before the history, or a hole)
    dropped: list[tuple[datetime, str]]  # (bar, boundary): gap rule found no later tick
    minimum_mismatches: list[tuple[datetime, int, int | None]]  # (bar, stored, from ticks)


def build(
    instrument: str, keep_ticks: bool = False
) -> tuple[InstrumentData, dict[datetime, WeekTicks]]:
    digits = point_digits(instrument)
    observations: list[Observation] = []
    mismatches: list[tuple[datetime, int, int | None]] = []
    n_bars = without_ticks = 0
    dropped: list[tuple[datetime, str]] = []
    week_ticks: dict[datetime, WeekTicks] = {}
    for start, end in sampled_weeks(instrument):
        ticks = load_week_ticks(instrument, start, end, digits, with_prices=keep_ticks)
        if keep_ticks:
            week_ticks[start] = ticks
        for bar_open, stored in load_week_bars(instrument, start, end):
            n_bars += 1
            open_us = to_us(bar_open)
            from_ticks = bar_minimum(
                ticks.times, ticks.spreads, open_us, open_us + to_us_delta(BAR)
            )
            if from_ticks is None:
                without_ticks += 1
                continue
            if from_ticks != stored:
                mismatches.append((bar_open, stored, from_ticks))
            split = "test" if bar_open >= TEST_FROM else "fit"
            hour = server_hour(bar_open)
            for kind, boundary in (("open", open_us), ("close", open_us + to_us_delta(BAR))):
                found = boundary_spread(ticks.times, ticks.spreads, boundary, GAP_US)
                if found is None:
                    dropped.append((bar_open, kind))
                    continue
                spread, gap = found
                observations.append(Observation(bar_open, hour, split, kind, spread, stored, gap))
    data = InstrumentData(observations, n_bars, without_ticks, dropped, mismatches)
    return data, week_ticks


def to_us_delta(d: timedelta) -> int:
    return d // timedelta(microseconds=1)


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _ticks_between(ticks: WeekTicks, lo: datetime, hi: datetime, digits: int) -> list[list[object]]:
    a, b = bisect_left(ticks.times, to_us(lo)), bisect_left(ticks.times, to_us(hi))
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    return [
        [
            (epoch + timedelta(microseconds=ticks.times[i])).isoformat(timespec="milliseconds"),
            f"{ticks.bids[i]:.{digits}f}",
            f"{ticks.asks[i]:.{digits}f}",
            ticks.spreads[i],
        ]
        for i in range(a, b)
    ]


def _ticks_around(ticks: WeekTicks, boundary: int, k: int, digits: int) -> list[list[object]]:
    """The k ticks before `boundary` and the k at or after it."""
    i = bisect_left(ticks.times, boundary)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    return [
        [
            (epoch + timedelta(microseconds=ticks.times[j])).isoformat(timespec="milliseconds"),
            f"{ticks.bids[j]:.{digits}f}",
            f"{ticks.asks[j]:.{digits}f}",
            ticks.spreads[j],
        ]
        for j in range(max(i - k, 0), min(i + k, len(ticks.times)))
    ]


def handcheck_picks(cell_test: list[Observation]) -> list[datetime]:
    """The six test bars of the hand-check cell, evenly spread through the test
    period. Shared by the export and the full run, so both use the same bars."""
    test_bars = sorted({o.bar_open for o in cell_test})
    return [test_bars[round(k * (len(test_bars) - 1) / 5)] for k in range(6)]


def handcheck() -> int:
    inst, hour = HANDCHECK_INSTRUMENT, HANDCHECK_HOUR
    digits = point_digits(inst)
    data, week_ticks = build(inst, keep_ticks=True)
    out = OUT / "handcheck"
    out.mkdir(parents=True, exist_ok=True)

    measured = data.bars - data.bars_without_ticks
    n_mis = len(data.minimum_mismatches)
    print(f"{inst}: {data.bars:,} M15 bars in the sampled weeks")
    print(f"  {data.bars_without_ticks:,} excluded: no ticks inside the bar")
    print(f"  {measured:,} measured -> {len(data.observations):,} observations")
    print(
        f"  stored spread = minimum tick spread on {measured - n_mis:,} bars; "
        f"{n_mis} disagree ({n_mis / measured:.3%} of measured bars)"
    )
    print(f"  {len(data.dropped)} observations dropped (gap rule, nothing after)")
    for bar, stored, ticks_min in data.minimum_mismatches[:5]:
        print(f"    disagree: {bar:%Y-%m-%d %H:%M} UTC  stored {stored}  ticks {ticks_min}")

    cell_fit = [o for o in data.observations if o.server_hour == hour and o.split == "fit"]
    cell_test = [o for o in data.observations if o.server_hour == hour and o.split == "test"]
    fit_bars = len({o.bar_open for o in cell_fit})

    # 1. The fit cell's excesses, sorted, with where each came from.
    ranked = sorted(cell_fit, key=lambda o: (o.boundary - o.minimum, o.bar_open, o.kind))
    _write_csv(
        out / "1_fit_excess_sorted.csv",
        [
            "rank",
            "excess_points",
            "bar_open_utc",
            "boundary",
            "boundary_spread",
            "bar_minimum",
            "gap_rule",
        ],
        [
            [
                i,
                o.boundary - o.minimum,
                o.bar_open.isoformat(),
                o.kind,
                o.boundary,
                o.minimum,
                o.gap_rule,
            ]
            for i, o in enumerate(ranked, start=1)
        ],
    )

    # 2. Six test bars of the cell, spread evenly through the test period.
    picks = handcheck_picks(cell_test)
    by_bar = {(o.bar_open, o.kind): o for o in cell_test}
    _write_csv(
        out / "2_test_bars.csv",
        [
            "bar_open_utc",
            "server_time",
            "bar_minimum",
            "open_boundary_spread",
            "open_gap_rule",
            "close_boundary_spread",
            "close_gap_rule",
        ],
        [
            [
                b.isoformat(),
                (b + SERVER_CLOCK.utc_offset(b)).strftime("%Y-%m-%d %H:%M"),
                by_bar[b, "open"].minimum,
                by_bar[b, "open"].boundary,
                by_bar[b, "open"].gap_rule,
                by_bar[b, "close"].boundary,
                by_bar[b, "close"].gap_rule,
            ]
            for b in picks
        ],
    )

    # 3. Raw ticks for the first picked bar: a minute before its open to a
    #    minute after its close -- enough to check both boundaries and its minimum.
    def week_of(b: datetime) -> WeekTicks:
        return next(t for s, t in week_ticks.items() if s <= b < s + timedelta(days=7))

    first = picks[0]
    _write_csv(
        out / "3_ticks_first_test_bar.csv",
        ["time_utc", "bid", "ask", "spread_points"],
        _ticks_between(
            week_of(first), first - timedelta(minutes=1), first + BAR + timedelta(minutes=1), digits
        ),
    )

    # 4. A gap-rule example: the first fit bar, not on a Sunday, whose open used
    #    the rule -- a daily break, so there is a stale quote before it to see.
    gap = next(
        o
        for o in data.observations
        if o.kind == "open" and o.gap_rule and o.split == "fit" and o.bar_open.weekday() != _SUNDAY
    )
    _write_csv(
        out / "4_gap_rule_example_ticks.csv",
        ["time_utc", "bid", "ask", "spread_points"],
        _ticks_around(week_of(gap.bar_open), to_us(gap.bar_open), 5, digits),
    )

    gaps_in_cell = sum(o.gap_rule for o in cell_fit)
    print(f"\nHand-check cell {inst} server hour {hour:02d}, FIT period:")
    print(f"  {fit_bars} bars, N = {len(cell_fit)} observations ({gaps_in_cell} used the gap rule)")
    print(
        f"Gap-rule example: bar {gap.bar_open:%Y-%m-%d %H:%M} UTC (server hour "
        f"{gap.server_hour:02d}), open boundary spread {gap.boundary}, bar minimum {gap.minimum}"
    )
    print(f"\nWritten to {out}:")
    for p in sorted(out.glob("*.csv")):
        print(f"  {p.name}  ({sum(1 for _ in p.open(encoding='utf-8')) - 1} rows)")
    return 0


# --- the fit and the out-of-sample validation ---------------------------------

INSTRUMENTS = ("NAS100", "US500", "EURUSD", "XAUUSD", "XAGUSD")
# Definition 3: only full sampled years count towards drift. Others' 2021 is shown.
FULL_YEARS = {"EURUSD": (2020, 2021, 2022, 2023, 2024)}
DEFAULT_FULL_YEARS = (2022, 2023, 2024)
SHOWN_ONLY_YEARS = {"EURUSD": ()}
DEFAULT_SHOWN_ONLY_YEARS = (2021,)


def pct(c: int | Fraction, n: int = 1) -> str:
    """A share as a percentage to two places, via Decimal: no float anywhere."""
    share = Fraction(c) / n
    return f"{Decimal(share.numerator) * 100 / Decimal(share.denominator):.2f}%"


def show_correction(c: int | Fraction, form: str) -> str:
    return f"{c:+d} pts" if form == "points" else f"{pct(c)}"


def points2(x: Fraction) -> str:
    return f"{Decimal(x.numerator) / Decimal(x.denominator):.2f}"


def _by_hour(obs: list[Observation]) -> dict[int, list[tuple[int, int]]]:
    cells: dict[int, list[tuple[int, int]]] = {}
    for o in obs:
        cells.setdefault(o.server_hour, []).append((o.boundary, o.minimum))
    return cells


def _bars_by_hour(obs: list[Observation]) -> dict[int, int]:
    bars: dict[int, set[datetime]] = {}
    for o in obs:
        bars.setdefault(o.server_hour, set()).add(o.bar_open)
    return {h: len(b) for h, b in bars.items()}


def _fit_and_score(
    fit_obs: list[Observation], test_cells: dict, hours: list[int], form: str
) -> tuple[dict, set[int], dict]:
    """Fit a per-hour table on `fit_obs` (every hour in `hours` present, empty if
    unseen, so it falls back) and score it on the test cells."""
    fit_cells = _by_hour(fit_obs)
    fit_bars = _bars_by_hour(fit_obs)
    table, fallbacks = fit_table(
        {h: fit_cells.get(h, []) for h in hours}, {h: fit_bars.get(h, 0) for h in hours}, form
    )
    return table, fallbacks, score(test_cells, table, form)


def _verdict_or_none(scores: dict, test_bars: dict, fallbacks: set[int]) -> Verdict | None:
    try:
        return judge(scores, test_bars, fallbacks)
    except ValueError:  # no judged cells at all
        return None


def evaluate(inst: str, data: InstrumentData, out: list[str]) -> dict:  # noqa: PLR0915 -- one report
    """Everything the pre-registered criteria ask for, for one instrument.
    Appends report lines to `out`; returns the JSON record."""
    say = out.append
    measured = data.bars - data.bars_without_ticks
    n_mis = len(data.minimum_mismatches)
    record: dict = {
        "bars_in_sampled_weeks": data.bars,
        "bars_without_ticks": data.bars_without_ticks,
        "bars_measured": measured,
        "minimum_mismatches": n_mis,
        "observations_dropped": len(data.dropped),
    }
    say(f"\n{'=' * 78}\n{inst}\n{'=' * 78}")
    say(
        f"Bars in sampled weeks {data.bars:,}; no ticks inside (unmeasurable) "
        f"{data.bars_without_ticks:,}; measured {measured:,}"
    )
    say(
        f"Data check: {n_mis} of {measured:,} measured bars disagree with their tick "
        f"minimum ({pct(n_mis, measured)})"
    )
    if not integrity_ok(n_mis, measured):
        say("  STOPPED: more than 1% disagree (definition 5). Not fitted.")
        record["stopped"] = True
        return record
    record["stopped"] = False
    dropped_days = sorted({b.date().isoformat() for b, _ in data.dropped})
    say(
        f"Observations dropped (gap rule, no later tick in the week): {len(data.dropped)}"
        + (
            f", on {len(dropped_days)} days: {', '.join(dropped_days[:_DAYS_SHOWN])}"
            + (" ..." if len(dropped_days) > _DAYS_SHOWN else "")
            if data.dropped
            else ""
        )
    )

    fit_obs = [o for o in data.observations if o.split == "fit"]
    test_obs = [o for o in data.observations if o.split == "test"]
    hours = sorted({o.server_hour for o in data.observations})
    test_cells = _by_hour(test_obs)
    test_bars = _bars_by_hour(test_obs)
    fit_bars = _bars_by_hour(fit_obs)
    gaps_fit = {h: sum(o.gap_rule for o in fit_obs if o.server_hour == h) for h in hours}
    gaps_test = {h: sum(o.gap_rule for o in test_obs if o.server_hour == h) for h in hours}
    say(
        f"Fit: {len({o.bar_open for o in fit_obs}):,} bars, {len(fit_obs):,} observations. "
        f"Test: {len({o.bar_open for o in test_obs}):,} bars, {len(test_obs):,} observations."
    )

    # Baseline: no correction -- today's model, the bar minimum alone.
    none_table = dict.fromkeys(test_cells, 0)
    none_scores = score(test_cells, none_table, "points")
    none_v = _verdict_or_none(none_scores, test_bars, set())
    record["baseline_no_correction"] = _verdict_json(none_v)
    say(
        f"\nBaseline, NO correction (bar minimum alone): overall "
        f"{pct(*none_v.overall) if none_v else 'n/a'}, "
        f"{len(none_v.failed) if none_v else '?'} of {len(none_v.judged) if none_v else '?'} "
        f"judged cells fail -> {'PASS' if none_v and none_v.passes else 'FAIL'}"
    )

    forms: dict[str, dict] = {}
    for form in FORMS:
        table, fallbacks, scores = _fit_and_score(fit_obs, test_cells, hours, form)
        v = _verdict_or_none(scores, test_bars, fallbacks)
        constant = fit_correction([(o.boundary, o.minimum) for o in fit_obs], form)
        c_table = dict.fromkeys(test_cells, constant)
        c_v = _verdict_or_none(score(test_cells, c_table, form), test_bars, set())

        say(f"\n--- {form.upper()} form ---")
        say(
            f"{'hour':>4} {'fit bars':>8} {'correction':>12} {'test bars':>9} {'obs':>5} "
            f"{'coverage':>9}  {'verdict':<9} gap-rule fit/test  notes"
        )
        cells_json = {}
        for h in hours:
            if h not in scores:
                say(
                    f"{h:>4} {fit_bars.get(h, 0):>8} {show_correction(table[h], form):>12} "
                    f"{'0':>9}     -          -  {'':<9} {gaps_fit[h]:>5}/{gaps_test[h]:<5}  "
                    "no test observations"
                )
                continue
            c, n = scores[h]
            judged = test_bars[h] >= MIN_TEST_BARS
            verdict = "unjudged" if not judged else "FAIL" if v and h in v.failed else "PASS"
            notes = []
            if h in fallbacks:
                notes.append("FALLBACK (instrument-wide)")
            if v and h in v.over_pessimistic:
                over = (
                    sum(
                        (Fraction(charge(m, table[h], form)) - b for b, m in test_cells[h]),
                        Fraction(0),
                    )
                    / n
                )
                notes.append(f"over-pessimistic, mean over-charge {points2(over)} pts")
            say(
                f"{h:>4} {fit_bars.get(h, 0):>8} {show_correction(table[h], form):>12} "
                f"{test_bars[h]:>9} {n:>5} {pct(c, n):>9}  {verdict:<9} "
                f"{gaps_fit[h]:>5}/{gaps_test[h]:<5}  {'; '.join(notes)}"
            )
            cells_json[h] = {
                "fit_bars": fit_bars.get(h, 0),
                "correction": str(table[h]),
                "fallback": h in fallbacks,
                "test_bars": test_bars[h],
                "covered": c,
                "observations": n,
                "verdict": verdict,
                "gap_rule_fit": gaps_fit[h],
                "gap_rule_test": gaps_test[h],
            }

        # Drift: a table fitted on each single year, scored on the same test period.
        years = FULL_YEARS.get(inst, DEFAULT_FULL_YEARS)
        shown = SHOWN_ONLY_YEARS.get(inst, DEFAULT_SHOWN_ONLY_YEARS)
        year_overall: dict[int, tuple[int, int]] = {}
        for y in (*shown, *years):
            y_obs = [o for o in fit_obs if o.bar_open.year == y]
            try:
                _, _, y_scores = _fit_and_score(y_obs, test_cells, hours, form)
            except ValueError:
                continue
            year_overall[y] = (
                sum(c for c, _ in y_scores.values()),
                sum(n for _, n in y_scores.values()),
            )
        counted = [year_overall[y] for y in years if y in year_overall]
        drift = coverage_range(counted) if len(counted) >= 2 else None  # noqa: PLR2004

        if v is None:
            say("Verdict: CANNOT JUDGE -- no cell has 100 test bars")
        else:
            fb_list = ", ".join(f"{h:02d}" for h in v.fallback_judged)
            say(
                f"Judged cells {len(v.judged)} (of which fallback {len(v.fallback_judged)}"
                f"{': ' + fb_list if fb_list else ''}); "
                f"failed {len(v.failed)}"
                f"{': ' + ', '.join(f'{h:02d}' for h in v.failed) if v.failed else ''}; "
                f"unjudged {len(v.unjudged)}"
                f"{' -- FLAG: more than two unjudged' if v.too_many_unjudged else ''}"
            )
            say(
                f"Overall test coverage (every observation) {pct(*v.overall)}; "
                f"cells passing {len(v.judged) - len(v.failed)}/{len(v.judged)}"
            )
            say(f"VERDICT, per-hour table: {'PASS' if v.passes else 'FAIL'}")
        say(
            f"Constant baseline ({show_correction(constant, form)} every hour): overall "
            f"{pct(*c_v.overall) if c_v else 'n/a'}, failing cells "
            f"{len(c_v.failed) if c_v else '?'} -> {'PASS' if c_v and c_v.passes else 'FAIL'}"
        )
        hourly_earns = bool(v and c_v and prefer_hourly(len(v.failed), len(c_v.failed)))
        say(
            f"Hour structure earns its place (strictly fewer failing cells than constant): "
            f"{'YES' if hourly_earns else 'NO -- the simpler model is preferred'}"
        )
        say(
            "Single-year fits, overall test coverage: "
            + ", ".join(
                f"{y}{'*' if y in shown else ''} {pct(*year_overall[y])}"
                for y in sorted(year_overall)
            )
            + (
                f"  -> drift (full years) {pct(drift)}"
                if drift is not None
                else "  -> drift: fewer than two full years"
            )
        )
        if shown:
            say("  (* shown, not counted: not a full sampled year)")
        forms[form] = {
            "verdict": _verdict_json(v),
            "cells": cells_json,
            "constant_correction": str(constant),
            "constant_verdict": _verdict_json(c_v),
            "hourly_earns_its_place": hourly_earns,
            "single_year_overall": {y: list(year_overall[y]) for y in sorted(year_overall)},
            "drift_full_years": str(drift) if drift is not None else None,
            "table": {h: str(table[h]) for h in hours},
        }

    p_v, q_v = forms["points"]["verdict"], forms["percentage"]["verdict"]
    p_d = Fraction(forms["points"]["drift_full_years"] or 0)
    q_d = Fraction(forms["percentage"]["drift_full_years"] or 0)
    chosen = choose_form(bool(p_v and p_v["passes"]), bool(q_v and q_v["passes"]), p_d, q_d)
    say(f"\nFORM CHOSEN (definition 4): {chosen or 'NONE -- the instrument fails'}")
    record["forms"] = forms
    record["form_chosen"] = chosen
    return record


def _verdict_json(v: Verdict | None) -> dict | None:
    if v is None:
        return None
    return {
        "passes": v.passes,
        "judged": v.judged,
        "failed": v.failed,
        "unjudged": v.unjudged,
        "over_pessimistic": v.over_pessimistic,
        "fallback_judged": v.fallback_judged,
        "overall": list(v.overall),
        "too_many_unjudged": v.too_many_unjudged,
    }


def handcheck_comparison(data: InstrumentData, out: list[str]) -> dict:
    """The script's figures for the operator's hand-check cell."""
    hour = HANDCHECK_HOUR
    fit_obs = [o for o in data.observations if o.split == "fit"]
    hours = sorted({o.server_hour for o in data.observations})
    fit_cells, fit_bars = _by_hour(fit_obs), _bars_by_hour(fit_obs)
    table, fallbacks = fit_table(
        {h: fit_cells.get(h, []) for h in hours},
        {h: fit_bars.get(h, 0) for h in hours},
        "points",
    )
    cell_test = [o for o in data.observations if o.server_hour == hour and o.split == "test"]
    picks = set(handcheck_picks(cell_test))
    chosen = [o for o in cell_test if o.bar_open in picks]
    n_cov = sum(covered(o.boundary, o.minimum, table[hour], "points") for o in chosen)
    v = table[hour]
    out.append(f"\nHAND-CHECK COMPARISON, {HANDCHECK_INSTRUMENT} server hour {hour:02d}:")
    out.append(
        f"  N = {len(fit_cells[hour])}; script's correction V = {v:+d} points"
        f"{' (FALLBACK)' if hour in fallbacks else ''}; operator's V = {OPERATOR_V:+d}"
    )
    out.append(
        f"  six test bars: {n_cov} of {len(chosen)} boundaries covered; "
        f"operator's {OPERATOR_COVERED} of {HANDCHECK_BOUNDARIES}"
    )
    agrees = (v, n_cov, len(chosen)) == (OPERATOR_V, OPERATOR_COVERED, HANDCHECK_BOUNDARIES)
    out.append(f"  -> {'AGREES' if agrees else 'DISAGREES'}")
    return {"n": len(fit_cells[hour]), "correction": v, "covered": n_cov, "of": len(chosen)}


def input_files(inst: str) -> list[Path]:
    tick_dir = DATA / inst / "ticks_monthly"
    years = sorted({y for s, e in sampled_weeks(inst) for y in (s.year, (e - BAR).year)})
    return [*sorted(tick_dir.glob("*")), *(DATA / inst / "M15" / f"{y}.parquet" for y in years)]


def files_digest(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for path in paths:
        h.update(path.name.encode("utf-8"))
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def full_run() -> int:
    started = datetime.now(UTC)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout.strip()
    )
    out: list[str] = [
        "3c.2 spread correction -- fit to end-2024, validated on 2025-2026",
        f"Run {started.isoformat(timespec='seconds')}; commit {commit}"
        f"{' (working tree has uncommitted changes)' if dirty else ''}",
        f"Percentile {PERCENTILE} nearest-rank; gap {GAP_US // 60_000_000} min; "
        f"thin fit cell < {MIN_FIT_BARS} bars; unjudged cell < {MIN_TEST_BARS} test bars",
        "This run validates the method; backtests re-fit on data before their start only.",
    ]
    result: dict = {
        "run_utc": started.isoformat(),
        "commit": commit,
        "working_tree_dirty": dirty,
        "percentile": PERCENTILE,
        "gap_minutes": GAP_US // 60_000_000,
        "min_fit_bars": MIN_FIT_BARS,
        "min_test_bars": MIN_TEST_BARS,
        "test_from_utc": TEST_FROM.isoformat(),
        "timeframe": "M15",
        "instruments": {},
    }
    for inst in INSTRUMENTS:
        print(f"{datetime.now(UTC):%H:%M:%S} {inst}: reading ...", flush=True)
        data, _ = build(inst)
        files = input_files(inst)
        record = evaluate(inst, data, out)
        record["inputs"] = {
            "files": len(files),
            "sha256": files_digest(files),
            "weeks": len(sampled_weeks(inst)),
        }
        if inst == HANDCHECK_INSTRUMENT and not record["stopped"]:
            record["handcheck"] = handcheck_comparison(data, out)
        result["instruments"][inst] = record
        del data
    OUT.mkdir(parents=True, exist_ok=True)
    report = "\n".join(out) + "\n"
    (OUT / "validation_fit_to_2024.txt").write_text(report, encoding="utf-8", newline="\n")
    (OUT / "validation_fit_to_2024.json").write_text(
        json.dumps(result, indent=1, default=str), encoding="utf-8", newline="\n"
    )
    print(report)
    print(f"Written to {OUT}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="3c.2 spread correction: fit and validation.")
    parser.add_argument("--handcheck", action="store_true")
    args = parser.parse_args(argv)
    return handcheck() if args.handcheck else full_run()


if __name__ == "__main__":
    sys.exit(main())
