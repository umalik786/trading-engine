"""
Server-timezone check against stored bars -- run after every extraction.

READ ONLY. Reads EURUSD M15 parquet from the data folder; touches no
terminal, writes nothing.

WHAT IT CHECKS. FX closes for the weekend at 17:00 New York time. The last
EURUSD M15 bar of each Friday below must therefore close at a fixed UTC
hour. The expected values are the operator's, written down independently of
any code in this repository -- they are not computed from
engine.core.clock or extract_mt5_data.py, because a check derived from the
code under test would agree with that code whatever it did.

WHY THESE THREE FRIDAYS. The FTMO server switches between +2 and +3 on the
United States daylight-saving calendar (spec Appendix A.6). In most weeks
the US and European calendars agree, so a converter using the wrong one
passes. Two of these dates fall in the weeks where they disagree:

  - Fri 14 Mar 2025: US already on summer time (from 9 Mar), Europe not
    until 30 Mar.
  - Fri 31 Oct 2025: Europe back on winter time (from 26 Oct), US not
    until 2 Nov.
  - Fri 17 Jan 2025: both calendars on winter time. A control -- it passes
    under either calendar, and fails only if the conversion is missing or
    wrong in some other way.

Prerequisites:
  - EURUSD M15 extracted for 2025 (extract_mt5_data.py)
  - Run with:  uv run python check_dst_boundaries.py
               uv run python check_dst_boundaries.py --data-root <folder>

Exit code 0 only if every date passes. Missing data is a failure, never a
skip.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from engine.feeds.replay import DEFAULT_DATA_ROOT, ReplayFeed

# The operator's expected values. Do not derive these from code.
# (Friday's UTC date, expected ts_close of that day's last M15 bar)
EXPECTED_FRIDAY_CLOSES = [
    (datetime(2025, 1, 17, tzinfo=UTC), datetime(2025, 1, 17, 22, 0, tzinfo=UTC)),
    (datetime(2025, 3, 14, tzinfo=UTC), datetime(2025, 3, 14, 21, 0, tzinfo=UTC)),
    (datetime(2025, 10, 31, tzinfo=UTC), datetime(2025, 10, 31, 21, 0, tzinfo=UTC)),
]

INSTRUMENT = "EURUSD"
TIMEFRAME = "M15"
# EURUSD's point size. ReplayFeed requires one to read the spread column;
# this check does not use the spread.
EURUSD_POINT = Decimal("0.00001")


def last_close_on(day_utc: datetime, data_root: Path) -> datetime | None:
    """ts_close of the last bar whose open falls on this UTC date, or None
    if the stored data has no bars that day."""
    feed = ReplayFeed(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        range_start=day_utc,
        range_end=day_utc + timedelta(days=1),
        point=EURUSD_POINT,
        data_root=data_root,
    )
    last = None
    for bar in feed.stream():
        last = bar
    return last.ts_close if last else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help=f"Folder holding <INSTRUMENT>/<TF>/<year>.parquet (default {DEFAULT_DATA_ROOT})",
    )
    args = parser.parse_args()

    print(f"DST boundary check -- {INSTRUMENT} {TIMEFRAME} under {args.data_root}\n")
    failures = 0
    for day, expected in EXPECTED_FRIDAY_CLOSES:
        actual = last_close_on(day, args.data_root)
        label = day.strftime("%a %d %b %Y")
        if actual is None:
            print(f"  FAIL  {label}: no bars stored for this date")
            failures += 1
        elif actual != expected:
            print(
                f"  FAIL  {label}: last bar closes {actual:%a %H:%M} UTC, "
                f"expected {expected:%a %H:%M} UTC"
            )
            failures += 1
        else:
            print(f"  PASS  {label}: last bar closes {actual:%H:%M} UTC")

    print()
    if failures:
        print(f"{failures} of {len(EXPECTED_FRIDAY_CLOSES)} FAILED -- do not use this data.")
        return 1
    print(f"All {len(EXPECTED_FRIDAY_CLOSES)} passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
