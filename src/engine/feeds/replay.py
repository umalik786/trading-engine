"""ReplayFeed: reads historical bars from the parquet files written by
extract_mt5_data.py. See docs/trading-engine-architecture.md §2.2 (Feed
protocol) and Appendix B.6 (no gap-filling for stored data).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq

from engine.core.provenance import DEFAULT_STALE_AFTER_DAYS, warn_if_unverified_or_stale
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

# Row-group batch size for stream()'s parquet reads. Bounds peak memory to
# roughly this many in-flight rows regardless of year-file size or how many
# years the requested range spans. Not tuned beyond "clearly smaller than a
# year's worth of M15 bars (~35,000) and clearly bigger than per-batch
# overhead would make worthwhile."
_STREAM_BATCH_SIZE = 4096


class ReplayFeed:
    """Feed protocol implementation (§2.2) over historical parquet bars.

    Reads only the year files touched by [range_start, range_end) -- a
    multi-year backtest does not load data outside its own window.
    """

    def __init__(  # noqa: PLR0913, PLR0917 -- two optional, sensibly-defaulted overrides
        self,
        instrument: str,
        timeframe: str,
        range_start: datetime,
        range_end: datetime,
        data_root: Path = DEFAULT_DATA_ROOT,
        stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
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
        self._check_server_timezone_provenance(stale_after_days)

    def _check_server_timezone_provenance(self, stale_after_days: int) -> None:
        """Warn per §6.5.6 if the extraction manifest's server_timezone
        claim is missing, incomplete, or stale.

        Silently skipped if no manifest.json is present at all. A real
        extraction via extract_mt5_data.py always writes one; its absence
        here means a synthetic test fixture, not genuine extracted data, so
        there is nothing to verify against.
        """
        manifest_path = self._dir / "manifest.json"
        if not manifest_path.exists():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        server_timezone = manifest.get("server_timezone") or {}
        verified_str = server_timezone.get("verified")
        verified = date.fromisoformat(verified_str) if verified_str else None
        warn_if_unverified_or_stale(
            subject=f"{self.instrument} {self.timeframe} server timezone",
            verified=verified,
            source=server_timezone.get("source"),
            stale_after_days=stale_after_days,
            stacklevel=4,
        )

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

    def stream(self) -> Iterator[Bar]:
        """Yield final bars in [range_start, range_end), strictly ascending
        by ts_close. See §2.2 -- never yields a bar whose ts_close is in the
        future; on historical data this should be structurally impossible,
        so it is asserted rather than assumed.

        Reads one row-group batch at a time via `ParquetFile.iter_batches()`
        rather than materialising a full table, so peak memory is bounded by
        batch size, not by how much history the requested range spans -- a
        21-year stream costs roughly the same peak memory as a 1-year one.

        No explicit sort. Rows within a year file are already time-ordered
        (by MT5 and by extract_mt5_data.py), and year files are opened in
        ascending order here, so output is already ascending by
        construction -- sorting an already-sorted sequence would only cost
        memory and time for no benefit. The inline monotonicity check below
        still verifies this on every bar rather than trusting it silently,
        and if it's ever violated it raises rather than re-sorting: §2.2
        states strictly ascending as a contract, not a best effort, and a
        feed that quietly reorders a malformed file hides a data defect
        instead of surfacing it.
        """
        now = datetime.now(UTC)
        previous_ts_close: datetime | None = None

        for year in range(self.range_start.year, self.range_end.year + 1):
            path = self._year_file(year)
            if not path.exists():
                continue
            parquet_file = pq.ParquetFile(path)
            for batch in parquet_file.iter_batches(batch_size=_STREAM_BATCH_SIZE):
                for row in batch.to_pylist():
                    ts_open = row["time"]
                    if not (self.range_start <= ts_open < self.range_end):
                        continue
                    bar = self._row_to_bar(row)
                    if previous_ts_close is not None and bar.ts_close <= previous_ts_close:
                        raise ValueError(
                            f"non-increasing ts_close in stored data for "
                            f"{self.instrument} {self.timeframe}: {bar.ts_close!r} "
                            f"at or before {previous_ts_close!r}"
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
