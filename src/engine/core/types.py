"""Core immutable data types shared by every component in the engine.

See docs/trading-engine-architecture.md §2.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal


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

    def __post_init__(self) -> None:
        require_utc("ts_open", self.ts_open)
        require_utc("ts_close", self.ts_close)
        for field_name in ("open", "high", "low", "close", "volume"):
            require_decimal(field_name, getattr(self, field_name))
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
    quantity: Decimal  # signed; negative = short; 0 = flat
    # OR, for allocation-style strategies:
    weight: Decimal | None  # fraction of equity; engine converts to quantity
    stop_price: Decimal | None
    take_profit: Decimal | None
    reason: str  # human-readable; logged with every decision
    confidence: Decimal | None  # 0-1, used by sizer if strategy provides it

    def __post_init__(self) -> None:
        for field_name in ("quantity", "weight", "stop_price", "take_profit", "confidence"):
            require_decimal(field_name, getattr(self, field_name))


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

    def __post_init__(self) -> None:
        for field_name in ("quantity", "limit_price", "stop_price"):
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

    def __post_init__(self) -> None:
        require_utc("ts", self.ts)
        for field_name in ("quantity", "price", "fees"):
            require_decimal(field_name, getattr(self, field_name))
