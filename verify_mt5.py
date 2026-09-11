"""
MT5 verification — answers architecture spec section 10, items 1, 3 and 4.

READ ONLY. This script places no orders and modifies nothing on the account.
It reads symbol specifications and measures how much history the broker's
server will actually serve.

Prerequisites:
  - MetaTrader 5 terminal is running and logged in
  - Tools > Options > Charts > "Max bars in chart" is set to Unlimited
  - Run with:  uv run --extra mt5 python verify_mt5.py

Output:
  - A readable report printed to the terminal
  - A JSON file in C:\\trading\\data\\ for the record
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import MetaTrader5 as mt5

# The engine's internal names, and the fragments to search for on the
# broker's server. Brokers rename things: gold is XAUUSD, XAUUSD.m, GOLD...
WANTED = {
    "NAS100": ["NAS100", "USTEC", "NDX", "US100"],
    "US500": ["US500", "SPX500", "SP500", "US500Cash"],
    "EURUSD": ["EURUSD"],
    "XAUUSD": ["XAUUSD", "GOLD"],
    "XAGUSD": ["XAGUSD", "SILVER"],
}

# Bar sizes to measure depth at. The chosen interval falls out of these numbers.
TIMEFRAMES = {
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "D1": mt5.TIMEFRAME_D1,
}

# Deliberately earlier than any retail broker holds, so the server's own
# limit is what we measure rather than ours.
HISTORY_START = datetime(2005, 1, 1, tzinfo=timezone.utc)

OUTPUT_DIR = Path(r"C:\trading\data")


def decode_filling_mode(mode: int) -> list[str]:
    """filling_mode is a bitmask. Which fill types this symbol accepts.

    Matters because order_send() fails with an unhelpful code if you ask
    for a fill type the symbol does not support.
    """
    modes = []
    if mode & 1:
        modes.append("FOK (fill or kill)")
    if mode & 2:
        modes.append("IOC (immediate or cancel)")
    if not modes:
        modes.append(f"unrecognised bitmask: {mode}")
    return modes


def resolve_symbols() -> dict[str, str | None]:
    """Find what each instrument is actually called on this server."""
    all_symbols = mt5.symbols_get()
    if all_symbols is None:
        print("  Could not list symbols:", mt5.last_error())
        return {k: None for k in WANTED}

    names = [s.name for s in all_symbols]
    print(f"  Server exposes {len(names)} symbols.")

    resolved: dict[str, str | None] = {}
    for internal, fragments in WANTED.items():
        matches = [
            n for n in names
            if any(f.upper() in n.upper() for f in fragments)
        ]
        # Prefer the shortest match: "XAUUSD" over "XAUUSD.raw" etc.
        matches.sort(key=len)
        resolved[internal] = matches[0] if matches else None
        if matches:
            extra = f"   (others: {', '.join(matches[1:6])})" if len(matches) > 1 else ""
            print(f"  {internal:<8} -> {matches[0]}{extra}")
        else:
            print(f"  {internal:<8} -> NOT FOUND (searched: {', '.join(fragments)})")
    return resolved


def describe_symbol(broker_name: str) -> dict:
    """Everything the sizer and cost model need. Spec section 10 item 4."""
    if not mt5.symbol_select(broker_name, True):
        return {"error": f"symbol_select failed: {mt5.last_error()}"}

    info = mt5.symbol_info(broker_name)
    if info is None:
        return {"error": f"symbol_info returned None: {mt5.last_error()}"}

    tick = mt5.symbol_info_tick(broker_name)
    spread_points = (
        round((tick.ask - tick.bid) / info.point) if tick and info.point else None
    )

    return {
        "broker_name": info.name,
        "description": info.description,
        "digits": info.digits,
        "point": info.point,
        "contract_size": info.trade_contract_size,
        "volume_min": info.volume_min,
        "volume_max": info.volume_max,
        "volume_step": info.volume_step,
        "tick_size": info.trade_tick_size,
        "tick_value": info.trade_tick_value,
        "margin_initial": info.margin_initial,
        "swap_long": info.swap_long,
        "swap_short": info.swap_short,
        "swap_mode": info.swap_mode,
        "filling_mode_raw": info.filling_mode,
        "filling_modes": decode_filling_mode(info.filling_mode),
        "spread_now_points": spread_points,
        "bid_now": tick.bid if tick else None,
        "ask_now": tick.ask if tick else None,
    }


def measure_depth(broker_name: str) -> dict:
    """How far back the server will actually serve. Spec section 10 item 1.

    This is the number that decides whether walk-forward validation is
    possible at all, so it is measured rather than assumed.
    """
    now = datetime.now(timezone.utc)
    result = {}

    for label, tf in TIMEFRAMES.items():
        rates = mt5.copy_rates_range(broker_name, tf, HISTORY_START, now)

        if rates is None or len(rates) == 0:
            result[label] = {
                "bars": 0,
                "earliest": None,
                "latest": None,
                "years": 0.0,
                "note": f"no data returned: {mt5.last_error()}",
            }
            continue

        earliest = datetime.fromtimestamp(int(rates[0]["time"]), tz=timezone.utc)
        latest = datetime.fromtimestamp(int(rates[-1]["time"]), tz=timezone.utc)
        span_years = (latest - earliest).days / 365.25

        result[label] = {
            "bars": len(rates),
            "earliest": earliest.isoformat(),
            "latest": latest.isoformat(),
            "years": round(span_years, 2),
        }
    return result


def main() -> None:
    print("=" * 70)
    print("MT5 VERIFICATION — read only, places no orders")
    print("=" * 70)

    if not mt5.initialize():
        print("\nCould not connect to the terminal:", mt5.last_error())
        print("Check that MT5 is running and logged in, then try again.")
        return

    term = mt5.terminal_info()
    acct = mt5.account_info()

    print(f"\nTerminal : {term.name} build {term.build}")
    print(f"Connected: {term.connected}   Algo trading enabled: {term.trade_allowed}")
    if acct:
        print(f"Account  : {acct.login} on {acct.server}")
        print(f"Currency : {acct.currency}   Balance: {acct.balance}")
        print(f"Company  : {acct.company}")

    print("\n" + "-" * 70)
    print("RESOLVING SYMBOL NAMES")
    print("-" * 70)
    resolved = resolve_symbols()

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "server": acct.server if acct else None,
        "company": acct.company if acct else None,
        "terminal_build": term.build,
        "instruments": {},
    }

    for internal, broker_name in resolved.items():
        print("\n" + "-" * 70)
        print(f"{internal}")
        print("-" * 70)

        if broker_name is None:
            print("  Skipped — no matching symbol on this server.")
            report["instruments"][internal] = {"error": "symbol not found"}
            continue

        spec = describe_symbol(broker_name)
        if "error" in spec:
            print("  ", spec["error"])
            report["instruments"][internal] = spec
            continue

        print(f"  Broker name   : {spec['broker_name']}  ({spec['description']})")
        print(f"  Digits        : {spec['digits']}   Point: {spec['point']}")
        print(f"  Contract size : {spec['contract_size']}")
        print(f"  Volume        : min {spec['volume_min']}, "
              f"step {spec['volume_step']}, max {spec['volume_max']}")
        print(f"  Swap long/short: {spec['swap_long']} / {spec['swap_short']}")
        print(f"  Filling modes : {', '.join(spec['filling_modes'])}")
        print(f"  Spread now    : {spec['spread_now_points']} points")

        print("  History depth:")
        depth = measure_depth(broker_name)
        for label, d in depth.items():
            if d["bars"] == 0:
                print(f"    {label:<4} none — {d.get('note', '')}")
            else:
                print(f"    {label:<4} {d['bars']:>9,} bars   "
                      f"from {d['earliest'][:10]}   ({d['years']} years)")

        report["instruments"][internal] = {"spec": spec, "depth": depth}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = OUTPUT_DIR / f"mt5-verification-{stamp}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n" + "=" * 70)
    print(f"Saved to {out}")
    print("=" * 70)

    mt5.shutdown()


if __name__ == "__main__":
    main()
