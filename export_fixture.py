"""
Fixture export — XAUUSD M15 windows, for the phase 2 golden test.

Reads bars through `ReplayFeed` and writes them out verbatim to CSVs the
golden test can load. Touches nothing on disk except the CSVs it writes.

IT COMPUTES NOTHING, DELIBERATELY. No P&L, no buy-and-hold, no high, no
low, no mean, no bar-count-per-day. The fixtures exist so that the phase 2
exit criterion can be checked against figures worked out independently of
this codebase — and a script that printed a price range or a summary
statistic alongside the data would be handing over part of the answer with
the question. The only things printed per window are the row count and the
first and last rows, so that what landed in each file can be seen without
opening it.

VALUES ARE COPIED, NOT CONVERTED. Prices go through `str(Decimal)` — no
float anywhere, no rounding, no reformatting, no padding. Whatever
precision the parquet file holds is the precision written. Timestamps are
ISO-8601 with a Z suffix, which is what the harness's loader expects and
refuses to guess at.

Line endings are forced to LF, matching the repository's `.gitattributes`,
so a committed fixture does not change shape depending on which machine
wrote it.

ON EXPORTING MORE THAN ONE WINDOW. Windows are listed in `EXPORTS` and
differ only in start, end and filename; the reading and writing happen
once, in `export_window`. A fixture's position is opened at its SECOND
bar's open, so two windows over the same week that begin at different bars
are two independent checks of the same accounting rather than the same
check twice.

Prerequisites:
  - Extracted parquet data under C:\\trading\\data\\raw
  - Run with:  uv run python export_fixture.py

Rerunning is safe: the same window over unchanged data produces a
byte-identical file, so a fixture already pinned to an expected figure is
not disturbed.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from engine.core.instruments import load_point_sizes
from engine.core.types import Bar
from engine.feeds.replay import ReplayFeed

INSTRUMENT = "XAUUSD"
TIMEFRAME = "M15"

HEADER = ("ts_open", "ts_close", "open", "high", "low", "close", "volume", "spread")

REPO_ROOT = Path(__file__).resolve().parent
FIXTURE_DIR = REPO_ROOT / "tests" / "golden" / "fixtures"
INSTRUMENTS_CONFIG = REPO_ROOT / "config" / "instruments.yaml"


@dataclass(frozen=True)
class Export:
    """One window to copy out. `range_start` is inclusive, `range_end`
    exclusive, matching `ReplayFeed`."""

    range_start: datetime
    range_end: datetime
    filename: str


# Both windows end at the same instant and cover the same week, which
# contains one weekend plus the daily session breaks in gold. They differ
# only in where they start, and therefore in which bar is their second.
EXPORTS = (
    Export(
        range_start=datetime(2025, 2, 5, 0, 0, tzinfo=UTC),
        range_end=datetime(2025, 2, 12, 0, 0, tzinfo=UTC),
        filename="xauusd_m15_2025-02-05_2025-02-12.csv",
    ),
    Export(
        range_start=datetime(2025, 2, 5, 2, 45, tzinfo=UTC),
        range_end=datetime(2025, 2, 12, 0, 0, tzinfo=UTC),
        filename="xauusd_m15_2025-02-05T0245_2025-02-12.csv",
    ),
    # Phase 3a. Starts at 21:45 so the deciding bar, the fill bar and the
    # last bar all carry DIFFERENT spreads (64, 27 and 23 points). The two
    # windows above cannot separate a spread taken from the deciding bar
    # from one taken from the fill bar, because in both of them those two
    # bars happen to share a spread -- the same degeneracy as the 00:00
    # window's equal open and close, one layer down.
    Export(
        range_start=datetime(2025, 2, 5, 21, 45, tzinfo=UTC),
        range_end=datetime(2025, 2, 12, 0, 0, tzinfo=UTC),
        filename="xauusd_m15_2025-02-05T2145_2025-02-12.csv",
    ),
)


def iso_z(moment: datetime) -> str:
    """ISO-8601 with a Z suffix rather than +00:00. Both are valid and mean
    the same thing; Z is written because it is unambiguous to read."""
    return moment.isoformat().replace("+00:00", "Z")


def row_for(bar: Bar) -> tuple[str, ...]:
    return (
        iso_z(bar.ts_open),
        iso_z(bar.ts_close),
        str(bar.open),
        str(bar.high),
        str(bar.low),
        str(bar.close),
        str(bar.volume),
        str(bar.spread),
    )


def export_window(spec: Export) -> None:
    print("-" * 70)
    print(f"{INSTRUMENT} {TIMEFRAME}  {iso_z(spec.range_start)} to {iso_z(spec.range_end)}")
    print("-" * 70)

    feed = ReplayFeed(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        range_start=spec.range_start,
        range_end=spec.range_end,
        point=load_point_sizes(INSTRUMENTS_CONFIG)[INSTRUMENT],
    )
    rows = [row_for(bar) for bar in feed.stream()]

    if not rows:
        print("  No bars in that range. Nothing written.")
        return

    output_path = FIXTURE_DIR / spec.filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerows(rows)

    print(f"  Rows written : {len(rows)}")
    print(f"  Header       : {','.join(HEADER)}")
    print(f"  First row    : {','.join(rows[0])}")
    print(f"  Last row     : {','.join(rows[-1])}")
    print(f"  Written to   : {output_path}")


def main() -> None:
    print("=" * 70)
    print("FIXTURE EXPORT — copies bars out, computes nothing")
    print("=" * 70)
    for spec in EXPORTS:
        print()
        export_window(spec)
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
