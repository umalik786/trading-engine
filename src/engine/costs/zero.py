"""ZeroCostModel -- frictionless fills, for testing the engine only.

See docs/trading-engine-architecture.md §2.8, which permits this model
"for engine testing only, never for evaluation."

Every fill lands exactly on the bar's open, no spread is crossed, no
commission is charged and no position is financed overnight. That is not
a claim about any market; it is the removal of one variable. Phase 2 asks
whether the accounting is right, and the answer has to be checkable by
hand against a price series. Phase 3 puts the costs back and asks whether
they are applied once, in the right direction, at the right time.

Using this model to judge whether a strategy makes money would be
self-deception with extra steps: it reports the P&L of a venue that does
not exist.
"""

from __future__ import annotations

from decimal import Decimal

from engine.core.portfolio import Position
from engine.core.types import Bar, Order
from engine.costs.base import BookSnapshot


class ZeroCostModel:
    def fill_price(
        self,
        order: Order,  # noqa: ARG002 -- side and size are irrelevant without spread or impact
        bar: Bar,
        book: BookSnapshot | None = None,  # noqa: ARG002
    ) -> Decimal:
        return bar.open

    def fees(
        self,
        order: Order,  # noqa: ARG002
        fill_price: Decimal,  # noqa: ARG002
    ) -> Decimal:
        return Decimal(0)

    def financing(
        self,
        position: Position,  # noqa: ARG002
        bar: Bar,  # noqa: ARG002
    ) -> Decimal:
        return Decimal(0)
