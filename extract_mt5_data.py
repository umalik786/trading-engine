"""
MT5 historical data extraction -- year-by-year, to parquet.

Throwaway tooling, not engine code. Lives in the repo root like
verify_mt5.py and is never imported from src/. It only extracts and stores
raw broker data; building Bar objects from it is ReplayFeed's job.

Why year-by-year: verify_mt5.py found that a single copy_rates_range() call
across the full history returns exactly ~100,000 bars for EURUSD, XAUUSD and
XAGUSD at M5, M15 and H1 alike -- a download cap, not the server's own limit
(indices returned 354,465 in one call). Fetching one calendar year at a time
keeps every request well under that cap for M15/H1/H4, and logs a per-year
count so a truncated year is visible rather than silently swallowed into a
larger, capped total.

No gap filling. Weekends, holidays and index session breaks appear as
missing rows in the output -- that is correct. A missing bar means the
market was shut; inventing one invents a price that was never traded.

TIMEZONE FIX (2026-09-17): the previous version of this script labelled
every MT5 timestamp UTC via datetime.fromtimestamp(t, tz=UTC) without
converting it. MT5 returns (and expects) times in the trade server's own
clock, not UTC -- see spec Appendix A.3/A.6. Both the output (stored "time"
column) and the input (year_bounds request windows) needed converting; see
FTMO_SERVER_UTC_OFFSET below for the correction and why it can't be a plain
IANA zone. docs/state.md's CRITICAL section has the full incident writeup.

Prerequisites:
  - MetaTrader 5 terminal is running and logged in
  - Run with:  uv run --extra mt5 python extract_mt5_data.py [--force]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import MetaTrader5 as mt5
import pyarrow as pa
import pyarrow.parquet as pq

# Internal name -> broker symbol. Verified against a live FTMO account,
# docs/state.md, 2026-09-10. This mapping is the only broker-specific
# knowledge in this script -- everything else (digits, precision) is read
# live from symbol_info() rather than hardcoded, per Appendix A.6.
SYMBOL_MAP = {
    "NAS100": "US100.cash",
    "US500": "US500.cash",
    "EURUSD": "EURUSD",
    "XAUUSD": "XAUUSD",
    "XAGUSD": "XAGUSD",
}

TIMEFRAMES = {
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
}

# Deliberately earlier than any confirmed broker history (docs/state.md's
# earliest verified start is 2017-12-29) so a year with no data is measured
# and logged as zero, rather than the loop's start date silently assuming
# where history begins.
EARLIEST_YEAR = 2005

DATA_ROOT = Path("C:/trading/data/raw")

# --- Server timezone: verified 2026-09-17, spec Appendix A.6 ---------------

_NEW_YORK = ZoneInfo("America/New_York")

SERVER_TZ_VERIFIED_DATE = "2026-09-17"
SERVER_TZ_SOURCE = "https://ftmo.com/en/blog/trading-updates/trading-update-5-mar-2026/"
SERVER_TZ_CONVENTION = (
    "GMT+2 in winter, GMT+3 in summer, transitioning on the United States "
    "daylight-saving calendar rather than the European one. No IANA "
    "timezone matches this combination."
)


def ftmo_server_utc_offset(reference: datetime) -> timedelta:
    """The FTMO MT5 server's offset ahead of UTC at a given moment.

    Verified 2026-09-17 from FTMO's own trading updates (see
    SERVER_TZ_SOURCE): the server clock runs GMT+2 in winter and GMT+3 in
    summer, but switches on the UNITED STATES daylight-saving calendar, not
    the European one -- FTMO states plainly that the platform moves to
    GMT+3 on the US spring-forward date and back to GMT+2 on the US
    fall-back date, leaving a two-to-three week window each spring and
    autumn where the server clock and Europe disagree by two hours rather
    than the usual one.

    This EET-magnitude offset on a US transition calendar corresponds to no
    real IANA timezone: no geographic region observes GMT+2/+3 on a US DST
    schedule, so `zoneinfo` cannot be asked for this zone by name. Instead,
    ask whether America/New_York itself is in daylight time at the
    reference moment, and derive +3 or +2 from that -- the DST calendar
    still comes from zoneinfo's own tz database, just the US entry rather
    than a European one, so a future change to US DST legislation is
    picked up automatically rather than needing a hand-maintained date
    table that would be wrong the first time legislation changed.

    `reference` may be naive (an approximate wall-clock reading -- accurate
    enough to place it on the correct side of a transition, since FTMO
    itself brackets each transition with a multi-hour trading halt rather
    than an instantaneous flip; see the verification notes) or UTC-aware
    (treated exactly).
    """
    if reference.tzinfo is None:
        probe = reference.replace(tzinfo=_NEW_YORK)
    else:
        probe = reference.astimezone(_NEW_YORK)
    is_dst = probe.dst() != timedelta(0)
    return timedelta(hours=3) if is_dst else timedelta(hours=2)


def server_epoch_to_utc(epoch_seconds: int) -> datetime:
    """MT5 epoch seconds -> true UTC.

    MT5 computes its epoch value by treating the server's own wall-clock
    reading as if it were UTC, so a plain UTC epoch conversion recovers the
    server's local digits, not the true instant. Recover those digits as a
    naive reading, then correct with the verified server offset.
    """
    naive_server_reading = datetime.fromtimestamp(epoch_seconds, tz=UTC).replace(tzinfo=None)
    offset = ftmo_server_utc_offset(naive_server_reading)
    return (naive_server_reading - offset).replace(tzinfo=UTC)


def utc_instant_to_mt5_request(instant_utc: datetime) -> datetime:
    """The datetime to hand to copy_rates_range() for a desired true-UTC
    instant.

    MT5 reads only the wall-clock fields of whatever datetime it is given
    and treats them as server-local, ignoring tzinfo entirely -- this is
    exactly how the original bug went unnoticed: passing a UTC-labelled
    datetime was silently honoured as a server-local request. So: compute
    the server-local wall-clock reading for this UTC instant, then
    re-attach a UTC label purely so the object stays a valid tz-aware
    datetime for the API -- the label itself is not read by MT5.
    """
    offset = ftmo_server_utc_offset(instant_utc)
    server_local_reading = (instant_utc + offset).replace(tzinfo=None)
    return server_local_reading.replace(tzinfo=UTC)


# --- Extraction --------------------------------------------------------


@dataclass(frozen=True)
class ExtractionJob:
    internal_name: str
    broker_symbol: str
    timeframe_label: str
    mt5_timeframe: int
    digits: int


def year_bounds_utc(year: int) -> tuple[datetime, datetime]:
    """True-UTC [start, end] as a closed range, one second short of the
    next year, so a bar landing exactly on the year boundary is never
    fetched twice."""
    start = datetime(year, 1, 1, tzinfo=UTC)
    end = datetime(year + 1, 1, 1, tzinfo=UTC) - timedelta(seconds=1)
    return start, end


def price_to_decimal(value: float, digits: int) -> Decimal:
    """Round to the symbol's own precision before converting to Decimal, so
    float noise beyond what the broker actually reports never enters the
    stored value. Convert via str(), never Decimal(float) directly."""
    return Decimal(str(round(float(value), digits)))


def decimal_type_for(digits: int) -> pa.Decimal128Type:
    return pa.decimal128(10 + digits, digits)


def fetch_year(
    broker_symbol: str, mt5_timeframe: int, year: int
) -> list[tuple[datetime, object]] | None:
    """Fetch one true-UTC calendar year of bars, filtered to that year.

    Both sides of the MT5 call are converted: the request window is built
    in true UTC then translated to the server-local reading MT5 expects
    (utc_instant_to_mt5_request), and every returned row's time is
    converted back to true UTC (server_epoch_to_utc) before filtering.

    copy_rates_range() can also return a single bar nearest to the
    requested window instead of an empty result when no real data exists
    inside it (observed: a year decades before a symbol's history starts
    returns the series' very first bar). Filtering to [start, end] turns
    that into a correct zero rather than a borrowed bar misattributed to
    the wrong year.
    """
    utc_start, utc_end = year_bounds_utc(year)
    request_start = utc_instant_to_mt5_request(utc_start)
    request_end = utc_instant_to_mt5_request(utc_end)

    rates = mt5.copy_rates_range(broker_symbol, mt5_timeframe, request_start, request_end)
    if rates is None or len(rates) == 0:
        return None

    converted = [(server_epoch_to_utc(int(r["time"])), r) for r in rates]
    in_range = [(ts, r) for ts, r in converted if utc_start <= ts <= utc_end]
    if not in_range:
        return None
    return in_range


def rates_to_table(converted_rates: list[tuple[datetime, object]], digits: int) -> pa.Table:
    """Store exactly what MT5 returns: bar-open time (already corrected to
    true UTC by the caller), OHLC, tick volume, spread and real volume. No
    derived fields, no gap filling."""
    dtype = decimal_type_for(digits)
    times = [ts for ts, _ in converted_rates]
    rows = [r for _, r in converted_rates]
    return pa.table(
        {
            "time": pa.array(times, type=pa.timestamp("us", tz="UTC")),
            "open": pa.array([price_to_decimal(r["open"], digits) for r in rows], type=dtype),
            "high": pa.array([price_to_decimal(r["high"], digits) for r in rows], type=dtype),
            "low": pa.array([price_to_decimal(r["low"], digits) for r in rows], type=dtype),
            "close": pa.array([price_to_decimal(r["close"], digits) for r in rows], type=dtype),
            "tick_volume": pa.array([int(r["tick_volume"]) for r in rows], type=pa.int64()),
            "spread": pa.array([int(r["spread"]) for r in rows], type=pa.int32()),
            "real_volume": pa.array([int(r["real_volume"]) for r in rows], type=pa.int64()),
        }
    )


def existing_year_bounds(year_path: Path) -> tuple[int, datetime, datetime]:
    table = pq.read_table(year_path, columns=["time"])
    column = table.column("time")
    return table.num_rows, column[0].as_py(), column[-1].as_py()


def extract_job(job: ExtractionJob, force: bool) -> dict:
    out_dir = DATA_ROOT / job.internal_name / job.timeframe_label
    out_dir.mkdir(parents=True, exist_ok=True)

    current_year = datetime.now(UTC).year
    per_year_counts: dict[str, int] = {}
    earliest: datetime | None = None
    latest: datetime | None = None
    total = 0

    for year in range(EARLIEST_YEAR, current_year + 1):
        year_path = out_dir / f"{year}.parquet"

        if year_path.exists() and not force:
            count, y_earliest, y_latest = existing_year_bounds(year_path)
            print(f"    {year}  {count:>7,} bars  (on disk, skipped)")
        else:
            converted_rates = fetch_year(job.broker_symbol, job.mt5_timeframe, year)
            if converted_rates is None:
                # A re-fetch that now correctly finds nothing must not leave
                # a stale file from an earlier (possibly buggy) run behind.
                if year_path.exists():
                    year_path.unlink()
                per_year_counts[str(year)] = 0
                print(f"    {year}  {0:>7,} bars")
                continue
            table = rates_to_table(converted_rates, job.digits)
            pq.write_table(table, year_path)
            count = table.num_rows
            y_earliest = table.column("time")[0].as_py()
            y_latest = table.column("time")[-1].as_py()
            print(f"    {year}  {count:>7,} bars")

        if count > 0:
            earliest = y_earliest if earliest is None else min(earliest, y_earliest)
            latest = y_latest if latest is None else max(latest, y_latest)
        per_year_counts[str(year)] = count
        total += count

    return {
        "internal_name": job.internal_name,
        "broker_symbol": job.broker_symbol,
        "timeframe": job.timeframe_label,
        "digits": job.digits,
        "decimal_precision": 10 + job.digits,
        "decimal_scale": job.digits,
        "total_bars": total,
        "earliest_bar_utc": earliest.isoformat() if earliest else None,
        "latest_bar_utc": latest.isoformat() if latest else None,
        "bars_per_year": per_year_counts,
    }


def write_manifest(out_dir: Path, data: dict, server: str, terminal_build: int) -> None:
    """One manifest per instrument/timeframe, alongside its parquet files.

    Per spec §6.5.6's provenance principle -- a number with no record of
    where it came from can't be checked later. server_timezone records the
    convention this extraction assumed, so a future reader (or a future
    re-verification) can tell what was believed true and when.
    """
    manifest = {
        "internal_name": data["internal_name"],
        "broker_symbol": data["broker_symbol"],
        "timeframe": data["timeframe"],
        "source_server": server,
        "mt5_terminal_build": terminal_build,
        "server_timezone": {
            "convention": SERVER_TZ_CONVENTION,
            "verified": SERVER_TZ_VERIFIED_DATE,
            "source": SERVER_TZ_SOURCE,
        },
        "extracted_at_utc": datetime.now(UTC).isoformat(),
        "earliest_bar_utc": data["earliest_bar_utc"],
        "latest_bar_utc": data["latest_bar_utc"],
        "total_bars": data["total_bars"],
        "bars_per_year": data["bars_per_year"],
        "digits": data["digits"],
        "decimal_precision": data["decimal_precision"],
        "decimal_scale": data["decimal_scale"],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def print_summary_table(results: list[dict]) -> None:
    print("\n" + "=" * 84)
    print("SUMMARY")
    print("=" * 84)
    header = f"{'Instrument':<10} {'TF':<5} {'Bars':>10}  {'Earliest':<20} {'Latest':<20}"
    print(header)
    print("-" * len(header))
    for r in results:
        earliest = r["earliest_bar_utc"][:19] if r["earliest_bar_utc"] else "--"
        latest = r["latest_bar_utc"][:19] if r["latest_bar_utc"] else "--"
        print(
            f"{r['internal_name']:<10} {r['timeframe']:<5} {r['total_bars']:>10,}  "
            f"{earliest:<20} {latest:<20}"
        )
    print("=" * 84)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract MT5 historical bars to parquet, year by year."
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-fetch years already on disk."
    )
    args = parser.parse_args()

    print("=" * 70)
    print("MT5 DATA EXTRACTION -- read only, places no orders")
    print("=" * 70)

    if not mt5.initialize():
        print("\nCould not connect to the terminal:", mt5.last_error())
        print("Check that MT5 is running and logged in, then try again.")
        return

    term = mt5.terminal_info()
    acct = mt5.account_info()
    server = acct.server if acct else "unknown"
    terminal_build = term.build if term else 0
    print(f"\nTerminal build {terminal_build}, server {server}")

    results: list[dict] = []
    for internal_name, broker_symbol in SYMBOL_MAP.items():
        if not mt5.symbol_select(broker_symbol, True):
            print(f"\n{internal_name}: could not select {broker_symbol}: {mt5.last_error()}")
            continue
        info = mt5.symbol_info(broker_symbol)
        if info is None:
            print(f"\n{internal_name}: symbol_info returned None: {mt5.last_error()}")
            continue

        for timeframe_label, mt5_timeframe in TIMEFRAMES.items():
            print(f"\n{internal_name} ({broker_symbol})  {timeframe_label}")
            job = ExtractionJob(
                internal_name=internal_name,
                broker_symbol=broker_symbol,
                timeframe_label=timeframe_label,
                mt5_timeframe=mt5_timeframe,
                digits=info.digits,
            )
            data = extract_job(job, args.force)
            out_dir = DATA_ROOT / internal_name / timeframe_label
            write_manifest(out_dir, data, server, terminal_build)
            results.append(data)

    mt5.shutdown()
    print_summary_table(results)


if __name__ == "__main__":
    main()
