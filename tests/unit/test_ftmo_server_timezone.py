"""Market-fact regression test for the FTMO server-timezone conversion.

See docs/trading-engine-architecture.md Appendix A.6 (server timezone,
verified 2026-09-17) and docs/state.md's CRITICAL section for the incident
this guards against (every stored timestamp was silently mislabelled for
weeks before ReplayFeed's own future-bar assertion caught it by accident).

Why this test exists: everything else that checks the server-timezone
conversion -- extract_mt5_data.py's docstrings, the manifest's recorded
verification, Appendix A.6 itself -- ultimately rests on a claim FTMO
makes about their own platform. FTMO can restate or change that claim at
any time, and nothing in this repo would notice on its own. This test
instead checks stored data against an external, physical fact FTMO cannot
silently change: FX closes Friday 17:00 New York, every year, regardless
of what any broker's platform does. If FTMO ever alters its server's
convention -- a different base offset, a different DST calendar, dropping
DST entirely -- and the data is re-extracted without extract_mt5_data.py's
conversion being updated to match, the stored weekly gap will land at the
wrong UTC hour and this test goes red, without anyone needing to remember
to look for it.

Fixture: tests/unit/fixtures/ftmo_timezone/EURUSD/M15/2024.parquet -- 48
real bars extracted from the corrected production data (one small window
bracketing the January 2024 weekend, one bracketing the July 2024
weekend), same schema extract_mt5_data.py writes. Small and committed --
CI has no access to C:/trading/data/.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

from engine.feeds.replay import ReplayFeed

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "ftmo_timezone"


def _weekly_gap_close(year: int, month: int) -> datetime:
    """The ts_close of the last bar before the weekend gap in the fixture's
    window for this year/month. Both fixture windows start on a Friday the
    5th and run into the following Tuesday, so days 5-9 safely bracket it.
    """
    feed = ReplayFeed(
        instrument="EURUSD",
        timeframe="M15",
        range_start=datetime(year, month, 5, tzinfo=UTC),
        range_end=datetime(year, month, 9, tzinfo=UTC),
        data_root=FIXTURE_ROOT,
    )
    bars = list(feed.stream())
    for earlier, later in pairwise(bars):
        if (later.ts_close - earlier.ts_close).days >= 1:
            return earlier.ts_close
    raise AssertionError(f"no weekend gap found in fixture window {year}-{month:02d}")


class TestServerTimezoneAgainstMarketFact:
    """FX closes Friday 17:00 New York. In US winter (EST, UTC-5) that is
    22:00 UTC; in US summer (EDT, UTC-4) that is 21:00 UTC. If the stored
    weekly close ever lands anywhere else, the server-timezone conversion
    in extract_mt5_data.py no longer matches reality -- catches a silently
    changed or mis-verified broker convention, not just a code regression.
    """

    def test_winter_close_lands_at_22_00_utc(self) -> None:
        close = _weekly_gap_close(2024, 1)
        assert close == datetime(2024, 1, 5, 22, 0, tzinfo=UTC)

    def test_summer_close_lands_at_21_00_utc(self) -> None:
        close = _weekly_gap_close(2024, 7)
        assert close == datetime(2024, 7, 5, 21, 0, tzinfo=UTC)
