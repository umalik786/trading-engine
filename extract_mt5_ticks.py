"""
MT5 tick-sample extraction -- day by day, to parquet.

Throwaway tooling, not engine code, like extract_mt5_data.py beside it.
Read only: places no orders.

WHY A SAMPLE. Spec Appendix C.1 asks for an empirical spread distribution
per instrument per hour of day, with explicit attention to the daily
rollover and scheduled data releases. The per-bar spread column holds one
spread figure per bar, which can miss a widening that lasts a few minutes. Ticks
(every individual bid/ask quote) carry the spread at every moment. A few
weeks is enough to see the rollover and release behaviour; the full history
is not needed for that and would be very large.

THE WINDOW. Default 2026-10-19 to 2026-11-14 (four weeks, UTC). It contains
twenty daily rollovers, the late-October weeks where the US and European
daylight-saving calendars disagree, and should contain a US non-farm
payrolls release -- confirm the date on the BLS release calendar before
running, and pass --start/--end to move the window if needed.

TIME CONVERSION. Identical to the bars: the request window is built in true
UTC and translated with extract_mt5_data.utc_instant_to_mt5_request, and
every tick's server timestamp goes back through
extract_mt5_data.server_epoch_to_utc. Imported, not copied, so there is one
definition of the server clock. Ticks carry milliseconds (time_msc); the
whole seconds are converted and the milliseconds added back.

Each UTC day is requested with a minute of overlap either side and then
filtered to exactly [day 00:00, next day 00:00) UTC after conversion, so no
tick is lost at a day edge and none is stored twice, whatever MT5 does with
the edges of a request.

Output: C:/trading/data/raw/<INSTRUMENT>/ticks/<YYYY-MM-DD>.parquet, one file
per UTC day, plus manifest.json. Days with no ticks (weekends) are logged
as zero and write no file.

Prerequisites:
  - MetaTrader 5 terminal is running and logged in
  - Run with:  uv run --extra mt5 python extract_mt5_ticks.py
    Options: --start YYYY-MM-DD, --end YYYY-MM-DD (exclusive), --force
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import MetaTrader5 as mt5
import pyarrow as pa
import pyarrow.parquet as pq

from extract_mt5_data import (
    DATA_ROOT,
    SERVER_TZ_CONVENTION,
    SERVER_TZ_SOURCE,
    SERVER_TZ_VERIFIED_DATE,
    SYMBOL_MAP,
    decimal_type_for,
    price_to_decimal,
    server_epoch_to_utc,
    utc_instant_to_mt5_request,
)

DEFAULT_START = date(2026, 10, 19)
DEFAULT_END = date(2026, 11, 14)  # exclusive

# A minute either side of each day's request, filtered away afterwards.
REQUEST_MARGIN = timedelta(minutes=1)

# volume_real is a quantity, so Decimal by project convention. Eight places
# is finer than any lot step on these instruments.
VOLUME_REAL_TYPE = pa.decimal128(20, 8)


def tick_time_to_utc(time_msc: int) -> datetime:
    """Server-clock milliseconds -> true UTC, via the bars' own converter."""
    whole_seconds, millis = divmod(int(time_msc), 1000)
    return server_epoch_to_utc(whole_seconds) + timedelta(milliseconds=millis)


def fetch_day(broker_symbol: str, day: date) -> list[tuple[datetime, object]]:
    utc_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    utc_end = utc_start + timedelta(days=1)
    ticks = mt5.copy_ticks_range(
        broker_symbol,
        utc_instant_to_mt5_request(utc_start - REQUEST_MARGIN),
        utc_instant_to_mt5_request(utc_end + REQUEST_MARGIN),
        mt5.COPY_TICKS_ALL,
    )
    if ticks is None:
        raise RuntimeError(f"copy_ticks_range failed for {broker_symbol} {day}: {mt5.last_error()}")
    converted = [(tick_time_to_utc(t["time_msc"]), t) for t in ticks]
    return [(ts, t) for ts, t in converted if utc_start <= ts < utc_end]


