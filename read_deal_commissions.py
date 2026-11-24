"""
Deal-history commission reader -- what the venue actually charged.

READ ONLY. This script places no orders, modifies nothing on the account and
writes no files. It reads the account's deal history with
history_deals_get() and prints every deal in a window.

WHY. config/cost_ftmo_demo.yaml carries a ZERO commission placeholder, and
third-party sources disagree on FTMO's rate (operator, 2026-11-23). The deal
history is the venue's own record of what it charged on real round trips.

WHAT IT PRINTS, per deal: ticket, position, symbol, type (buy/sell, or a
non-trade type such as a separate commission or balance deal), entry
(in = opening, out = closing), volume, price, commission, fee, swap,
profit -- the money fields exactly as MT5 returns them (repr), so rounding
to cents is visible rather than hidden. For trade deals it also prints
commission per lot and as a percentage of notional (volume x contract size
x price), side by side: a per-lot rate is constant per lot, a percentage
rate is constant per notional. One deal alone fits either; comparing
instruments of the same class (XAUUSD vs XAGUSD, US100 vs US500) helps,
and the venue's own statement settles it.

Non-trade deals (MT5 can charge commission daily or monthly as separate
deals rather than on each trade) are printed too, never filtered out.

TIME. MT5 reports deal times as seconds in SERVER time. Printed as server
time, and as UTC via the profile's server clock (UTC+2/+3, US calendar).

Usage (MT5 terminal running and logged in to the trial account):
    uv run --extra mt5 python read_deal_commissions.py --day 2026-11-24
The window is that UTC day, widened by a day either side so no deal is
missed at a boundary; every deal in it is printed.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import MetaTrader5 as mt5

from engine.core.clock import DstSwitchedServerClock
from engine.core.instruments import load_instrument_specs
from extract_mt5_data import SYMBOL_MAP

INSTRUMENTS = Path(__file__).resolve().parent / "config" / "instruments.yaml"
CLOCK = DstSwitchedServerClock(timedelta(hours=2), timedelta(hours=3), "America/New_York")

DEAL_TYPES = {
    0: "BUY",
    1: "SELL",
    2: "BALANCE",
    3: "CREDIT",
    4: "CHARGE",
    5: "CORRECTION",
    6: "BONUS",
    7: "COMMISSION",
    8: "COMMISSION_DAILY",
    9: "COMMISSION_MONTHLY",
    10: "COMMISSION_AGENT_DAILY",
    11: "COMMISSION_AGENT_MONTHLY",
    12: "INTEREST",
    13: "BUY_CANCELED",
    14: "SELL_CANCELED",
}
ENTRIES = {0: "IN", 1: "OUT", 2: "INOUT", 3: "OUT_BY"}


def server_to_utc(server_seconds: int) -> datetime:
    """Server wall time -> UTC. Unambiguous except within an hour of a DST
    switch, which a trading session in late November never is."""
    wall = datetime.fromtimestamp(server_seconds, tz=UTC)  # server wall time, labelled UTC
    return wall - CLOCK.utc_offset(wall)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--day", required=True, help="UTC date of the trades, YYYY-MM-DD")
    day = datetime.fromisoformat(parser.parse_args().day).replace(tzinfo=UTC)

    print("=" * 78)
    print("DEAL-HISTORY COMMISSION READER -- read only, places no orders")
    print("=" * 78)
    if not mt5.initialize():
        print("\nCould not connect to the terminal:", mt5.last_error())
        return
    try:
        account = mt5.account_info()
        if account is not None:
            print(
                f"Server {account.server} | company {account.company} | "
                f"currency {account.currency} | leverage 1:{account.leverage}"
            )
        internal = {broker: name for name, broker in SYMBOL_MAP.items()}
        specs = load_instrument_specs(INSTRUMENTS)

        deals = mt5.history_deals_get(day - timedelta(days=1), day + timedelta(days=2))
        if deals is None:
            print("history_deals_get failed:", mt5.last_error())
            return
        print(
            f"{len(deals)} deal(s) between {day - timedelta(days=1):%Y-%m-%d} and "
            f"{day + timedelta(days=2):%Y-%m-%d} (UTC dates, widened)\n"
        )
        for d in sorted(deals, key=lambda d: (d.time_msc, d.ticket)):
            kind = DEAL_TYPES.get(d.type, f"UNKNOWN({d.type})")
            entry = ENTRIES.get(d.entry, f"UNKNOWN({d.entry})")
            utc = server_to_utc(d.time)
            server = datetime.fromtimestamp(d.time, tz=UTC)
            print(
                f"deal {d.ticket}  position {d.position_id}  {kind:<10} {entry:<6} "
                f"{d.symbol or '-':<11} server {server:%Y-%m-%d %H:%M:%S}"
                f"  UTC {utc:%Y-%m-%d %H:%M:%S}"
            )
            print(
                f"    volume {d.volume!r}  price {d.price!r}  commission {d.commission!r}  "
                f"fee {d.fee!r}  swap {d.swap!r}  profit {d.profit!r}  comment {d.comment!r}"
            )
            name = internal.get(d.symbol)
            if kind in ("BUY", "SELL") and name in specs and d.volume:
                volume = Decimal(repr(d.volume))
                price = Decimal(repr(d.price))
                commission = Decimal(repr(d.commission))
                notional = volume * specs[name].contract_size * price
                per_lot = commission / volume
                pct = commission / notional * 100 if notional else None
                print(
                    f"    {name}: notional {notional} USD | commission per lot {per_lot} | "
                    f"as % of notional {pct}"
                )
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
