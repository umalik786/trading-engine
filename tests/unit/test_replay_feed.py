"""Tests for ReplayFeed. See docs/trading-engine-architecture.md §2.2 and
Appendix B.6 (no gap-filling for stored data)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from engine.feeds.replay import ReplayFeed

_DECIMAL_TYPE = pa.decimal128(15, 5)


def _write_year(root: Path, instrument: str, timeframe: str, year: int, rows: list[dict]) -> None:
    out_dir = root / instrument / timeframe
    out_dir.mkdir(parents=True, exist_ok=True)
    table = pa.table(
        {
            "time": pa.array([r["time"] for r in rows], type=pa.timestamp("us", tz="UTC")),
            "open": pa.array([r["open"] for r in rows], type=_DECIMAL_TYPE),
            "high": pa.array([r["high"] for r in rows], type=_DECIMAL_TYPE),
            "low": pa.array([r["low"] for r in rows], type=_DECIMAL_TYPE),
            "close": pa.array([r["close"] for r in rows], type=_DECIMAL_TYPE),
            "tick_volume": pa.array([r["tick_volume"] for r in rows], type=pa.int64()),
            "spread": pa.array([1] * len(rows), type=pa.int32()),
            "real_volume": pa.array([0] * len(rows), type=pa.int64()),
        }
    )
    pq.write_table(table, out_dir / f"{year}.parquet")


def _row(ts_open: datetime, price: str, volume: int = 100) -> dict:
    p = Decimal(price)
    return {
        "time": ts_open,
        "open": p,
        "high": p + Decimal("0.0001"),
        "low": p - Decimal("0.0001"),
        "close": p,
        "tick_volume": volume,
    }


def _m15_series(start: datetime, count: int, start_price: str = "1.1000") -> list[dict]:
    price = Decimal(start_price)
    rows = []
    ts = start
    for i in range(count):
        rows.append(_row(ts, str(price + Decimal("0.0001") * i)))
        ts = ts + timedelta(minutes=15)
    return rows


class TestOrderingAndDeterminism:
    def test_bars_come_out_strictly_ascending(self, tmp_path: Path) -> None:
        rows = _m15_series(datetime(2024, 1, 2, 0, 0, tzinfo=UTC), 20)
        _write_year(tmp_path, "EURUSD", "M15", 2024, rows)

        feed = ReplayFeed(
            instrument="EURUSD",
            timeframe="M15",
            range_start=datetime(2024, 1, 1, tzinfo=UTC),
            range_end=datetime(2024, 1, 3, tzinfo=UTC),
            data_root=tmp_path,
        )
        bars = list(feed.stream())

        assert len(bars) == 20
        for earlier, later in pairwise(bars):
            assert later.ts_close > earlier.ts_close

    def test_same_range_replayed_twice_is_identical(self, tmp_path: Path) -> None:
        rows = _m15_series(datetime(2024, 1, 2, 0, 0, tzinfo=UTC), 20)
        _write_year(tmp_path, "EURUSD", "M15", 2024, rows)

        feed = ReplayFeed(
            instrument="EURUSD",
            timeframe="M15",
            range_start=datetime(2024, 1, 1, tzinfo=UTC),
            range_end=datetime(2024, 1, 3, tzinfo=UTC),
            data_root=tmp_path,
        )

        first_pass = list(feed.stream())
        second_pass = list(feed.stream())

        assert first_pass == second_pass
        assert first_pass is not second_pass


class TestGapsStayGaps:
    def test_weekend_gap_yields_a_jump_not_filler(self, tmp_path: Path) -> None:
        bar_duration = timedelta(minutes=15)
        friday_close = datetime(2024, 1, 5, 21, 45, tzinfo=UTC)
        monday_open = datetime(2024, 1, 8, 0, 0, tzinfo=UTC)  # gap of ~2.1 days

        rows = _m15_series(datetime(2024, 1, 5, 20, 0, tzinfo=UTC), 8)  # Friday session
        assert rows[-1]["time"] == friday_close
        rows += _m15_series(monday_open, 4, start_price="1.2000")  # Monday session

        _write_year(tmp_path, "EURUSD", "M15", 2024, rows)

        feed = ReplayFeed(
            instrument="EURUSD",
            timeframe="M15",
            range_start=datetime(2024, 1, 1, tzinfo=UTC),
            range_end=datetime(2024, 1, 9, tzinfo=UTC),
            data_root=tmp_path,
        )
        bars = list(feed.stream())

        # No filler was inserted -- exactly the 12 written bars come out.
        assert len(bars) == 12

        gaps = [later.ts_close - earlier.ts_close for earlier, later in pairwise(bars)]
        weekend_gap = gaps[7]  # between the 8th (Friday) and 9th (Monday) bar
        other_gaps = gaps[:7] + gaps[8:]

        assert weekend_gap > bar_duration
        assert weekend_gap == monday_open - friday_close
        assert all(gap == bar_duration for gap in other_gaps)


class TestWarmup:
    def test_warmup_returns_bars_strictly_before_start(self, tmp_path: Path) -> None:
        rows = _m15_series(datetime(2024, 1, 2, 0, 0, tzinfo=UTC), 40)
        _write_year(tmp_path, "EURUSD", "M15", 2024, rows)

        range_start = datetime(2024, 1, 2, 5, 0, tzinfo=UTC)  # the 20th bar's open
        feed = ReplayFeed(
            instrument="EURUSD",
            timeframe="M15",
            range_start=range_start,
            range_end=datetime(2024, 1, 3, tzinfo=UTC),
            data_root=tmp_path,
        )

        warmup_bars = feed.warmup(10)

        assert len(warmup_bars) == 10
        assert all(bar.ts_open < range_start for bar in warmup_bars)
        for earlier, later in pairwise(warmup_bars):
            assert later.ts_close > earlier.ts_close
        # immediately before range_start -- no gap to the run's first bar
        assert warmup_bars[-1].ts_close == range_start

    def test_warmup_raises_when_not_enough_bars_exist(self, tmp_path: Path) -> None:
        rows = _m15_series(datetime(2024, 1, 2, 0, 0, tzinfo=UTC), 5)
        _write_year(tmp_path, "EURUSD", "M15", 2024, rows)

        feed = ReplayFeed(
            instrument="EURUSD",
            timeframe="M15",
            range_start=datetime(2024, 1, 2, 1, 0, tzinfo=UTC),
            range_end=datetime(2024, 1, 3, tzinfo=UTC),
            data_root=tmp_path,
        )

        with pytest.raises(ValueError, match="only"):
            feed.warmup(100)

    def test_warmup_reaches_back_into_an_earlier_year_file(self, tmp_path: Path) -> None:
        rows_2023 = _m15_series(datetime(2023, 12, 31, 21, 0, tzinfo=UTC), 8)
        rows_2024 = _m15_series(datetime(2024, 1, 1, 1, 0, tzinfo=UTC), 4)
        _write_year(tmp_path, "EURUSD", "M15", 2023, rows_2023)
        _write_year(tmp_path, "EURUSD", "M15", 2024, rows_2024)

        feed = ReplayFeed(
            instrument="EURUSD",
            timeframe="M15",
            range_start=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
            range_end=datetime(2024, 1, 2, tzinfo=UTC),
            data_root=tmp_path,
        )

        warmup_bars = feed.warmup(6)

        assert len(warmup_bars) == 6
        # 8 bars written in 2023, from 21:00; the 6 immediately before
        # range_start are the last 6 of those, starting at 21:30.
        assert warmup_bars[0].ts_open == datetime(2023, 12, 31, 21, 30, tzinfo=UTC)
        assert warmup_bars[-1].ts_open == datetime(2023, 12, 31, 22, 45, tzinfo=UTC)


class TestBarShape:
    def test_is_final_is_always_true(self, tmp_path: Path) -> None:
        rows = _m15_series(datetime(2024, 1, 1, 23, 0, tzinfo=UTC), 14)
        _write_year(tmp_path, "EURUSD", "M15", 2024, rows)

        feed = ReplayFeed(
            instrument="EURUSD",
            timeframe="M15",
            range_start=datetime(2024, 1, 2, 0, 0, tzinfo=UTC),
            range_end=datetime(2024, 1, 3, tzinfo=UTC),
            data_root=tmp_path,
        )

        stream_bars = list(feed.stream())
        warmup_bars = feed.warmup(3)

        assert all(bar.is_final is True for bar in stream_bars)
        assert all(bar.is_final is True for bar in warmup_bars)

    def test_prices_are_decimal(self, tmp_path: Path) -> None:
        rows = _m15_series(datetime(2024, 1, 2, 0, 0, tzinfo=UTC), 5)
        _write_year(tmp_path, "EURUSD", "M15", 2024, rows)

        feed = ReplayFeed(
            instrument="EURUSD",
            timeframe="M15",
            range_start=datetime(2024, 1, 1, tzinfo=UTC),
            range_end=datetime(2024, 1, 3, tzinfo=UTC),
            data_root=tmp_path,
        )

        for bar in feed.stream():
            assert isinstance(bar.open, Decimal)
            assert isinstance(bar.high, Decimal)
            assert isinstance(bar.low, Decimal)
            assert isinstance(bar.close, Decimal)
            assert isinstance(bar.volume, Decimal)


class TestReadsOnlyTouchedYears:
    def test_a_year_outside_the_range_is_never_read(self, tmp_path: Path) -> None:
        rows_2024 = _m15_series(datetime(2024, 1, 2, 0, 0, tzinfo=UTC), 5)
        # A "poison" bar in 2099 that would corrupt results if ever read.
        rows_2099 = _m15_series(datetime(2099, 1, 2, 0, 0, tzinfo=UTC), 5, start_price="999.0000")
        _write_year(tmp_path, "EURUSD", "M15", 2024, rows_2024)
        _write_year(tmp_path, "EURUSD", "M15", 2099, rows_2099)

        feed = ReplayFeed(
            instrument="EURUSD",
            timeframe="M15",
            range_start=datetime(2024, 1, 1, tzinfo=UTC),
            range_end=datetime(2024, 1, 3, tzinfo=UTC),
            data_root=tmp_path,
        )

        bars = list(feed.stream())

        assert len(bars) == 5
        assert all(bar.open < Decimal("2.0") for bar in bars)


class TestConstructorValidation:
    def test_naive_range_start_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            ReplayFeed(
                instrument="EURUSD",
                timeframe="M15",
                range_start=datetime(2024, 1, 1),  # noqa: DTZ001 -- naivety is what's under test
                range_end=datetime(2024, 1, 3, tzinfo=UTC),
                data_root=tmp_path,
            )

    def test_unknown_timeframe_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="timeframe"):
            ReplayFeed(
                instrument="EURUSD",
                timeframe="M5",
                range_start=datetime(2024, 1, 1, tzinfo=UTC),
                range_end=datetime(2024, 1, 3, tzinfo=UTC),
                data_root=tmp_path,
            )
