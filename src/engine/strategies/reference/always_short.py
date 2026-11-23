"""AlwaysShort -- the sell-side mirror of AlwaysLong.

See docs/trading-engine-architecture.md §7.1, which lists `AlwaysLong`,
`AlwaysFlat`, `PerfectForesight` and `RandomEntry` but no short
equivalent. That is a gap in coverage rather than in the spec's
reasoning: every path a short takes through this engine is a separate
path. `Order.side` is "sell" instead of "buy", `Fill.quantity` is
negative instead of positive, `Position.quantity` and `Position.cost`
are both negative, and unrealised P&L moves against the mark rather than
with it. None of that was exercised end to end by phase 2's exit
criterion, which only ever bought.

Its correct result is known in advance in the same way AlwaysLong's is:
the mirror of buy-and-hold on `quantity` lots, less modelled costs. A
short held from entry to the end of the run makes what the long loses and
loses what the long makes.

CONSTRUCTED WITH A POSITIVE SIZE, TARGETS A NEGATIVE ONE. The caller says
how many lots to be short, as a positive number, and the strategy returns
the negative target. Taking a negative constructor argument would make
`AlwaysShort(quantity=Decimal(-1))` and `AlwaysShort(quantity=Decimal(1))`
both look plausible at the call site while meaning different things, and
one of them would silently be a long.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from engine.core.portfolio import PortfolioView
from engine.core.types import Bar, TargetPosition, require_decimal


class AlwaysShort:
    """Sized as EXACTLY ONE of `quantity` (lots) or `weight` (fraction of
    equity), both positive; the strategy applies the direction. A
    `stop_price` (3c.3) is passed through on every target for a sizer to
    size against; the strategy itself never acts on it."""

    def __init__(
        self,
        symbol: str,
        quantity: Decimal | None = None,
        *,
        weight: Decimal | None = None,
        stop_price: Decimal | None = None,
    ) -> None:
        require_decimal("quantity", quantity)
        require_decimal("weight", weight)
        require_decimal("stop_price", stop_price)
        if (quantity is None) == (weight is None):
            raise ValueError(
                f"AlwaysShort takes exactly one of quantity or weight, got "
                f"quantity={quantity}, weight={weight}"
            )
        if quantity is not None and quantity <= 0:
            raise ValueError(
                f"AlwaysShort quantity must be positive lots, got {quantity} -- "
                "the sign is applied by the strategy, not by the caller"
            )
        if weight is not None and weight <= 0:
            raise ValueError(
                f"AlwaysShort weight must be positive, got {weight} -- "
                "the sign is applied by the strategy, not by the caller"
            )
        self._symbol = symbol
        self._quantity = quantity
        self._weight = weight
        self._stop_price = stop_price

    def on_bar(
        self,
        bar: Bar,  # noqa: ARG002 -- the point of this strategy is to ignore its inputs
        features: Mapping[str, Any],  # noqa: ARG002
        portfolio: PortfolioView,  # noqa: ARG002
    ) -> list[TargetPosition]:
        return [
            TargetPosition(
                symbol=self._symbol,
                quantity=None if self._quantity is None else -self._quantity,
                weight=None if self._weight is None else -self._weight,
                stop_price=self._stop_price,
                take_profit=None,
                reason="AlwaysShort: constant short target, every bar",
                confidence=None,
            )
        ]

    @property
    def required_features(self) -> set[str]:
        return set()

    @property
    def warmup_bars(self) -> int:
        return 0
