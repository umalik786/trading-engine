"""
Margin mode check — netting or hedging, per firm.

READ ONLY. This script places no orders, opens nothing, closes nothing and
writes no files. It reads three fields from account_info() and prints them.

WHY THIS MATTERS. The engine is target-position based (spec section 2.4):
a strategy says where it wants to be, and the engine orders the difference
between that and the one net position it believes it holds. That belief is
only true on a NETTING account, where buying 1 lot and then selling 1 lot
leaves nothing open.

On a HEDGING account the same two orders leave two independent positions
open, each with its own ticket, and "the position in XAUUSD" stops being a
single number. Closing then means addressing specific tickets rather than
trading the difference, and Portfolio.position_quantity() would describe
something the venue does not have.

So this is not a detail of broker configuration. It decides whether the
accounting built in phase 2 describes the account it will eventually trade,
and it is worth knowing before phase 7 picks a firm rather than after.

Prerequisites:
  - MetaTrader 5 terminal is running and logged in to the account to check
  - Run with:  uv run --extra mt5 python check_margin_mode.py

Run it once logged in to each firm and compare the two outputs.
"""

from __future__ import annotations

import MetaTrader5 as mt5

# The three values ACCOUNT_MARGIN_MODE can take. The raw integer is printed
# alongside the name so that an unexpected value shows up as unrecognised
# rather than being silently labelled as one of these.
RETAIL_NETTING = 0
EXCHANGE = 1
RETAIL_HEDGING = 2

MARGIN_MODES = {
    RETAIL_NETTING: "retail netting — one net position per symbol",
    EXCHANGE: "exchange — exchange-style netting",
    RETAIL_HEDGING: "retail hedging — multiple independent positions per symbol",
}


def main() -> None:
    print("=" * 70)
    print("MARGIN MODE CHECK — read only, places no orders")
    print("=" * 70)

    if not mt5.initialize():
        print("\nCould not connect to the terminal:", mt5.last_error())
        print("Check that MT5 is running and logged in, then try again.")
        return

    account = mt5.account_info()
    if account is None:
        print("\naccount_info() returned nothing:", mt5.last_error())
        print("The terminal is running but not logged in to an account.")
        mt5.shutdown()
        return

    mode = account.margin_mode
    description = MARGIN_MODES.get(mode, "UNRECOGNISED — check the MT5 documentation")

    print(f"\nServer      : {account.server}")
    print(f"Company     : {account.company}")
    print(f"Login       : {account.login}")
    print(f"Margin mode : {mode}  ({description})")

    if mode == RETAIL_HEDGING:
        print(
            "\nNote: hedging. Target-position semantics assume one net position\n"
            "per symbol, so this account would need position tickets tracked\n"
            "individually. See the note at the top of this file."
        )

    print("\n" + "=" * 70)
    mt5.shutdown()


if __name__ == "__main__":
    main()
