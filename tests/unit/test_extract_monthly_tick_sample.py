"""extract_mt5_ticks.py's monthly-sample mode: several separate weeks into
ticks_monthly/, described by ONE manifest covering every week.

The reason for the test: the contiguous mode writes its manifest per run, so
running it once per week would leave a manifest describing only the last
week. Fake MT5 here: two ticks per weekday, none at weekends.

Marked requires_mt5 because the extractor imports MetaTrader5. Needs the
package, not a terminal. Run with:  uv run --extra mt5 pytest -m requires_mt5
"""

from __future__ import annotations

import calendar
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("MetaTrader5")

import numpy as np

pytestmark = pytest.mark.requires_mt5

REPO = Path(__file__).resolve().parents[2]
TICK = np.dtype(
    [
        ("time", "<i8"),
        ("bid", "<f8"),
        ("ask", "<f8"),
        ("last", "<f8"),
        ("volume", "<u8"),
        ("time_msc", "<i8"),
        ("flags", "<u4"),
        ("volume_real", "<f8"),
    ]
)


def test_two_weeks_land_in_ticks_monthly_with_one_manifest(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO))
    import extract_mt5_ticks as xt  # noqa: PLC0415 -- needs REPO on sys.path first
    import tick_sample_weeks  # noqa: PLC0415

    def fake_copy_ticks_range(_symbol, start, _end, _flags):
        # `start` is the server-clock reading of (UTC midnight - 1 minute).
        day = (start + timedelta(minutes=1) - timedelta(hours=2)).date()
        if day.weekday() >= 5:
            return np.array([], dtype=TICK)
        noon_server = calendar.timegm(day.timetuple()) * 1000 + (14 * 3600 * 1000)
        rows = [
            (t // 1000, 1.1, 1.1001, 0.0, 0, t, 6, 0.0) for t in (noon_server, noon_server + 500)
        ]
        return np.array(rows, dtype=TICK)

    monkeypatch.setattr(xt, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(xt.mt5, "copy_ticks_range", fake_copy_ticks_range)

    # January 2025 (US winter, server +2) and February 2025.
    sample = tick_sample_weeks.sample_weeks((2025, 1), (2025, 2))
    per_day = xt.extract_weeks("EURUSD", "EURUSD", 5, sample, subdir="ticks_monthly", force=True)
    xt.write_sample_manifest(
        "EURUSD", "EURUSD", 5, sample, per_day, server="fake", terminal_build=0
    )

    out = tmp_path / "EURUSD" / "ticks_monthly"
    files = sorted(p.name for p in out.glob("*.parquet"))
    assert len(files) == 10, files  # five weekdays in each of two weeks
    assert not (tmp_path / "EURUSD" / "ticks").exists(), "the 3c.0 folder must not be touched"

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert [w["start_utc"][:10] for w in manifest["weeks"]] == [
        s.date().isoformat() for s, _ in sample
    ]
    assert len(manifest["ticks_per_day"]) == 14  # every day of both weeks, weekends as 0
    assert manifest["total_ticks"] == 20
    assert "anchor" in manifest["sample_rule"]


class TestStartupGuard:
    """Defence in depth, added after the 2026-11-20 incident: a stale compiled
    copy of the week rule produced eight-day weeks, and the extraction ran on
    it. The extractor now refuses, before connecting to MT5, any sample week
    that is not exactly Sunday 00:00 UTC to the next Sunday 00:00 UTC."""

    @pytest.fixture
    def xt(self, monkeypatch):
        monkeypatch.syspath_prepend(str(REPO))
        import extract_mt5_ticks  # noqa: PLC0415 -- needs REPO on sys.path first

        return extract_mt5_ticks

    def test_the_real_rule_is_accepted(self, xt):
        import tick_sample_weeks  # noqa: PLC0415

        xt.validate_sample_weeks(tick_sample_weeks.sample_weeks((2019, 12), (2026, 10)))

    def test_an_eight_day_week_is_refused(self, xt):
        start = datetime(2026, 4, 5, tzinfo=UTC)
        with pytest.raises(ValueError, match="7 days"):
            xt.validate_sample_weeks([(start, start + timedelta(days=8))])

    def test_a_week_not_starting_on_a_sunday_is_refused(self, xt):
        start = datetime(2026, 4, 6, tzinfo=UTC)  # a Monday
        with pytest.raises(ValueError, match="Sunday"):
            xt.validate_sample_weeks([(start, start + timedelta(days=7))])

    def test_a_week_not_starting_at_midnight_is_refused(self, xt):
        start = datetime(2026, 4, 5, 1, tzinfo=UTC)
        with pytest.raises(ValueError, match="00:00"):
            xt.validate_sample_weeks([(start, start + timedelta(days=7))])

    def test_a_week_not_in_utc_is_refused(self, xt):
        start = datetime(2026, 4, 5, tzinfo=timezone(timedelta(hours=2)))
        with pytest.raises(ValueError, match="UTC"):
            xt.validate_sample_weeks([(start, start + timedelta(days=7))])

    def test_main_refuses_an_eight_day_rule_before_connecting(self, xt, monkeypatch):
        """The incident itself: the rule hands back eight-day weeks. The run
        must stop before MT5 is touched, so nothing is fetched or written."""

        def eight_day_weeks(_first, _last):
            start = datetime(2026, 4, 5, tzinfo=UTC)
            return [(start, start + timedelta(days=8))]

        def must_not_connect():
            raise AssertionError("connected to MT5 despite an invalid sample rule")

        monkeypatch.setattr(xt, "sample_weeks", eight_day_weeks)
        monkeypatch.setattr(xt.mt5, "initialize", must_not_connect)
        monkeypatch.setattr("sys.argv", ["extract_mt5_ticks.py", "--monthly-sample"])
        with pytest.raises(ValueError, match="7 days"):
            xt.main()
