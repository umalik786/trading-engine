"""check_bar_spacing.py: catches bars of the wrong width filed under a
timeframe, month by month.

The history that motivated it (docs/state.md, trial session 2026-11-17):
index "M15" on this venue is daily bars to 2021-01-21, then HOURLY bars to
2021-09-14, then genuine 15-minute bars. A per-year share of correctly
spaced bars put 2021 at 64% -- the hourly tier hid inside the year. The
check therefore asks, for every month, what the COMMONEST gap between
consecutive bars is.

Synthetic series below, timeframe M15, all of 2024 Q1-Q2 compressed into
three tiers: January daily bars, February-March hourly, April genuine.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

REPO = Path(__file__).resolve().parents[2]
M15 = timedelta(minutes=15)
FEB = datetime(2024, 2, 1, tzinfo=UTC)
APR = datetime(2024, 4, 1, tzinfo=UTC)


def _every(start: datetime, end: datetime, step: timedelta) -> list[datetime]:
    out, t = [], start
    while t < end:
        out.append(t)
        t += step
    return out


THREE_TIERS = (
    _every(datetime(2024, 1, 1, 22, tzinfo=UTC), FEB, timedelta(days=1))
    + _every(FEB, APR, timedelta(hours=1))
    + _every(APR, datetime(2024, 5, 1, tzinfo=UTC), M15)
)


@pytest.fixture
def spacing(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO))
    import check_bar_spacing  # noqa: PLC0415 -- needs REPO on sys.path first

    return check_bar_spacing


def _by_month(reports) -> dict:
    return {r.month: r for r in reports}


def test_each_tier_is_reported_with_its_own_commonest_gap(spacing):
    months = _by_month(spacing.monthly_reports(THREE_TIERS, M15, genuine_from=None))
    assert months["2024-01"].commonest_gap == timedelta(days=1)
    assert months["2024-02"].commonest_gap == timedelta(hours=1)
    assert months["2024-03"].commonest_gap == timedelta(hours=1)
    assert months["2024-04"].commonest_gap == M15


def test_with_no_genuine_from_every_wrong_month_is_a_violation(spacing):
    months = _by_month(spacing.monthly_reports(THREE_TIERS, M15, genuine_from=None))
    assert [m for m, r in months.items() if r.status == "VIOLATION"] == [
        "2024-01",
        "2024-02",
        "2024-03",
    ]
    assert months["2024-04"].status == "ok"


def test_genuine_from_at_the_true_start_excludes_the_tiers_and_passes(spacing):
    months = _by_month(spacing.monthly_reports(THREE_TIERS, M15, genuine_from=APR))
    assert [months[m].status for m in ("2024-01", "2024-02", "2024-03")] == ["excluded"] * 3
    assert months["2024-04"].status == "ok"


def test_genuine_from_set_after_the_daily_tier_still_catches_the_hourly_one(spacing):
    """The failure the per-year view missed: a date that clears the daily
    bars but not the hourly ones."""
    months = _by_month(spacing.monthly_reports(THREE_TIERS, M15, genuine_from=FEB))
    assert months["2024-01"].status == "excluded"
    assert months["2024-02"].status == "VIOLATION"
    assert months["2024-03"].status == "VIOLATION"


def test_a_month_straddling_genuine_from_is_judged_on_its_allowed_part(spacing):
    """March 15 onward is genuine here; March 1-14 hourly is excluded. The
    month's commonest gap overall is irrelevant -- only what the engine
    is allowed to read is judged."""
    times = _every(FEB, datetime(2024, 3, 15, tzinfo=UTC), timedelta(hours=1)) + _every(
        datetime(2024, 3, 15, tzinfo=UTC), APR, M15
    )
    months = _by_month(
        spacing.monthly_reports(times, M15, genuine_from=datetime(2024, 3, 15, tzinfo=UTC))
    )
    assert months["2024-03"].status == "mixed"


def _write_series(root: Path, instrument: str, timeframe: str, times: list[datetime]) -> None:
    out = root / instrument / timeframe
    out.mkdir(parents=True)
    pq.write_table(
        pa.table({"time": pa.array(times, type=pa.timestamp("us", tz="UTC"))}),
        out / "2024.parquet",
    )


def _write_config(path: Path, genuine_from: str | None) -> Path:
    block = f'    bars_genuine_from:\n      M15: "{genuine_from}"\n' if genuine_from else ""
    path.write_text(
        f'instruments:\n  NAS100:\n    contract_size: 1\n    point: "0.01"\n{block}',
        encoding="utf-8",
    )
    return path


def test_the_command_inspects_m1(spacing, tmp_path):
    """Hourly bars filed under M1, as the index history has, must be caught."""
    hourly = _every(FEB, APR, timedelta(hours=1))
    _write_series(tmp_path / "data", "NAS100", "M1", hourly)
    config = _write_config(tmp_path / "instruments.yaml", None)
    assert spacing.main(["--data-root", str(tmp_path / "data"), "--config", str(config)]) == 1


def test_the_command_fails_without_the_config_date(spacing, tmp_path):
    _write_series(tmp_path / "data", "NAS100", "M15", THREE_TIERS)
    config = _write_config(tmp_path / "instruments.yaml", None)
    assert spacing.main(["--data-root", str(tmp_path / "data"), "--config", str(config)]) == 1


def test_the_command_passes_with_the_right_config_date(spacing, tmp_path):
    _write_series(tmp_path / "data", "NAS100", "M15", THREE_TIERS)
    config = _write_config(tmp_path / "instruments.yaml", "2024-04-01T00:00:00Z")
    assert spacing.main(["--data-root", str(tmp_path / "data"), "--config", str(config)]) == 0
