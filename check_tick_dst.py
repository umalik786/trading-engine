"""
Tick-level server-timezone check for the monthly tick sample.

READ ONLY. Reads EURUSD ticks under C:/trading/data/raw/EURUSD/ticks_monthly/
and the sample's manifest; writes nothing.

WHAT IT CHECKS. FX reopens for the week at 17:00 New York time on Sunday --
a market fact, not something this repository decides. Each sampled week runs
from Sunday 00:00 UTC, so the first EURUSD tick in it is that Sunday's open,
and must fall in [17:00, 18:00) New York time -- 17:00 included, 18:00 not.
That is about 21:0x UTC while New York is on summer time and 22:0x in winter.

WHY EXACTLY ONE HOUR WIDE, half-open (operator decision 2026-11-20). A
calendar error shifts every time by exactly one hour. Any time inside a
half-open window one hour wide, moved an hour later, lands at or after 18:00;
moved an hour earlier, before 17:00. So every calendar error still fails,
however late inside the hour the open falls, while a genuinely late open
(2020-06-07 opened at 17:48) passes. The window was 17:00-17:30 until that
week prompted the review; it was widened because of this argument, not to
make that week pass. Any wider and a shifted open could stay inside.

WHICH WEEKS MATTER. In most weeks the US and European daylight-saving
calendars agree, so a converter using the wrong one still passes. The weeks
where they disagree at the Sunday open -- mid/late March, and the end of
October -- are the ones that can catch it, and are marked in the output.

LIMITS. The New York time is computed with the same time-zone library
(America/New_York) the converter relies on, so a wrong FTMO offset rule is
caught but an error in the library's own New York calendar would not be.
Weeks with no Sunday ticks (before the tick history starts, or a holiday) are
reported, not failed.

--european-calendar rebuilds the times a converter using the European DST
calendar would have stored (each tick's server time re-converted with
Europe/Prague's calendar instead of New York's), to show this check failing
on exactly the weeks where the calendars disagree. It changes nothing on disk.

Run with:  uv run python check_tick_dst.py [--european-calendar]
Exit code 0 only if no week fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow.parquet as pq

from engine.core.clock import DstSwitchedServerClock

DATA = Path("C:/trading/data/raw/EURUSD/ticks_monthly")
NEW_YORK = ZoneInfo("America/New_York")
OPEN_FROM, OPEN_TO = time(17, 0), time(18, 0)  # half-open, exactly one hour

# The FTMO server clock as configured (+2/+3 on the US calendar), and the
# wrong one a European-calendar converter would have used.
US_CLOCK = DstSwitchedServerClock(timedelta(hours=2), timedelta(hours=3), "America/New_York")
EU_CLOCK = DstSwitchedServerClock(timedelta(hours=2), timedelta(hours=3), "Europe/Prague")


def as_european_converter(utc: datetime) -> datetime:
    """The UTC time a converter using the European DST calendar would have
    stored for the tick that truly happened at `utc`."""
    server_reading = (utc + US_CLOCK.utc_offset(utc)).replace(tzinfo=None)
    return (server_reading - EU_CLOCK.utc_offset(server_reading)).replace(tzinfo=utc.tzinfo)


def calendars_disagree(utc: datetime) -> bool:
    return US_CLOCK.utc_offset(utc) != EU_CLOCK.utc_offset(utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sunday-open check on the monthly tick sample.")
    parser.add_argument("--european-calendar", action="store_true")
    args = parser.parse_args(argv)

    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    label = (
        "AS A EUROPEAN-CALENDAR CONVERTER WOULD HAVE STORED THEM"
        if args.european_calendar
        else "as stored"
    )
    print(f"Tick DST check -- EURUSD Sunday open, {len(manifest['weeks'])} weeks, {label}\n")

    failures = passes = skipped = 0
    for week in manifest["weeks"]:
        sunday = datetime.fromisoformat(week["start_utc"])
        path = DATA / f"{sunday.date().isoformat()}.parquet"
        if not path.exists():
            print(f"  ----  {sunday:%Y-%m-%d}  no Sunday ticks")
            skipped += 1
            continue
        first = pq.read_table(path, columns=["time"])["time"][0].as_py()
        if args.european_calendar:
            first = as_european_converter(first)
        local = first.astimezone(NEW_YORK)
        ok = OPEN_FROM <= local.time() < OPEN_TO and local.date() == sunday.date()
        flag = "  <- calendars disagree" if calendars_disagree(first) else ""
        status = "PASS" if ok else "FAIL"
        print(
            f"  {status}  {sunday:%Y-%m-%d}  first tick {first:%H:%M:%S} UTC = "
            f"{local:%H:%M} New York{flag}"
        )
        if ok:
            passes += 1
        else:
            failures += 1

    print(f"\n{passes} passed, {failures} failed, {skipped} with no Sunday ticks")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
