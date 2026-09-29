"""Broker adapter protocol. See docs/trading-engine-architecture.md §2.7.

`SimBroker` implements this against a `CostModel`; a live broker
implements it against a real API. The engine cannot tell them apart, and
nothing above this layer is aware of MT5 or of any other venue
(Appendix A.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from engine.core.portfolio import Position
from engine.core.types import Order


@dataclass(frozen=True)
class BrokerOrderRef:
    """A handle on a submitted order, for cancelling it later.

    Carries the caller's own `client_order_id` rather than a venue ticket,
    because the venue's identifier is not knowable at submit time on every
    venue and is not stable across a restart. §5.2 makes the
    caller-generated id the one that matters.
    """

    client_order_id: str


@dataclass(frozen=True)
class AccountState:
    """What the venue says the account is worth.

    `balance` is the cash-basis figure, closed P&L only. `equity` includes
    open positions at current prices. The distinction is load-bearing:
    §6.5.3 records for each firm whether its daily loss limit is measured
    on equity or on closed balance, and the two diverge exactly when a
    position is deep underwater and still open.
    """

    balance: Decimal
    equity: Decimal


class Broker(Protocol):
    def submit(self, order: Order) -> BrokerOrderRef:
        """MUST be idempotent on client_order_id. Resubmitting the same
        client_order_id MUST NOT create a second order."""
        ...

    def cancel(self, order_ref: BrokerOrderRef) -> None: ...

    def positions(self) -> list[Position]:
        """Ground truth. The engine trusts this over its own memory."""
        ...

    def account(self) -> AccountState: ...

    def is_market_open(self, symbol: str) -> bool: ...
