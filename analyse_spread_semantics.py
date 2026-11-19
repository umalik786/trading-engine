"""
Phase 3c.0 -- what does MT5's stored per-bar spread mean?

READ ONLY. Reads the tick sample and the stored bars under C:/trading/data/raw;
writes nothing. Analysis tooling, not engine code.

Three questions, all decided before the C.1 spread model is built
(docs/state.md, "Phase 3c plan and decisions"):

Q1. Is a bar's stored `spread` the minimum spread seen inside the bar, the
    maximum, the first tick's, the last tick's, or the average? For every M1
    and M15 bar inside the tick window, each candidate is rebuilt from the
    ticks inside the bar (spread = ask - bid, in points) and compared with
    the stored figure.

    A match only counts as evidence where the candidates DISAGREE. In a bar
    whose ticks all have one spread, min = max = first = last, and every
    candidate "matches" -- that bar cannot tell them apart, the same lesson
    as the phase 2 and 3a fixtures. So match rates are reported over
    "discriminating" bars only: bars where min < max.

Q2. EURUSD's zero spreads (ask = bid): how often in the ticks, by server hour,
    and how often stored bars carry a zero spread, year by year over the whole
    history. The cost config treats every stored zero as missing data.

Q3. Are EURUSD and XAUUSD spreads fixed in the Asian session? Per server hour:
    the commonest tick spread and the share of ticks at it.

Hours are on the trade server's clock, taken from the FTMO cost profile's own
server_clock (config/cost_ftmo_demo.yaml) so there is one definition.

Run with:  uv run python analyse_spread_semantics.py
"""

from __future__ import annotations

import warnings
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from engine.core.instruments import load_point_sizes
from engine.costs.configured import build_server_clock
from engine.costs.profile import load_cost_profile

REPO = Path(__file__).resolve().parent
DATA = Path("C:/trading/data/raw")
INSTRUMENTS = ["NAS100", "US500", "EURUSD", "XAUUSD", "XAGUSD"]
WINDOW_START = datetime(2026, 10, 19, tzinfo=UTC)
WINDOW_END = datetime(2026, 11, 14, tzinfo=UTC)  # exclusive
TIMEFRAMES = {"M1": 1, "M15": 15}  # minutes
CANDIDATES = ["min", "max", "first", "last", "mean"]

POINTS = load_point_sizes(REPO / "config" / "instruments.yaml")
with warnings.catch_warnings():
    warnings.simplefilter("ignore")  # the profile's placeholder warning is not news here
    SERVER_CLOCK = build_server_clock(
        load_cost_profile(REPO / "config" / "cost_ftmo_demo.yaml").server_clock
    )


def load_ticks(instrument: str) -> pa.Table:
    """All ticks in the window: time, spread in integer points, server hour."""
    files = sorted((DATA / instrument / "ticks").glob("*.parquet"))
    table = pa.concat_tables(pq.read_table(f, columns=["time", "bid", "ask"]) for f in files)
    point = float(POINTS[instrument])
    raw = pc.divide(
        pc.subtract(pc.cast(table["ask"], pa.float64()), pc.cast(table["bid"], pa.float64())),
        point,
    )
    spread = pc.cast(pc.round(raw), pa.int64())
    # Server hour: one offset lookup per distinct UTC hour (the offset only
    # changes at a DST switch, which falls on a whole hour).
    utc_hour = pc.floor_temporal(table["time"], unit="hour")
    distinct = pc.unique(utc_hour)
    server_hour = [(h + SERVER_CLOCK.utc_offset(h)).hour for h in distinct.to_pylist()]
    index = pc.index_in(utc_hour, value_set=distinct)
    hours = pc.take(pa.array(server_hour, type=pa.int8()), index)
    return pa.table({"time": table["time"], "spread": spread, "server_hour": hours})


def per_bar_candidates(ticks: pa.Table, minutes: int) -> pa.Table:
    key = pc.floor_temporal(ticks["time"], multiple=minutes, unit="minute")
    grouped = (
        pa.table({"time": key, "s": ticks["spread"]})
        .group_by("time", use_threads=False)  # keeps tick order, so first/last are real
        .aggregate(
            [
                ("s", "min"),
                ("s", "max"),
                ("s", "first"),
                ("s", "last"),
                ("s", "mean"),
                ("s", "count"),
            ]
        )
    )
    return grouped.rename_columns(["time", "min", "max", "first", "last", "mean", "ticks"])


def stored_bars(instrument: str, timeframe: str) -> pa.Table:
    table = pq.read_table(
        DATA / instrument / timeframe / "2026.parquet", columns=["time", "spread"]
    )
    in_window = pc.and_(
        pc.greater_equal(table["time"], pa.scalar(WINDOW_START, pa.timestamp("us", tz="UTC"))),
        pc.less(table["time"], pa.scalar(WINDOW_END, pa.timestamp("us", tz="UTC"))),
    )
    return table.filter(in_window).rename_columns(["time", "stored"])


