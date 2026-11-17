"""extract_mt5_data.py must not store a bar that has not finished.

MT5 returns the bar still forming at the moment of the request, with a
partial high, low and close. Found in the 2026-11-17 trial session: the
last bar of every 2026 file was one that never finished.

The clock is frozen at 06:30:00 UTC on Tue 17 Nov 2026 (US winter, server
+2). Fake MT5 returns three M15 bars:

  opens 06:00, closes 06:15  -- finished: kept
  opens 06:15, closes 06:30  -- closes exactly at the cutoff: kept
  opens 06:30, closes 06:45  -- still forming: dropped

Marked requires_mt5 because extract_mt5_data imports MetaTrader5. Needs the
package, not a terminal. Run with:  uv run --extra mt5 pytest -m requires_mt5
"""

from __future__ import annotations

import calendar
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("MetaTrader5")

import pyarrow.parquet as pq

pytestmark = pytest.mark.requires_mt5

REPO = Path(__file__).resolve().parents[2]
FROZEN_NOW = datetime(2026, 11, 17, 6, 30, tzinfo=UTC)
SERVER_OFFSET = timedelta(hours=2)  # US winter on the FTMO server clock
BAR_OPENS_UTC = [
    datetime(2026, 11, 17, 6, 0, tzinfo=UTC),
    datetime(2026, 11, 17, 6, 15, tzinfo=UTC),
    datetime(2026, 11, 17, 6, 30, tzinfo=UTC),
]


def _fake_rate(open_utc: datetime) -> dict:
    server_reading = (open_utc + SERVER_OFFSET).replace(tzinfo=None)
    return {
        "time": calendar.timegm(server_reading.timetuple()),  # MT5's epoch convention
        "open": 1.1,
        "high": 1.1,
        "low": 1.1,
        "close": 1.1,
        "tick_volume": 1,
        "spread": 1,
        "real_volume": 0,
    }


@pytest.fixture
def run_job(tmp_path, monkeypatch):
    """Run one EURUSD M15 extraction job against fake MT5 at FROZEN_NOW."""
    monkeypatch.syspath_prepend(str(REPO))
    import extract_mt5_data as ex  # noqa: PLC0415 -- needs REPO on sys.path first

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_NOW.astimezone(tz) if tz else FROZEN_NOW.replace(tzinfo=None)

    def fake_copy_rates_range(_symbol, _timeframe, start, _end):
        return [_fake_rate(t) for t in BAR_OPENS_UTC] if start.year == 2026 else None

    monkeypatch.setattr(ex, "datetime", FrozenDatetime)
    monkeypatch.setattr(ex, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(ex.mt5, "copy_rates_range", fake_copy_rates_range)

    job = ex.ExtractionJob(
        internal_name="EURUSD",
        broker_symbol="EURUSD",
        timeframe_label="M15",
        mt5_timeframe=ex.mt5.TIMEFRAME_M15,
        digits=5,
    )
    data = ex.extract_job(job, force=True)
    out_dir = tmp_path / "EURUSD" / "M15"
    ex.write_manifest(out_dir, data, server="fake", terminal_build=0)
    stored = pq.read_table(out_dir / "2026.parquet").column("time").to_pylist()
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    return stored, manifest


def test_finished_bars_are_kept_and_the_forming_bar_is_dropped(run_job):
    stored, _ = run_job
    assert BAR_OPENS_UTC[0] in stored, "a finished bar was dropped"
    assert BAR_OPENS_UTC[1] in stored, "the bar closing exactly at the cutoff was dropped"
    assert BAR_OPENS_UTC[2] not in stored, "the bar still forming at the cutoff was stored"
    assert len(stored) == 2


def test_the_manifest_records_where_the_data_is_complete_through(run_job):
    _, manifest = run_job
    assert manifest["complete_through_utc"] == FROZEN_NOW.isoformat()
