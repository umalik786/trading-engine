"""AlwaysFlat -- a reference strategy whose correct result is nothing at all.

See docs/trading-engine-architecture.md §7.1: expected result is exactly
zero P&L and zero orders, and what it catches is phantom trades and state
leakage.

That sounds like a test of nothing, and it is the opposite. A run of this
strategy over data that moves violently must still end with the account
exactly where it started. Any figure other than zero means the engine
opened a position nobody asked for, or carried state from one run into
another, or valued something that was never held. Those faults are
invisible in a profitable-looking equity curve and obvious here.

It returns a target of zero lots rather than an empty list. An empty list
means "no change from current" (§2.4); a target of zero means "be flat",
which is a claim the engine can check against the book.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from engine.core.portfolio import PortfolioView
from engine.core.types import Bar, TargetPosition


class AlwaysFlat:
    def __init__(self, symbol: str) -> None:
        self._symbol = symbol

    def on_bar(
        self,
        bar: Bar,  # noqa: ARG002 -- the point of this strategy is to ignore its inputs
        features: Mapping[str, Any],  # noqa: ARG002
        portfolio: PortfolioView,  # noqa: ARG002
    ) -> list[TargetPosition]:
        return [
            TargetPosition(
                symbol=self._symbol,
                quantity=Decimal(0),
                weight=None,
                stop_price=None,
                take_profit=None,
                reason="AlwaysFlat: never in the market",
                confidence=None,
            )
        ]

    @property
    def required_features(self) -> set[str]:
        return set()

    @property
    def warmup_bars(self) -> int:
        return 0
