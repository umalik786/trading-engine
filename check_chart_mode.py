"""
Chart mode check -- which price each symbol's bars are built from.

READ ONLY. This script places no orders and writes no files. It reads
symbol_info() for each instrument and prints what it finds.

WHY THIS MATTERS. config/cost_ftmo_demo.yaml says `price_basis: bid`, which
is an assumption, not a finding (docs/state.md, carried-forward gaps). The
basis decides which side of a trade pays the spread: on bid-built bars a
long pays it on entry and a short pays it while open. Get it wrong and the
cost lands on the wrong side of every trade -- plausible on every chart,
wrong on every trade. symbol_info().chart_mode is the broker's own record
of the answer: 0 = bars built from bid, 1 = bars built from last.

Also printed, because it is in the same record and was never captured:
swap_rollover3days, the weekday the triple swap is charged (0 = Sunday ...
6 = Saturday). This settles WHICH day, not whether "Wednesday" labels the
rollover that ends Wednesday or the one that begins it -- that still needs
a position held across the night (docs/state.md, trial-session plan).

Prerequisites:
  - MetaTrader 5 terminal is running and logged in
  - Run with:  uv run --extra mt5 python check_chart_mode.py
"""

from __future__ import annotations

import MetaTrader5 as mt5

from extract_mt5_data import SYMBOL_MAP

# The raw integer is printed alongside the name so that an unexpected value
# shows up as unrecognised rather than being silently labelled.
CHART_MODES = {0: "bid", 1: "last"}
WEEKDAYS = {
    0: "Sunday",
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
}


def main() -> None:
    print("=" * 70)
    print("CHART MODE CHECK -- read only, places no orders")
    print("=" * 70)

    if not mt5.initialize():
        print("\nCould not connect to the terminal:", mt5.last_error())
        print("Check that MT5 is running and logged in, then try again.")
        return

    account = mt5.account_info()
    if account is not None:
        print(f"\nServer  : {account.server}")
        print(f"Company : {account.company}")

    print(f"\n{'Instrument':<10} {'Broker symbol':<14} {'chart_mode':<22} swap_rollover3days")
    print("-" * 70)
    for internal_name, broker_symbol in SYMBOL_MAP.items():
        mt5.symbol_select(broker_symbol, True)
        info = mt5.symbol_info(broker_symbol)
        if info is None:
            print(f"{internal_name:<10} {broker_symbol:<14} symbol_info failed: {mt5.last_error()}")
            continue
        mode = info.chart_mode
        mode_text = f"{mode} ({CHART_MODES.get(mode, 'UNRECOGNISED')})"
        triple = info.swap_rollover3days
        triple_text = f"{triple} ({WEEKDAYS.get(triple, 'UNRECOGNISED')})"
        print(f"{internal_name:<10} {broker_symbol:<14} {mode_text:<22} {triple_text}")

    print("=" * 70)
    mt5.shutdown()


if __name__ == "__main__":
    main()
