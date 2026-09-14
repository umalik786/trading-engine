"""Decision log record. See docs/trading-engine-architecture.md §2.9.

Built in phase 0 deliberately: decision context not captured at the time is
unrecoverable, and the advisory layer in §13 depends on it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from engine.core.types import Bar, Order, TargetPosition, require_decimal, require_utc


class RiskDecision(Enum):
    """See §2.6 -- the risk gate's three possible outcomes for an order."""

    APPROVE = "APPROVE"
    REDUCE = "REDUCE"
    REJECT = "REJECT"


@dataclass(frozen=True)
class DecisionRecord:
    """One record per bar in which the engine made or declined to make a decision.

    Two properties are enforced here rather than left to convention (§2.9):

    Rejections are logged as fully as executions. `features`, `strategy_reason`,
    `risk_reason` and `account_snapshot` are validated as present on every
    record regardless of `risk_decision` -- there is no special case that
    lets a REJECT skip them.

    `realised_fill` is backfilled once the fill actually arrives, after the
    record has already been constructed and frozen. There is no in-place
    update: build the updated record with
    `dataclasses.replace(record, realised_fill=filled_price)`, which returns
    a new, independently valid `DecisionRecord` with everything else
    unchanged.
    """

    ts: datetime
    symbol: str
    bar: Bar
    features: Mapping[str, Any]  # full snapshot at decision time
    strategy_output: TargetPosition | None
    strategy_reason: str  # the strategy's stated rationale
    sized_quantity: Decimal | None
    risk_decision: RiskDecision  # APPROVE / REDUCE / REJECT
    risk_reason: str  # why, in every case including approval
    order: Order | None
    expected_fill: Decimal | None  # from the cost model
    realised_fill: Decimal | None  # backfilled when the fill arrives
    account_snapshot: Mapping[str, Any]

    def __post_init__(self) -> None:
        require_utc("ts", self.ts)
        for field_name in ("sized_quantity", "expected_fill", "realised_fill"):
            require_decimal(field_name, getattr(self, field_name))
        if not self.features:
            raise ValueError(
                "features must not be empty -- rejections are logged as fully "
                "as executions, see §2.9"
            )
        if not self.strategy_reason:
            raise ValueError("strategy_reason must not be empty -- see §2.9")
        if not self.risk_reason:
            raise ValueError(
                "risk_reason must not be empty -- required in every case "
                "including approval, see §2.9"
            )
        if not self.account_snapshot:
            raise ValueError(
                "account_snapshot must not be empty -- rejections are logged "
                "as fully as executions, see §2.9"
            )
