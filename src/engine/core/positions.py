"""The position book: turning a target quantity into orders, per position mode.

See docs/trading-engine-architecture.md §2.10 (spec v3.12, position
conventions).

A strategy and the sizer think in ONE number per symbol: the signed lots
the engine should hold. The account may not. Under netting it holds one
position per symbol, and moving from one quantity to another is one order
for the difference. Under hedging -- what both candidate venues do -- it
holds one position per opening fill, a TICKET, each with its own open
price, and a sell that names no ticket does not reduce a long: it opens a
short beside it. So under hedging a reduction must be planned as closing
orders that name tickets.

The rules, from §2.10:

| | Netting | Hedging |
|---|---|---|
| Increase | one order for the difference | one opening order (a new ticket) |
| Reduction | one order for the difference | close tickets OLDEST FIRST, the last one partly |
| To flat | one order | close every ticket |
| Flip | one order through zero | close every ticket, then open the new direction |

"Oldest first" is the ledger's order: open time, ticket number breaking
ties (`Portfolio.tickets`).

ORDERS NOT YET FILLED COUNT. As in the harness since phase 2, lots ordered
and not filled are as committed as lots held, so the plan starts from held
plus pending. Under hedging a pending close also uses up its ticket: the
lots it will close are not available to close again. A reduction that
could only be met by closing lots whose opening order has not filled yet
-- they have no ticket to name -- is refused (`PlanError`) rather than
guessed at.

IDENTIFIERS. One intent can now produce several orders (closing two
tickets, or a flip). They share the intent's `intent_id` and are told apart
by `client_order_id` = `<intent_id>:<n>`, n counting from 0 in plan order,
so the ids stay deterministic (§5.2) and no two orders share one.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from engine.core.portfolio import PortfolioView
from engine.core.types import Order, PositionMode


class PlanError(RuntimeError):
    """No order plan can move the book to the target without guessing. Under
    hedging: the reduction would have to close lots whose opening order has
    not filled yet, so there is no ticket to name."""


class PositionBook:
    """Plans orders against the ledger, for one position mode."""

    def __init__(self, portfolio: PortfolioView, position_mode: PositionMode) -> None:
        if portfolio.position_mode != position_mode:
            raise ValueError(
                f"the book's position mode ({position_mode}) and the ledger's "
                f"({portfolio.position_mode}) must be the same; they describe one account"
            )
        self._portfolio = portfolio
        self._position_mode = position_mode

    def net_quantity(self, symbol: str) -> Decimal:
        """Signed lots held in `symbol`, under either mode: what strategies,
        the sizer and target logic see."""
        return self._portfolio.position_quantity(symbol)

    def plan(
        self,
        symbol: str,
        target_quantity: Decimal,
        *,
        pending_orders: Sequence[Order],
        intent_id: str,
    ) -> list[Order]:
        """The orders that move held-plus-pending lots in `symbol` to
        `target_quantity`, in the order they must be submitted (closes
        first). Empty if already there."""
        pending = [order for order in pending_orders if order.symbol == symbol]
        committed = self.net_quantity(symbol) + sum(
            (_signed(order) for order in pending), Decimal(0)
        )
        if target_quantity == committed:
            return []
        if self._position_mode == "netting":
            legs = [(target_quantity - committed, None)]
        else:
            legs = self._hedging_legs(symbol, target_quantity, committed, pending)
        return [
            Order(
                client_order_id=f"{intent_id}:{n}",
                symbol=symbol,
                side="buy" if delta > 0 else "sell",
                quantity=abs(delta),
                order_type="market",
                limit_price=None,
                stop_price=None,
                intent_id=intent_id,
                closes_ticket=ticket,
            )
            for n, (delta, ticket) in enumerate(legs)
        ]

    def _hedging_legs(
        self,
        symbol: str,
        target: Decimal,
        committed: Decimal,
        pending: Sequence[Order],
    ) -> list[tuple[Decimal, str | None]]:
        """(signed lots, ticket closed or None) per order, under hedging."""
        same_direction = (target > 0) == (committed > 0)
        if committed == 0 or (same_direction and abs(target) > abs(committed)):
            return [(target - committed, None)]  # an increase: one new ticket
        flipping = target != 0 and not same_direction
        to_close = abs(committed) if flipping else abs(committed - target)
        close_sign = Decimal(-1) if committed > 0 else Decimal(1)
        legs: list[tuple[Decimal, str | None]] = []
        for position in self._portfolio.tickets(symbol):
            if to_close == 0:
                break
            if (position.quantity > 0) != (committed > 0):
                continue  # a ticket a pending flip is already closing out
            being_closed = sum(
                (o.quantity for o in pending if o.closes_ticket == position.ticket),
                Decimal(0),
            )
            take = min(abs(position.quantity) - being_closed, to_close)
            if take > 0:
                legs.append((close_sign * take, position.ticket))
                to_close -= take
        if to_close > 0:
            raise PlanError(
                f"{symbol}: moving {committed} committed lots to {target} would close "
                f"{to_close} lots that have no ticket yet -- their opening order has not "
                "filled. Refused rather than guessed"
            )
        if flipping:
            legs.append((target, None))  # then open the new direction
        return legs


def _signed(order: Order) -> Decimal:
    return order.quantity if order.side == "buy" else -order.quantity
