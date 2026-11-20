"""The rule choosing which week of each month goes into the 3c.2 tick sample.

Decided 2026-11-20 (docs/state.md, 3c.0): one Sunday 00:00 UTC to Sunday
00:00 UTC week per month -- exactly one trading week -- containing an anchor
day that rotates through the 4th, 11th, 18th and 25th by
(month - 1 + year) mod 4. A rotation by month alone repeats every year
(twelve is a multiple of four), so each calendar month always got the same
anchor: December was always Christmas week. Adding the year moves the cycle
on by one each year.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ANCHORS = {4, 11, 18, 25}


@pytest.fixture
def weeks(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO))
    import tick_sample_weeks  # noqa: PLC0415 -- needs REPO on sys.path first

    return tick_sample_weeks


def test_the_anchor_follows_month_plus_year(weeks):
    # (1 - 1 + 2020) mod 4 = 0 -> 4th; one step on per month and per year.
    assert weeks.anchor_day(2020, 1) == 4
    assert weeks.anchor_day(2020, 2) == 11
    assert weeks.anchor_day(2021, 1) == 11
    assert weeks.anchor_day(2023, 1) == 25


@pytest.mark.parametrize("month", range(1, 13))
def test_every_calendar_month_cycles_through_all_four_anchors(weeks, month):
    """Over ANY four consecutive years, each calendar month uses each anchor
    once -- the property the month-only rotation lacked."""
    for first_year in range(2019, 2031):
        used = {weeks.anchor_day(first_year + k, month) for k in range(4)}
        assert used == ANCHORS, f"month {month}, years {first_year}-{first_year + 3}: {used}"


def test_a_week_is_sunday_to_sunday_utc_and_contains_its_anchor(weeks):
    for year in range(2019, 2031):
        for month in range(1, 13):
            start, end = weeks.sample_week(year, month)
            anchor = date(year, month, weeks.anchor_day(year, month))
            assert start.tzinfo is UTC
            assert end.tzinfo is UTC
            assert start.weekday() == 6, f"{year}-{month:02d} starts on {start:%A}"
            assert (start.hour, start.minute, start.second) == (0, 0, 0)
            assert end - start == timedelta(days=7)
            assert start.date() <= anchor < end.date()


def test_an_anchor_on_a_sunday_starts_its_own_week(weeks):
    # 2022-12-11 is a Sunday, and December 2022's anchor is the 11th.
    assert weeks.anchor_day(2022, 12) == 11
    assert weeks.sample_week(2022, 12)[0] == datetime(2022, 12, 11, tzinfo=UTC)


def test_a_week_can_start_in_the_previous_month(weeks):
    # December 2021's anchor is the 4th, a Saturday; its week starts Sunday 28 November.
    assert weeks.sample_week(2021, 12)[0] == datetime(2021, 11, 28, tzinfo=UTC)


def test_no_two_sampled_weeks_overlap(weeks):
    sample = weeks.sample_weeks((2019, 12), (2030, 12))
    for (s1, e1), (s2, _) in pairwise(sample):
        assert e1 <= s2, f"week {s1:%Y-%m-%d} overlaps week {s2:%Y-%m-%d}"


def test_the_range_is_inclusive_at_both_ends(weeks):
    sample = weeks.sample_weeks((2019, 12), (2026, 10))
    assert len(sample) == 83
    assert sample[0][0] == datetime(2019, 12, 15, tzinfo=UTC)
    assert sample[-1][0] == datetime(2026, 10, 25, tzinfo=UTC)
