"""Tests for the server clock. See docs/trading-engine-architecture.md
Appendix A.6 and `engine.core.clock`.

The FTMO figures here are market facts, not preferences: gold's weekly
close lands at 22:00 UTC in US winter and 21:00 in US summer, which is
what the +2/+3-on-the-US-calendar convention predicts and what the stored
data shows (see test_ftmo_server_timezone.py).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from itertools import pairwise

import pytest

from engine.core.clock import DstSwitchedServerClock, IanaServerClock

FTMO = DstSwitchedServerClock(
    winter_offset=timedelta(hours=2),
    summer_offset=timedelta(hours=3),
    dst_calendar="America/New_York",
)


class TestDstSwitchedOffsets:
    def test_winter_is_two_hours_ahead(self) -> None:
        assert FTMO.utc_offset(datetime(2025, 2, 5, 12, 0, tzinfo=UTC)) == timedelta(hours=2)

    def test_summer_is_three_hours_ahead(self) -> None:
        assert FTMO.utc_offset(datetime(2025, 7, 5, 12, 0, tzinfo=UTC)) == timedelta(hours=3)

    def test_it_switches_on_the_us_calendar_not_the_european_one(self) -> None:
        """The whole point of this shape. US clocks spring forward on
        2025-03-09; European ones not until 2025-03-30. On 2025-03-20 the
        server is already on summer time, which no European zone is."""
        mid_march = datetime(2025, 3, 20, 12, 0, tzinfo=UTC)

        assert FTMO.utc_offset(mid_march) == timedelta(hours=3)

    def test_a_naive_reference_is_read_as_a_server_wall_clock(self) -> None:
        naive = datetime(2025, 2, 5, 0, 0)  # noqa: DTZ001 -- naive input is the case under test

        assert FTMO.utc_offset(naive) == timedelta(hours=2)

    def test_server_reading_is_naive(self) -> None:
        server = FTMO.to_server_naive(datetime(2025, 2, 5, 22, 0, tzinfo=UTC))

        assert server == datetime(2025, 2, 6, 0, 0)  # noqa: DTZ001 -- naive by contract
        assert server.tzinfo is None


class TestRolloverInstants:
    def test_a_winter_rollover_is_at_22_00_utc(self) -> None:
        instants = FTMO.rollover_instants(
            datetime(2025, 2, 5, 0, 0, tzinfo=UTC),
            datetime(2025, 2, 6, 0, 0, tzinfo=UTC),
        )

        assert instants == [datetime(2025, 2, 5, 22, 0, tzinfo=UTC)]

    def test_a_summer_rollover_is_at_21_00_utc(self) -> None:
        instants = FTMO.rollover_instants(
            datetime(2025, 7, 5, 0, 0, tzinfo=UTC),
            datetime(2025, 7, 6, 0, 0, tzinfo=UTC),
        )

        assert instants == [datetime(2025, 7, 5, 21, 0, tzinfo=UTC)]

    def test_the_window_excludes_its_start_and_includes_its_end(self) -> None:
        """Half-open so consecutive windows tile: an instant belongs to
        exactly one of them, so nothing is charged twice or skipped."""
        instant = datetime(2025, 2, 5, 22, 0, tzinfo=UTC)

        assert FTMO.rollover_instants(instant, instant + timedelta(hours=1)) == []
        assert FTMO.rollover_instants(instant - timedelta(hours=1), instant) == [instant]

    def test_consecutive_windows_cover_every_instant_exactly_once(self) -> None:
        start = datetime(2025, 2, 1, 0, 0, tzinfo=UTC)
        boundaries = [start + timedelta(hours=6 * n) for n in range(40)]
        tiled = []
        for earlier, later in pairwise(boundaries):
            tiled.extend(FTMO.rollover_instants(earlier, later))

        whole = FTMO.rollover_instants(boundaries[0], boundaries[-1])
        assert tiled == whole
        assert len(tiled) == len(set(tiled))

    def test_a_weekend_gap_yields_three_instants(self) -> None:
        """Friday's close to Monday's open contains the Saturday, Sunday
        and Monday rollovers. Which of them costs anything is the cost
        model's decision, not the clock's."""
        instants = FTMO.rollover_instants(
            datetime(2025, 2, 7, 22, 0, tzinfo=UTC),
            datetime(2025, 2, 10, 23, 0, tzinfo=UTC),
        )

        assert len(instants) == 3

    def test_an_empty_window_yields_nothing(self) -> None:
        moment = datetime(2025, 2, 5, 12, 0, tzinfo=UTC)

        assert FTMO.rollover_instants(moment, moment) == []

    def test_a_backwards_window_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="before its start"):
            FTMO.rollover_instants(
                datetime(2025, 2, 6, tzinfo=UTC), datetime(2025, 2, 5, tzinfo=UTC)
            )

    def test_a_window_spanning_the_dst_switch_still_has_one_per_day(self) -> None:
        """US clocks move on 2025-03-09, so the rollover shifts from 22:00
        to 21:00 UTC mid-window. Each server day must still turn over
        exactly once -- no day doubled, none missed."""
        instants = FTMO.rollover_instants(
            datetime(2025, 3, 5, 0, 0, tzinfo=UTC),
            datetime(2025, 3, 15, 0, 0, tzinfo=UTC),
        )

        assert len(instants) == 10
        assert len({instant.date() for instant in instants}) == 10


class TestDayEndingLabel:
    def test_a_rollover_is_labelled_by_the_day_it_ends(self) -> None:
        """2025-02-05 22:00 UTC is midnight server on the 6th, so it ends
        Wednesday the 5th. This is the convention behind "triple swap on
        Wednesday night"; labelling it Thursday would move every triple
        charge by a day."""
        instant = datetime(2025, 2, 5, 22, 0, tzinfo=UTC)

        assert FTMO.server_date_ending(instant) == date(2025, 2, 5)
        assert FTMO.server_date_ending(instant).strftime("%A") == "Wednesday"

    def test_the_label_is_the_server_day_not_the_utc_day(self) -> None:
        """A summer rollover at 21:00 UTC on a Friday ends server-Friday,
        even though 21:00 UTC is still Friday in UTC too -- the point is
        that the date comes from the server reading."""
        instant = datetime(2025, 7, 4, 21, 0, tzinfo=UTC)

        assert FTMO.server_date_ending(instant) == date(2025, 7, 4)


class TestIanaClock:
    def test_it_takes_its_offset_from_the_named_zone(self) -> None:
        athens = IanaServerClock(zone="Europe/Athens")

        assert athens.utc_offset(datetime(2025, 2, 5, 12, 0, tzinfo=UTC)) == timedelta(hours=2)
        assert athens.utc_offset(datetime(2025, 7, 5, 12, 0, tzinfo=UTC)) == timedelta(hours=3)

    def test_it_switches_on_its_own_calendar_not_the_us_one(self) -> None:
        """Europe/Athens is still on winter time on 2025-03-20, where the
        FTMO clock has already moved. Same offsets, different calendar --
        which is exactly why the two shapes both exist."""
        athens = IanaServerClock(zone="Europe/Athens")
        mid_march = datetime(2025, 3, 20, 12, 0, tzinfo=UTC)

        assert athens.utc_offset(mid_march) == timedelta(hours=2)
        assert FTMO.utc_offset(mid_march) == timedelta(hours=3)

    def test_a_utc_server_rolls_over_at_midnight_utc(self) -> None:
        utc_clock = IanaServerClock(zone="UTC")

        assert utc_clock.rollover_instants(
            datetime(2025, 2, 5, 0, 0, tzinfo=UTC),
            datetime(2025, 2, 6, 0, 0, tzinfo=UTC),
        ) == [datetime(2025, 2, 6, 0, 0, tzinfo=UTC)]
