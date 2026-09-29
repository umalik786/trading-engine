"""AlwaysLong -- a reference strategy that tests the engine, not an idea.

See docs/trading-engine-architecture.md §7.1. Reference strategies exist
because any strategy can be plugged in, so plugging in one whose correct
result is known in advance turns the engine itself into the thing under
test.

AlwaysLong's correct result is buy-and-hold on `quantity` lots, less
whatever costs are modelled. If the engine reports anything else, the
error is in fills, portfolio accounting or cost application -- not in the
strategy, which has no logic to be wrong about. §9 calls this the most
valuable test in the build: an accounting error found here is one that
would otherwise sit underneath every result the system ever produced.

It holds the same target on every bar, including the first and the last.
Under target-position semantics (§2.4) that produces exactly one order in
the whole run: on the first bar the target differs from a flat book by the
full size, and on every bar after that the difference is zero.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from engine.core.portfolio import PortfolioView
from engine.core.types import Bar, TargetPosition, require_decimal


class AlwaysLong:
    def __init__(self, symbol: str, quantity: Decimal) -> None:
        require_decimal("quantity", quantity)
        if quantity <= 0:
            raise ValueError(f"AlwaysLong quantity must be positive lots, got {quantity}")
        self._symbol = symbol
        self._quantity = quantity

    def on_bar(
        self,
        bar: Bar,  # noqa: ARG002 -- the point of this strategy is to ignore its inputs
        features: Mapping[str, Any],  # noqa: ARG002
        portfolio: PortfolioView,  # noqa: ARG002
    ) -> list[TargetPosition]:
        return [
            TargetPosition(
                symbol=self._symbol,
                quantity=self._quantity,
                weight=None,
                stop_price=None,
                take_profit=None,
                reason="AlwaysLong: constant long target, every bar",
                confidence=None,
            )
        ]

    @property
    def required_features(self) -> set[str]:
        return set()

    @property
    def warmup_bars(self) -> int:
        return 0
