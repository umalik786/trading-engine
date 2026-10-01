"""Position sizer protocol. See docs/trading-engine-architecture.md §2.5.

Sizing is separated from the strategy so that how much to trade can be
varied -- fixed fractional, volatility-scaled, Kelly-capped,
confidence-weighted -- without touching signal logic, and so two sizers
can be run against the same signals and compared.

The sizer converts an intent into a concrete quantity. It does not decide
direction: the sign comes from the strategy's target, and a sizer that
flipped it would be originating a position rather than sizing one.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Protocol

from engine.core.portfolio import PortfolioView
from engine.core.types import TargetPosition


class Sizer(Protocol):
    def size(
        self,
        target: TargetPosition,
        portfolio: PortfolioView,
        features: Mapping[str, Any],
    ) -> Decimal:
        """Convert an intent into a concrete quantity, in signed lots."""
        ...