def q1(instrument: str, ticks: pa.Table) -> None:
    for timeframe, minutes in TIMEFRAMES.items():
        bars = stored_bars(instrument, timeframe)
        joined = bars.join(per_bar_candidates(ticks, minutes), "time", join_type="inner")
        stored = pc.cast(joined["stored"], pa.int64())
        disc = pc.less(joined["min"], joined["max"])
        n_disc = pc.sum(disc).as_py() or 0
        print(
            f"  {timeframe:<4} bars in window {bars.num_rows:>6,}  "
            f"with ticks {joined.num_rows:>6,}  discriminating (min<max) {n_disc:>6,}"
        )
        for c in CANDIDATES:
            value = pc.round(joined[c]) if c == "mean" else joined[c]
            match = pc.equal(pc.cast(value, pa.int64()), stored)
            all_rate = pc.mean(pc.cast(match, pa.float64())).as_py()
            disc_rate = pc.sum(pc.and_(match, disc)).as_py() / n_disc if n_disc else float("nan")
            print(
                f"       {c:<6} matches stored: all bars {all_rate:7.2%}   "
                f"discriminating bars {disc_rate:7.2%}"
            )
        below = pc.sum(pc.less(stored, joined["min"])).as_py()
        above = pc.sum(pc.greater(stored, joined["max"])).as_py()
        print(
            f"       stored below every tick spread in the bar: {below:,};  "
            f"above every one: {above:,}"
        )


def q2_ticks(ticks: pa.Table) -> None:
    zero = pc.equal(ticks["spread"], 0)
    print(
        f"  ticks with zero spread: {pc.sum(zero).as_py():,} of {ticks.num_rows:,} "
        f"({pc.mean(pc.cast(zero, pa.float64())).as_py():.1%})"
    )


def q2_zero_by_hour(ticks: pa.Table) -> None:
    print("  server hour : share of ticks with zero spread")
    row = []
    for h in range(24):
        sel = pc.equal(ticks["server_hour"], h)
        n = pc.sum(sel).as_py() or 0
        z = pc.sum(pc.and_(sel, pc.equal(ticks["spread"], 0))).as_py() or 0
        row.append(f"{h:02d}:{z / n:5.1%}" if n else f"{h:02d}:  -- ")
    for i in range(0, 24, 6):
        print("    " + "   ".join(row[i : i + 6]))


def q2_stored_zero_by_year(instrument: str, timeframe: str) -> None:
    out = []
    for f in sorted((DATA / instrument / timeframe).glob("*.parquet")):
        s = pq.read_table(f, columns=["spread"])["spread"]
        if len(s):
            out.append(f"{f.stem}:{pc.mean(pc.cast(pc.equal(s, 0), pa.float64())).as_py():5.1%}")
    print(f"  stored {timeframe} bars with spread 0, by year:")
    for i in range(0, len(out), 6):
        print("    " + "  ".join(out[i : i + 6]))


def q3(ticks: pa.Table) -> None:
    print("  server hour : commonest tick spread (points), share of ticks at it, p10 / p50 / p90")
    for h in range(24):
        sel = ticks.filter(pc.equal(ticks["server_hour"], h))["spread"]
        if len(sel) == 0:
            print(f"    {h:02d}  no ticks")
            continue
        counts = pc.value_counts(sel)
        top = max(counts.to_pylist(), key=lambda d: d["counts"])
        q = pc.quantile(sel, q=[0.1, 0.5, 0.9], interpolation="lower").to_pylist()
        print(
            f"    {h:02d}  mode {top['values']:>5}  at mode {top['counts'] / len(sel):6.1%}   "
            f"{q[0]:>5} / {q[1]:>5} / {q[2]:>5}   ({len(sel):,} ticks)"
        )


def main() -> None:
    print(
        f"3c.0 spread semantics -- ticks {WINDOW_START:%Y-%m-%d} to {WINDOW_END:%Y-%m-%d} (excl.)"
    )
    ticks = {i: load_ticks(i) for i in INSTRUMENTS}

    print("\n== Q1: what is the stored per-bar spread?")
    for i in INSTRUMENTS:
        print(f"\n{i}")
        q1(i, ticks[i])

    print("\n== Q2: zero spreads")
    for i in INSTRUMENTS:
        print(f"\n{i}")
        q2_ticks(ticks[i])
    print("\nEURUSD")
    q2_zero_by_hour(ticks["EURUSD"])
    for tf in ("M1", "M15"):
        q2_stored_zero_by_year("EURUSD", tf)

    print("\n== Q3: fixed spreads by server hour")
    for i in ("EURUSD", "XAUUSD"):
        print(f"\n{i}")
        q3(ticks[i])


if __name__ == "__main__":
    main()