def ticks_to_table(converted: list[tuple[datetime, object]], digits: int) -> pa.Table:
    """Store what MT5 returns, time corrected to true UTC. No derived
    fields: the spread is ask - bid and is left to whoever reads this."""
    dtype = decimal_type_for(digits)
    rows = [t for _, t in converted]
    return pa.table(
        {
            "time": pa.array([ts for ts, _ in converted], type=pa.timestamp("us", tz="UTC")),
            "bid": pa.array([price_to_decimal(t["bid"], digits) for t in rows], type=dtype),
            "ask": pa.array([price_to_decimal(t["ask"], digits) for t in rows], type=dtype),
            "last": pa.array([price_to_decimal(t["last"], digits) for t in rows], type=dtype),
            "volume": pa.array([int(t["volume"]) for t in rows], type=pa.int64()),
            "volume_real": pa.array(
                [Decimal(str(round(float(t["volume_real"]), 8))) for t in rows],
                type=VOLUME_REAL_TYPE,
            ),
            "flags": pa.array([int(t["flags"]) for t in rows], type=pa.int32()),
        }
    )


def extract_instrument(  # noqa: PLR0913, PLR0917
    internal_name: str, broker_symbol: str, digits: int, start: date, end: date, force: bool
) -> dict[str, int]:
    out_dir = DATA_ROOT / internal_name / "ticks"
    out_dir.mkdir(parents=True, exist_ok=True)
    per_day: dict[str, int] = {}

    day = start
    while day < end:
        path = out_dir / f"{day.isoformat()}.parquet"
        if path.exists() and not force:
            count = pq.ParquetFile(path).metadata.num_rows
            print(f"    {day}  {count:>9,} ticks  (on disk, skipped)")
        else:
            converted = fetch_day(broker_symbol, day)
            count = len(converted)
            if count:
                pq.write_table(ticks_to_table(converted, digits), path)
            elif path.exists():
                path.unlink()
            print(f"    {day} {day:%a}  {count:>9,} ticks")
        per_day[day.isoformat()] = count
        day += timedelta(days=1)
    return per_day


def write_manifest(  # noqa: PLR0913, PLR0917
    internal_name: str,
    broker_symbol: str,
    digits: int,
    start: date,
    end: date,
    per_day: dict[str, int],
    server: str,
    terminal_build: int,
) -> None:
    manifest = {
        "internal_name": internal_name,
        "broker_symbol": broker_symbol,
        "kind": "ticks",
        "source_server": server,
        "mt5_terminal_build": terminal_build,
        "server_timezone": {
            "convention": SERVER_TZ_CONVENTION,
            "verified": SERVER_TZ_VERIFIED_DATE,
            "source": SERVER_TZ_SOURCE,
        },
        "extracted_at_utc": datetime.now(UTC).isoformat(),
        "window_utc": {"start": start.isoformat(), "end_exclusive": end.isoformat()},
        "total_ticks": sum(per_day.values()),
        "ticks_per_day": per_day,
        "digits": digits,
    }
    path = DATA_ROOT / internal_name / "ticks" / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract an MT5 tick sample to parquet, day by day."
    )
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END, help="exclusive")
    parser.add_argument("--force", action="store_true", help="Re-fetch days already on disk.")
    args = parser.parse_args()
    if args.end <= args.start:
        parser.error("--end must be after --start")

    print("=" * 70)
    print("MT5 TICK EXTRACTION -- read only, places no orders")
    print(f"Window (UTC): {args.start} to {args.end} (exclusive)")
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

    totals: dict[str, int] = {}
    for internal_name, broker_symbol in SYMBOL_MAP.items():
        if not mt5.symbol_select(broker_symbol, True):
            print(f"\n{internal_name}: could not select {broker_symbol}: {mt5.last_error()}")
            continue
        info = mt5.symbol_info(broker_symbol)
        if info is None:
            print(f"\n{internal_name}: symbol_info returned None: {mt5.last_error()}")
            continue
        print(f"\n{internal_name} ({broker_symbol})  ticks")
        per_day = extract_instrument(
            internal_name, broker_symbol, info.digits, args.start, args.end, args.force
        )
        write_manifest(
            internal_name,
            broker_symbol,
            info.digits,
            args.start,
            args.end,
            per_day,
            server,
            terminal_build,
        )
        totals[internal_name] = sum(per_day.values())

    mt5.shutdown()
    print("\n" + "=" * 70)
    for name, total in totals.items():
        print(f"{name:<10} {total:>12,} ticks")
    print("=" * 70)


if __name__ == "__main__":
    main()
