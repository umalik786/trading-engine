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
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from engine.core.instruments import InstrumentSpec
from engine.core.portfolio import PortfolioView
from engine.core.types import Bar, TargetPosition


@dataclass(frozen=True)
class SizingContext:
    """What the engine hands a sizer besides the target (spec §2.5, amended
    2026-11-23, phase 3c.3).

    `bar` is the DECIDING bar -- the one the strategy has just seen close.
    The fill bar's open is deliberately not here: it does not exist yet when
    the decision is made, so a sizer cannot use it even by mistake.

    `committed` is the signed quantity already held PLUS what is ordered and
    not yet filled. Counting only held lots re-sizes a position whose order
    is still in flight, which is the phase 2 double-ordering bug.

    `spec` is the instrument's specification. None only where the run was
    given no specs, which a sizer that needs them refuses.
    """

    bar: Bar
    committed: Decimal
    spec: InstrumentSpec | None


class Sizer(Protocol):
    def size(
        self,
        target: TargetPosition,
        portfolio: PortfolioView,
        features: Mapping[str, Any],
        context: SizingContext,
    ) -> Decimal:
        """Convert an intent into a concrete quantity, in signed lots."""
        ...
