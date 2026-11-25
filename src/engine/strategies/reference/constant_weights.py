"""ConstantWeights -- a basket reference strategy: a constant, signed weight
in each of several symbols, on every bar.

See docs/trading-engine-architecture.md §7.1, and docs/state.md, 3c.4
(operator, 2026-11-23). It is AlwaysLong / AlwaysShort for several
instruments at once: its correct result is each leg's buy-and-hold (or
sell-and-hold) at the size the sizer gives it, less costs, so a wrong figure
is the engine's -- in sizing from shared equity, or in applying each
instrument's own costs -- and not the strategy's, which has no logic.

It restates every leg on every bar, whichever symbol's bar has arrived.
Under target-position semantics (§2.4) each leg produces one order in the
whole run, sized on its own symbol's first bar (the per-symbol deciding bar,
3c.3), and is then held.

The weight's sign is the direction: +1 long, -1 short. A zero weight is
refused: a flat leg is AlwaysFlat's job, and a zero here is more likely a
typing slip than a decision.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from engine.core.portfolio import PortfolioView
from engine.core.types import Bar, TargetPosition, require_decimal


class ConstantWeights:
    """`weights`: symbol -> signed weight (a fraction of equity). Targets are
    returned in the order given, which fixes their order ids."""

    def __init__(self, weights: Mapping[str, Decimal]) -> None:
        if not weights:
            raise ValueError("ConstantWeights needs at least one symbol")
        for symbol, weight in weights.items():
            require_decimal(f"weights[{symbol!r}]", weight)
            if weight == 0:
                raise ValueError(
                    f"ConstantWeights: zero weight for {symbol} -- a flat leg is "
                    "AlwaysFlat's job; leave the symbol out"
                )
        self._weights = dict(weights)  # a copy: later edits by the caller do not leak in

    def on_bar(
        self,
        bar: Bar,  # noqa: ARG002 -- the point of this strategy is to ignore its inputs
        features: Mapping[str, Any],  # noqa: ARG002
        portfolio: PortfolioView,  # noqa: ARG002
    ) -> list[TargetPosition]:
        return [
            TargetPosition(
                symbol=symbol,
                quantity=None,
                weight=weight,
                stop_price=None,
                take_profit=None,
                reason="ConstantWeights: constant weight, every bar",
                confidence=None,
            )
            for symbol, weight in self._weights.items()
        ]

    @property
    def required_features(self) -> set[str]:
        return set()

    @property
    def warmup_bars(self) -> int:
        return 0
