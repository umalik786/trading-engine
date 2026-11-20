"""
Which week of each month goes into the 3c.2 tick sample.

Pure date arithmetic, no MetaTrader5 import, so its tests run everywhere.
Decided 2026-11-20 (docs/state.md, 3c.0 / spread-table source):

- One week per month: Sunday 00:00 UTC to the next Sunday 00:00 UTC. That
  window holds exactly one trading week -- the Sunday-evening open, five
  daily rollovers, the Friday close -- and nothing of the weeks either side.
- The week is the one containing an ANCHOR day: the 4th, 11th, 18th or 25th,
  chosen by (month - 1 + year) mod 4.

Why the anchor rotates: a fixed 15th never contained US payrolls (always on
or before the 7th) and over-sampled CPI (usually the 10th-15th). Why the
year is in the formula: a rotation by month alone repeats every year,
because twelve is a multiple of four, so each calendar month always got the
same anchor -- December was always Christmas week. Adding the year moves the
cycle on by one each year, so every calendar month passes through all four
anchors over any four consecutive years.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

ANCHOR_DAYS = (4, 11, 18, 25)
_WEEK = timedelta(days=7)
_DECEMBER = 12


def anchor_day(year: int, month: int) -> int:
    """The day of `month` whose week is sampled."""
    return ANCHOR_DAYS[(month - 1 + year) % 4]


def sample_week(year: int, month: int) -> tuple[datetime, datetime]:
    """[start, end) in UTC: the Sunday 00:00 on or before the anchor day,
    and seven days later. A week may start in the previous month."""
    anchor = date(year, month, anchor_day(year, month))
    sunday = anchor - timedelta(days=(anchor.weekday() + 1) % 7)  # Monday=0 ... Sunday=6
    start = datetime(sunday.year, sunday.month, sunday.day, tzinfo=UTC)
    return start, start + _WEEK


def sample_weeks(first: tuple[int, int], last: tuple[int, int]) -> list[tuple[datetime, datetime]]:
    """One week per month from `first` to `last` (year, month), both included."""
    out = []
    year, month = first
    while (year, month) <= last:
        out.append(sample_week(year, month))
        year, month = (year + 1, 1) if month == _DECEMBER else (year, month + 1)
    return out
