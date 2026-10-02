"""The trade server's clock, and when its day turns over.

See docs/trading-engine-architecture.md §3 (`core/clock.py`), Appendix A.3
and A.6 (MT5 returns server time, not UTC; the server's zone is per-broker
configuration that must be verified rather than assumed).

Financing is charged at the server's daily rollover, which is midnight on
this clock. Everything about where that instant falls lives here, so no
component has to hold a constant like "22:00 UTC" -- a figure that is
correct for roughly four months of the year and silently wrong for the
rest, because the offset moves twice annually.

THIS IS NOT THE ACCOUNTING-DAY CLOCK. §6.5 gives each firm an
accounting-day boundary in its own timezone, used for daily loss limits.
FTMO monitors that in Prague time on the European DST calendar, while its
MT5 server runs EET-magnitude offsets on the US calendar. The two differ
by two hours rather than one for two to three weeks each spring and
autumn. They are deliberately separate objects with separate
configuration, and merging them would be correct most of the year and
wrong exactly when it mattered.

TWO SHAPES, because a server clock is venue configuration:

- `IanaServerClock` -- the server runs a real timezone, named by its IANA
  identifier. The library handles DST. This is the sane case and what a
  retail broker is likely to use.
- `DstSwitchedServerClock` -- the server runs fixed winter and summer
  offsets, but switches between them on some *other* region's DST
  calendar. FTMO is +2/+3 switching on `America/New_York`. This
  combination corresponds to no IANA zone, because no geographic region
  observes it, so it cannot be expressed as a zone name. The DST calendar
  still comes from the tz database -- just a different region's entry --
  so a change in US daylight-saving law is picked up automatically rather
  than needing a hand-maintained table of transition dates.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

_MIDNIGHT = {"hour": 0, "minute": 0, "second": 0, "microsecond": 0}


class ServerClock(Protocol):
    def utc_offset(self, reference: datetime) -> timedelta:
        """How far ahead of UTC the server clock is at `reference`.

        `reference` may be UTC-aware (treated exactly) or naive, in which
        case it is read as an approximate server wall-clock reading --
        accurate enough to place it on the correct side of a DST
        transition, which is all that is needed because a venue brackets
        each transition with a trading halt rather than flipping
        instantaneously.
        """
        ...

    def to_server_naive(self, moment_utc: datetime) -> datetime:
        """The server's own wall-clock reading of a UTC instant, as a naive
        datetime. Naive because the server's zone may not be nameable."""
        ...

    def rollover_instants(self, after: datetime, through: datetime) -> list[datetime]:
        """Every server midnight in the half-open window (after, through],
        in UTC, ascending.

        Half-open so that consecutive windows tile without overlapping: an
        instant belongs to exactly one window however the caller slices
        time, and no instant is counted twice or dropped across a gap.
        """
        ...

    def server_date_ending(self, rollover_instant_utc: datetime) -> date:
        """The server-local date that ENDS at this rollover.

        A rollover from Wednesday into Thursday is labelled Wednesday,
        which is the convention behind "triple swap on Wednesday night".
        Labelling it Thursday instead would move every triple charge by a
        day -- see the note in docs/state.md; this convention is recorded
        as unverified until read off a real deal record.
        """
        ...


class _RolloverMixin:
    """Shared rollover arithmetic, in terms of `utc_offset` alone."""

    def to_server_naive(self, moment_utc: datetime) -> datetime:
        return (moment_utc + self.utc_offset(moment_utc)).replace(tzinfo=None)

    def _midnight_utc(self, server_day: date) -> datetime:
        """The UTC instant at which `server_day` begins on the server.

        The offset is taken from the naive server reading rather than from
        a UTC instant, because the instant is what is being solved for.
        """
        naive_midnight = datetime(server_day.year, server_day.month, server_day.day)  # noqa: DTZ001
        return (naive_midnight - self.utc_offset(naive_midnight)).replace(tzinfo=UTC)

    def rollover_instants(self, after: datetime, through: datetime) -> list[datetime]:
        if through < after:
            raise ValueError(f"window end {through!r} is before its start {after!r}")
        # Widen by a day either side before filtering, so a midnight whose
        # UTC instant is pulled across a date boundary by the offset, or
        # shifted by a DST transition, is still considered.
        first = self.to_server_naive(after).date() - timedelta(days=1)
        last = self.to_server_naive(through).date() + timedelta(days=1)
        instants = []
        day = first
        while day <= last:
            instant = self._midnight_utc(day)
            if after < instant <= through:
                instants.append(instant)
            day += timedelta(days=1)
        return instants

    def server_date_ending(self, rollover_instant_utc: datetime) -> date:
        # One microsecond before the rollover is the last moment of the
        # day that is ending.
        return self.to_server_naive(rollover_instant_utc - timedelta(microseconds=1)).date()


class IanaServerClock(_RolloverMixin):
    """A server running a real, nameable timezone."""

    def __init__(self, zone: str) -> None:
        self._zone = ZoneInfo(zone)
        self.zone_name = zone

    def utc_offset(self, reference: datetime) -> timedelta:
        if reference.tzinfo is None:
            probe = reference.replace(tzinfo=self._zone)
        else:
            probe = reference.astimezone(self._zone)
        offset = probe.utcoffset()
        if offset is None:  # pragma: no cover -- a named zone always has one
            raise ValueError(f"zone {self.zone_name!r} returned no UTC offset")
        return offset


class DstSwitchedServerClock(_RolloverMixin):
    """Fixed winter and summer offsets, switching on another region's DST
    calendar.

    FTMO: +2 in winter, +3 in summer, transitioning on `America/New_York`.
    Verified 2026-09-17 from FTMO's own trading updates -- they state that
    the platform moves to GMT+3 on the US spring-forward date and back on
    the US fall-back date, which leaves a two-to-three week window each
    spring and autumn where the server clock and European time differ by
    two hours rather than one.
    """

    def __init__(
        self,
        winter_offset: timedelta,
        summer_offset: timedelta,
        dst_calendar: str,
    ) -> None:
        self._winter = winter_offset
        self._summer = summer_offset
        self._calendar = ZoneInfo(dst_calendar)
        self.dst_calendar_name = dst_calendar

    def utc_offset(self, reference: datetime) -> timedelta:
        if reference.tzinfo is None:
            probe = reference.replace(tzinfo=self._calendar)
        else:
            probe = reference.astimezone(self._calendar)
        in_summer = probe.dst() != timedelta(0)
        return self._summer if in_summer else self._winter
