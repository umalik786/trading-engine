"""
Bar spacing check -- are stored bars really the width their folder says?

READ ONLY. Reads parquet bar times and config/instruments.yaml; touches no
terminal, writes nothing. Run after every extraction.

WHY. A venue can file bars of another width under a timeframe. On FTMO the
index "M15" history is daily bars until 2021-01-21, then HOURLY bars until
2021-09-14, then genuine 15-minute bars; index H1 and H4 are daily bars
until 2021-01-21. ReplayFeed gives every bar ts_close = ts_open + the
timeframe's width, so it would read a day's move as fifteen minutes and
nothing would error.

HOW. For every instrument, timeframe and calendar MONTH, the commonest gap
between consecutive bars in that month. In a genuine month it is the
timeframe's width: weekends, holidays and session breaks are rarer than
ordinary bar-to-bar steps. Month, not year: for index M15 in 2021 the
share of correctly spaced bars over the whole year is 64%, and only a
monthly view separates the hourly tier from the genuine one.

Each month is judged only on the bars the engine is allowed to read -- those
at or after the instrument's `bars_genuine_from` for that timeframe in
config/instruments.yaml (all of them, where none is set). Status per month:

  ok         commonest gap is the width, nothing excluded
  mixed      allowed part is fine, but part of the month was excluded or
             under 90% of its gaps are the width -- printed, not a failure
  excluded   wholly before bars_genuine_from -- printed, not a failure
  VIOLATION  the allowed bars' commonest gap is not the width, or fewer than
             two allowed bars to judge -- the check fails

Months are printed unless they are plainly ok (or always, with --verbose).

Run with:  uv run python check_bar_spacing.py [--data-root DIR] [--config FILE] [--verbose]
Exit code 0 only if there is no VIOLATION anywhere.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import groupby, pairwise
from pathlib import Path

import pyarrow.parquet as pq

from engine.core.instruments import load_bars_genuine_from
from engine.feeds.replay import DEFAULT_DATA_ROOT, TIMEFRAME_DURATIONS

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config" / "instruments.yaml"

# Below this share of width-sized gaps, a month whose commonest gap is still
# the width is reported as mixed. Informational only.
MIXED_BELOW = 0.90


@dataclass(frozen=True)
class MonthReport:
    month: str  # "YYYY-MM"
    bars: int
    commonest_gap: timedelta | None  # over all the month's bars, for display
    width_share: float  # share of the month's gaps equal to the width
    status: str


def _commonest_gap(times: list[datetime]) -> timedelta | None:
    gaps = Counter(b - a for a, b in pairwise(times))
    return gaps.most_common(1)[0][0] if gaps else None


def monthly_reports(
    times: list[datetime], width: timedelta, genuine_from: datetime | None
) -> list[MonthReport]:
    """One report per calendar month present in `times` (ascending, UTC)."""
    reports = []
    for month, group in groupby(times, key=lambda t: t.strftime("%Y-%m")):
        month_times = list(group)
        gaps = [b - a for a, b in pairwise(month_times)]
        share = sum(1 for g in gaps if g == width) / len(gaps) if gaps else 0.0
        allowed = [t for t in month_times if genuine_from is None or t >= genuine_from]

        if not allowed:
            status = "excluded"
        elif len(allowed) < 2 or _commonest_gap(allowed) != width:  # noqa: PLR2004
            status = "VIOLATION"
        elif len(allowed) < len(month_times) or share < MIXED_BELOW:
            status = "mixed"
        else:
            status = "ok"

        reports.append(
            MonthReport(month, len(month_times), _commonest_gap(month_times), share, status)
        )
    return reports


def _read_times(series_dir: Path) -> list[datetime]:
    times: list[datetime] = []
    for path in sorted(series_dir.glob("*.parquet")):
        times.extend(pq.read_table(path, columns=["time"]).column("time").to_pylist())
    return times


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--verbose", action="store_true", help="Print every month.")
    args = parser.parse_args(argv)

    genuine = load_bars_genuine_from(args.config)
    print(f"Bar spacing check -- {args.data_root}, config {args.config}")
    violations = 0

    for instrument in genuine:
        for timeframe, width in TIMEFRAME_DURATIONS.items():
            series_dir = args.data_root / instrument / timeframe
            if not series_dir.is_dir():
                continue
            genuine_from = genuine[instrument].get(timeframe)
            reports = monthly_reports(_read_times(series_dir), width, genuine_from)
            bad = [r for r in reports if r.status == "VIOLATION"]
            violations += len(bad)
            since = genuine_from.date().isoformat() if genuine_from else "all history"
            print(
                f"\n{instrument} {timeframe}  genuine from {since}  "
                f"{len(reports)} months, {len(bad)} violations"
            )
            for r in reports:
                if args.verbose or r.status != "ok":
                    gap = str(r.commonest_gap) if r.commonest_gap is not None else "--"
                    print(
                        f"  {r.month}  bars {r.bars:>6,}  commonest gap {gap:>15}  "
                        f"width share {r.width_share:6.1%}  {r.status}"
                    )

    print()
    if violations:
        print(f"{violations} VIOLATION(S) -- bars read by the engine are not their timeframe.")
        return 1
    print("No violations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
