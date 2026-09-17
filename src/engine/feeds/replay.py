"""ReplayFeed: reads historical bars from the parquet files written by
extract_mt5_data.py. See docs/trading-engine-architecture.md §2.2 (Feed
protocol) and Appendix B.6 (no gap-filling for stored data).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq

from engine.core.types import Bar, require_utc

DEFAULT_DATA_ROOT = Path("C:/trading/data/raw")

# Bar duration per timeframe, used to derive ts_close from the bar-open time
# parquet stores (extract_mt5_data.py stores MT5's own "time" field, which is
# bar-open). ASSUMPTION: every bar in a given timeframe's series spans
# exactly this fixed duration, so ts_close = ts_open + duration. True for
# M15/H1/H4 on this venue. A wrong duration here would silently shift every
# ts_close by one bar width -- there is no independent check against it,
# since the parquet files carry no ts_close of their own.
TIMEFRAME_DURATIONS = {
    "M15": timedelta(minutes=15),
    "H1": timedelta(hours=1),
    "H4": timedelta(hours=4),
}

# Safety bound for warmup()'s backward search through year files. Not a data
# assumption -- just where the search gives up and raises rather than
# looping forever if a symbol's directory is empty or missing entirely.
_EARLIEST_POSSIBLE_YEAR = 2000


class ReplayFeed:
    """Feed protocol implementation (§2.2) over historical parquet bars.

    Reads only the year files touched by [range_start, range_end) -- a
    multi-year backtest does not load data outside its own window.
    """

    def __init__(
        self,
        instrument: str,
        timeframe: str,
        range_start: datetime,
        range_end: datetime,
        data_root: Path = DEFAULT_DATA_ROOT,
    ) -> None:
        require_utc("range_start", range_start)
        require_utc("range_end", range_end)
        if range_end <= range_start:
            raise ValueError(
                f"range_end ({range_end!r}) must be after range_start ({range_start!r})"
            )
        if timeframe not in TIMEFRAME_DURATIONS:
            raise ValueError(
                f"unknown timeframe {timeframe!r}, expected one of "
                f"{sorted(TIMEFRAME_DURATIONS)}"
            )

        self.instrument = instrument
        self.timeframe = timeframe
        self.range_start = range_start
        self.range_end = range_end
        self._bar_duration = TIMEFRAME_DURATIONS[timeframe]
        self._dir = data_root / instrument / timeframe

    def _year_file(self, year: int) -> Path:
        return self._dir / f"{year}.parquet"

    def _row_to_bar(self, row: dict) -> Bar:
        ts_open = row["time"]
        return Bar(
            symbol=self.instrument,
            ts_open=ts_open,
            ts_close=ts_open + self._bar_duration,
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=Decimal(row["tick_volume"]),
            is_final=True,
        )

    def _bars_in_range(self, start: datetime, end: datetime) -> list[Bar]:
        """Bars with ts_open in [start, end), reading only years touched."""
        bars: list[Bar] = []
        for year in range(start.year, end.year + 1):
            path = self._year_file(year)
            if not path.exists():
                continue
            table = pq.read_table(path)
            for row in table.to_pylist():
                ts_open = row["time"]
                if start <= ts_open < end:
                    bars.append(self._row_to_bar(row))
        bars.sort(key=lambda b: b.ts_close)
        return bars

    def stream(self) -> Iterator[Bar]:
        """Yield final bars in [range_start, range_end), strictly ascending
        by ts_close. See §2.2 -- never yields a bar whose ts_close is in the
        future; on historical data this should be structurally impossible,
        so it is asserted rather than assumed.
        """
        now = datetime.now(UTC)
        previous_ts_close: datetime | None = None
        for bar in self._bars_in_range(self.range_start, self.range_end):
            if previous_ts_close is not None and bar.ts_close <= previous_ts_close:
                raise ValueError(
                    f"non-increasing ts_close in stored data for {self.instrument} "
                    f"{self.timeframe}: {bar.ts_close!r} at or before {previous_ts_close!r}"
                )
            assert bar.ts_close <= now, (
                f"ReplayFeed yielded a future bar: {bar.ts_close!r} > now ({now!r})"
            )
            previous_ts_close = bar.ts_close
            yield bar

    def warmup(self, n: int) -> list[Bar]:
        """The n bars immediately before range_start, for feature warmup
        only -- never passed to a strategy. Raises if fewer than n exist
        rather than returning a short list: a silently half-warmed feature
        is a bug that surfaces as bad results, not as an error.
        """
        if n <= 0:
            raise ValueError(f"n must be a positive number of bars, got {n}")

        collected: list[Bar] = []
        year = self.range_start.year
        while len(collected) < n and year >= _EARLIEST_POSSIBLE_YEAR:
            path = self._year_file(year)
            if path.exists():
                table = pq.read_table(path)
                year_bars = [
                    self._row_to_bar(row)
                    for row in table.to_pylist()
                    if row["time"] < self.range_start
                ]
                collected = year_bars + collected
            year -= 1

        if len(collected) < n:
            raise ValueError(
                f"requested {n} warmup bars for {self.instrument} {self.timeframe} "
                f"before {self.range_start.isoformat()}, but only {len(collected)} "
                "exist on disk"
            )

        collected.sort(key=lambda b: b.ts_close)
        return collected[-n:]
