"""FixedQuantitySizer -- passes the strategy's own quantity straight through.

See docs/trading-engine-architecture.md §2.5.

It exists so that the sizing stage is present in the wiring from the start,
with nothing in it. A real sizer arrives in phase 3c; until then the
quantity a strategy asks for is the quantity that gets ordered, and this
class is where that is stated rather than being implied by the absence of a
step. Adding the stage later would mean changing the middle of the wiring,
which is what P1 exists to prevent.

It also keeps the reference strategies honest: `AlwaysLong` asks for a
constant size and gets exactly that, so when the exit figures are computed
by hand there is no sizing behaviour to account for.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from engine.core.portfolio import PortfolioView
from engine.core.types import TargetPosition


class FixedQuantitySizer:
    def size(
        self,
        target: TargetPosition,
        portfolio: PortfolioView,  # noqa: ARG002 -- a pass-through needs neither
        features: Mapping[str, Any],  # noqa: ARG002
    ) -> Decimal:
        return target.quantity
