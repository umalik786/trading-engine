"""check_dst_boundaries.py must be able to fail, for the right reasons.

A check that has never failed may be checking nothing. This builds synthetic
MT5-shaped EURUSD M15 bars for the three Fridays the check inspects, runs
them through extract_mt5_data.py's REAL conversion code, and runs the REAL
check script against the result as a subprocess:

  correct     -- the server clock as shipped (America/New_York DST calendar)
  european    -- identical code, only the DST calendar swapped to Europe
  unconverted -- server time labelled UTC unconverted, the 2026-09-17 bug
  missing     -- no data at all

Input premise, not under test: FTMO's server week closes at its own
midnight (the reason for its +2/+3 choice, spec Appendix A.6), so the
synthetic Friday runs 00:00-23:45 on the server clock.

What this proves: the check tells the US calendar from the European one,
and catches a missing conversion and missing data. What it does not prove:
that real extracted data is right -- only running the check on it does.

Marked requires_mt5 because extract_mt5_data imports MetaTrader5. It needs
the package, not a running terminal. Run with:
    uv run --extra mt5 pytest -m requires_mt5
"""

from __future__ import annotations

import calendar
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("MetaTrader5")

import pyarrow.parquet as pq

from engine.core.clock import DstSwitchedServerClock

pytestmark = pytest.mark.requires_mt5

REPO = Path(__file__).resolve().parents[2]
FRIDAYS = [(2025, 1, 17), (2025, 3, 14), (2025, 10, 31)]
BARS_PER_DAY = 96


@pytest.fixture
def extractor(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO))
    import extract_mt5_data  # noqa: PLC0415 -- needs REPO on sys.path first

    return extract_mt5_data


def _synthetic_rows() -> list[dict]:
    rows = []
    for y, m, d in FRIDAYS:
        server_midnight = datetime(y, m, d)  # noqa: DTZ001 -- a server wall-clock reading
        for i in range(BARS_PER_DAY):
            reading = server_midnight + timedelta(minutes=15 * i)
            rows.append(
                {
                    "time": calendar.timegm(reading.timetuple()),  # MT5's epoch convention
                    "open": 1.1,
                    "high": 1.1,
                    "low": 1.1,
                    "close": 1.1,
                    "tick_volume": 1,
                    "spread": 1,
                    "real_volume": 0,
                }
            )
    return rows


def _write(root: Path, extractor, convert) -> Path:
    out = root / "EURUSD" / "M15"
    out.mkdir(parents=True)
    converted = [(convert(int(r["time"])), r) for r in _synthetic_rows()]
    pq.write_table(extractor.rates_to_table(converted, 5), out / "2025.parquet")
    return root


def _run_check(data_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "check_dst_boundaries.py"), "--data-root", str(data_root)],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )


def test_correct_conversion_passes(tmp_path, extractor):
    root = _write(tmp_path, extractor, extractor.server_epoch_to_utc)
    result = _run_check(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS  Fri 17 Jan 2025: last bar closes 22:00 UTC" in result.stdout
    assert "PASS  Fri 14 Mar 2025: last bar closes 21:00 UTC" in result.stdout
    assert "PASS  Fri 31 Oct 2025: last bar closes 21:00 UTC" in result.stdout


def test_european_calendar_fails_only_in_divergence_weeks(tmp_path, extractor, monkeypatch):
    monkeypatch.setattr(
        extractor,
        "FTMO_SERVER_CLOCK",
        DstSwitchedServerClock(
            winter_offset=timedelta(hours=2),
            summer_offset=timedelta(hours=3),
            dst_calendar="Europe/Prague",
        ),
    )
    root = _write(tmp_path, extractor, extractor.server_epoch_to_utc)
    result = _run_check(root)
    assert result.returncode == 1
    assert "PASS  Fri 17 Jan 2025: last bar closes 22:00 UTC" in result.stdout
    assert (
        "FAIL  Fri 14 Mar 2025: last bar closes Fri 22:00 UTC, expected Fri 21:00 UTC"
        in result.stdout
    )
    assert (
        "FAIL  Fri 31 Oct 2025: last bar closes Fri 22:00 UTC, expected Fri 21:00 UTC"
        in result.stdout
    )


def test_unconverted_server_time_fails_every_date(tmp_path, extractor):
    root = _write(tmp_path, extractor, lambda t: datetime.fromtimestamp(t, tz=UTC))
    result = _run_check(root)
    assert result.returncode == 1
    assert result.stdout.count("last bar closes Sat 00:00 UTC") == len(FRIDAYS)


def test_missing_data_fails_rather_than_skips(tmp_path):
    result = _run_check(tmp_path)
    assert result.returncode == 1
    assert result.stdout.count("no bars stored for this date") == len(FRIDAYS)
