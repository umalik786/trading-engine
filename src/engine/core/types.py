"""Core immutable data types shared by every component in the engine.

See docs/trading-engine-architecture.md §2.1.

`Bar.spread` is an addition to the §2.1 contract, recorded as spec v3.8.
It is carried in PRICE units, never in points: MT5 reports spread as an
integer count of points, and the conversion happens once, at the feed
adapter, using the instrument's point size from configuration. Nothing
above the adapter knows what a point is, because a point means something
different on every instrument (0.01 on XAUUSD, 0.00001 on EURUSD) and a
component that converted on its own would eventually convert with the
wrong one.

A spread of zero is passed through as zero. Whether a zero means "no
spread" or "the broker did not record one" is a question about data
provenance, which the cost model answers from configuration -- see
`engine.costs.configured`. The feed does not guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

# How the account holds positions (spec v3.12, §2.10). Venue configuration,
# never an engine assumption: "netting" keeps one position per symbol;
# "hedging" keeps one per opening fill (a ticket). Both candidate venues are
# hedging (margin_mode 2, verified 2026-09-29).
PositionMode = Literal["netting", "hedging"]


def require_utc(field_name: str, value: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware, got a naive datetime: {value!r}")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be UTC, got offset {value.utcoffset()}: {value!r}")


def require_decimal(field_name: str, value: Decimal | None) -> None:
    if value is None:
        return
    if not isinstance(value, Decimal):
        raise TypeError(
            f"{field_name} must be a Decimal, got {type(value).__name__}. "
            f"Convert via str() first: Decimal(str(value))."
        )


@dataclass(frozen=True)
class Bar:
    symbol: str
    ts_open: datetime  # timezone-aware, always UTC internally
    ts_close: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_final: bool  # False for in-progress bars; strategies see finals only
    spread: Decimal  # bid-ask spread, in PRICE units -- never in points

    def __post_init__(self) -> None:
        require_utc("ts_open", self.ts_open)
        require_utc("ts_close", self.ts_close)
        for field_name in ("open", "high", "low", "close", "volume", "spread"):
            require_decimal(field_name, getattr(self, field_name))
        if self.spread < 0:
            raise ValueError(f"spread must not be negative, got {self.spread}")
        if self.ts_close <= self.ts_open:
            raise ValueError(
                f"ts_close ({self.ts_close!r}) must be after ts_open ({self.ts_open!r})"
            )
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) must be >= low ({self.low})")
        if self.high < self.open:
            raise ValueError(f"high ({self.high}) must be >= open ({self.open})")
        if self.high < self.close:
            raise ValueError(f"high ({self.high}) must be >= close ({self.close})")
        if self.low > self.open:
            raise ValueError(f"low ({self.low}) must be <= open ({self.open})")
        if self.low > self.close:
            raise ValueError(f"low ({self.low}) must be <= close ({self.close})")


@dataclass(frozen=True)
class TargetPosition:
    symbol: str
    # EXACTLY ONE of quantity and weight is given (spec §2.1, amended
    # 2026-11-23, phase 3c.3): two answers to "how big" would leave the
    # sizer choosing between them silently.
    quantity: Decimal | None  # signed lots; negative = short; 0 = flat
    weight: Decimal | None  # signed fraction of equity; the sizer converts it
    stop_price: Decimal | None
    take_profit: Decimal | None
    reason: str  # human-readable; logged with every decision
    confidence: Decimal | None  # 0-1, used by sizer if strategy provides it

    def __post_init__(self) -> None:
        for field_name in ("quantity", "weight", "stop_price", "take_profit", "confidence"):
            require_decimal(field_name, getattr(self, field_name))
        if (self.quantity is None) == (self.weight is None):
            raise ValueError(
                f"a target gives exactly one of quantity or weight; {self.symbol} got "
                f"quantity={self.quantity}, weight={self.weight}"
            )


@dataclass(frozen=True)
class Order:
    client_order_id: str  # deterministic; see §5.2
    symbol: str
    side: Literal["buy", "sell"]
    quantity: Decimal
    order_type: Literal["market", "limit", "stop"]
    limit_price: Decimal | None
    stop_price: Decimal | None
    intent_id: str  # links back to the TargetPosition that produced it
    # Spec v3.12 (position conventions). None: the order opens a position
    # (or, under netting, trades the net position). A ticket: the order
    # reduces exactly that position. On a hedging account an opposite order
    # that names no ticket does not reduce anything -- it opens a second
    # position in the other direction -- so a reduction must say which
    # position it reduces.
    closes_ticket: str | None = None
    # Spec v3.12. The stop loss attached to the position this order opens,
    # executed by the venue, never by the engine. Not `stop_price`, which is
    # the trigger of a stop ENTRY order: one protects a position, the other
    # opens one.
    stop_loss: Decimal | None = None

    def __post_init__(self) -> None:
        for field_name in ("quantity", "limit_price", "stop_price", "stop_loss"):
            require_decimal(field_name, getattr(self, field_name))


@dataclass(frozen=True)
class Fill:
    order_id: str
    client_order_id: str
    symbol: str
    quantity: Decimal
    price: Decimal
    fees: Decimal
    ts: datetime
    # Spec v3.12. The position this fill opened, added to or reduced. Under
    # hedging every opening fill is a new ticket; under netting there is one
    # position per symbol and its ticket is the symbol. No default: every
    # fill touches some position, and a broker that did not say which would
    # leave the ledger guessing.
    ticket: str
    # Spec v3.12. "stop_loss" when the venue closed the position at its stop
    # (phase PC.3); the engine never sends that order itself.
    trigger: Literal["order", "stop_loss"] = "order"

    def __post_init__(self) -> None:
        require_utc("ts", self.ts)
        for field_name in ("quantity", "price", "fees"):
            require_decimal(field_name, getattr(self, field_name))
        if not self.ticket:
            raise ValueError(f"a fill names the position it touched; {self.symbol} got no ticket")
        if self.trigger not in ("order", "stop_loss"):
            raise ValueError(f"trigger must be 'order' or 'stop_loss', got {self.trigger!r}")
