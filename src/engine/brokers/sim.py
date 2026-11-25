"""SimBroker -- a simulated venue that fills against a `CostModel`.

See docs/trading-engine-architecture.md §2.7 (Broker protocol) and §2.8
(cost model). Appendix A.1: this exists instead of MT5's Strategy Tester
specifically so that its fill assumptions can be read, tested and
replaced.

FILL TIMING -- the rule this class exists to enforce
----------------------------------------------------
A strategy decides when a bar closes. The earliest price it could
actually have traded at is the NEXT bar's open. So `submit()` does not
fill; it queues. The fill happens when the engine hands over the next
bar, at whatever price the cost model derives from that bar.

Filling at the deciding bar's close instead is a one-line change that
inflates every result in the system, and it is undetectable in a P&L
curve: the strategy gets to trade at a price it could only know after the
fact, on every single trade, forever.

"THE NEXT BAR" MEANS THE NEXT BAR THAT EXISTS
---------------------------------------------
There is no clock arithmetic anywhere in this class. It does not know
what a 15-minute bar is and never computes "decision time plus fifteen
minutes". It fills against whatever bar it is handed next for that
symbol. So an order decided at Friday's close fills at Monday's open
across a weekend, and the same holds across an index session break or a
holiday -- Appendix B.6, stored data is never gap-filled, and absent rows
stay absent.

POSITION MODE (spec v3.12, §2.7; phase PC.1)
---------------------------------------------
The simulated account behaves as the configured mode does. Netting: every
fill trades the symbol's one position, whose ticket is the symbol.
Hedging: an order naming no ticket opens a new one, numbered 1, 2, 3... in
fill order and never reused; an order naming a ticket closes it, and MT5's
refusals are reproduced (`SimRejectionError`). An opposite order that names
no ticket opens an opposite position, exactly as MT5 would, so an engine
that forgets to name tickets is caught by the ledger rather than netted for
it.

ONE LEDGER
----------
Positions and account state come from the `Portfolio` this broker is
constructed with -- the same ledger the engine hands the strategy. §5.1
makes the broker authoritative for positions, and in a backtest there is
no second system that could disagree: the simulated venue and the
engine's accounting are the same arithmetic over the same fills, so
giving them separate copies of the book would invent a drift that cannot
occur here and hide the one that can. A live adapter has no such luxury,
which is what §5.3 startup reconciliation is for.
"""

from __future__ import annotations

from engine.brokers.base import AccountState, BrokerOrderRef
from engine.core.portfolio import Portfolio, Position
from engine.core.types import Bar, Fill, Order, PositionMode
from engine.costs.base import CostModel


class SimRejectionError(RuntimeError):
    """The simulated venue refused an order, as MT5 would: closing a ticket
    that is not open, closing it in its own direction, closing more than it
    holds, or naming a ticket on a netting account. Raised, not skipped: an
    engine that sends such an order has a bug, and a backtest that dropped
    the order quietly would report a book the engine never asked for."""


class SimBroker:
    def __init__(
        self, cost_model: CostModel, portfolio: Portfolio, *, position_mode: PositionMode
    ) -> None:
        if portfolio.position_mode != position_mode:
            raise ValueError(
                f"the simulated venue's position mode ({position_mode}) and the ledger's "
                f"({portfolio.position_mode}) must be the same; they describe one account"
            )
        self._position_mode: PositionMode = position_mode
        # Hedging tickets, numbered 1, 2, 3... in fill order and never reused,
        # so a run's tickets are deterministic and their numbers break ties in
        # the close order (§2.10).
        self._last_ticket = 0
        self._cost_model = cost_model
        self._portfolio = portfolio
        self._pending: dict[str, Order] = {}
        self._known_client_order_ids: set[str] = set()
        self._fills: list[Fill] = []

    def submit(self, order: Order) -> BrokerOrderRef:
        """Queue `order` to fill on the next bar for its symbol.

        Idempotent on `client_order_id` per §2.7: an id already seen is
        acknowledged and otherwise ignored, never queued a second time.
        That is the whole point of §5.2 -- a process that dies between
        submitting and recording the response retries with the same id on
        restart, and the retry must be a no-op rather than a second
        position. The id stays known after the order has filled, so a
        late retry cannot re-open it either.
        """
        if order.stop_loss is not None:
            raise NotImplementedError(
                f"{order.symbol}: an order carrying a stop loss ({order.stop_loss}); stop "
                "execution is PC.3, not built yet. Accepting the stop and ignoring it would "
                "run straight through it"
            )
        if order.client_order_id not in self._known_client_order_ids:
            self._known_client_order_ids.add(order.client_order_id)
            self._pending[order.client_order_id] = order
        return BrokerOrderRef(client_order_id=order.client_order_id)

    def cancel(self, order_ref: BrokerOrderRef) -> None:
        self._pending.pop(order_ref.client_order_id, None)

    def fill_pending(self, bar: Bar) -> list[Fill]:
        """Fill every order queued for `bar.symbol` against this bar,
        apply each to the ledger, and return them in submission order.

        NOT part of the `Broker` protocol (§2.7), deliberately. This is
        the simulated venue's bar tick, and a live adapter has no
        equivalent: live fills are discovered by polling deal history over
        a time range and matching against a durable intent log
        (Appendix A.4, A.5, A.7). Reconciling those two shapes behind one
        interface is phase 7's problem, and guessing at it now would bake
        a backtest-only assumption into the orchestrator -- the exact
        drift P1 forbids. Until then, only `SimBroker` has this method and
        only the phase 2 harness calls it.

        Fills are produced in submission order, which is deterministic:
        `dict` preserves insertion order, and insertion order is the order
        the engine submitted in.

        `Fill.quantity` is signed here -- positive for a buy, negative for
        a sell -- because §2.1's `Fill` has no `side` field. `Portfolio`
        reads direction from that sign, so a live adapter must sign its
        fills the same way.
        """
        due = [order for order in self._pending.values() if order.symbol == bar.symbol]
        fills: list[Fill] = []
        for order in due:
            ticket = self._ticket_for(order)
            fill_price = self._cost_model.fill_price(order, bar, None)
            fill = Fill(
                order_id=f"sim-{order.client_order_id}",
                client_order_id=order.client_order_id,
                symbol=order.symbol,
                quantity=order.quantity if order.side == "buy" else -order.quantity,
                price=fill_price,
                fees=self._cost_model.fees(order, fill_price),
                ts=bar.ts_open,
                ticket=ticket,
            )
            del self._pending[order.client_order_id]
            self._portfolio.apply_fill(fill)
            fills.append(fill)
        self._fills.extend(fills)
        return fills

    @property
    def position_mode(self) -> PositionMode:
        """What this simulated account does (§2.7, v3.12)."""
        return self._position_mode

    def _ticket_for(self, order: Order) -> str:
        """The position `order` fills against, refusing what MT5 would refuse.

        Netting: the symbol's one position; naming a ticket is refused.
        Hedging: an order naming no ticket opens a new one -- whatever its
        direction, exactly as MT5 does, so an opposite order that should
        have named a ticket reaches the ledger and halts there
        (`BothDirectionsError`). An order naming a ticket must close an open
        position in that symbol, in the opposite direction, for no more
        lots than it holds.
        """
        if self._position_mode == "netting":
            if order.closes_ticket is not None:
                raise SimRejectionError(
                    f"{order.symbol}: order {order.client_order_id} names ticket "
                    f"{order.closes_ticket}, but a netting account has one position per "
                    "symbol and an order trades it without naming one"
                )
            return order.symbol
        if order.closes_ticket is None:
            self._last_ticket += 1
            return str(self._last_ticket)
        held = self._portfolio.positions().get(order.closes_ticket)
        if held is None or held.symbol != order.symbol:
            raise SimRejectionError(
                f"{order.symbol}: order {order.client_order_id} closes ticket "
                f"{order.closes_ticket}, which is not open in {order.symbol}"
            )
        if (held.quantity > 0) == (order.side == "buy"):
            raise SimRejectionError(
                f"{order.symbol}: order {order.client_order_id} is a {order.side} naming "
                f"ticket {order.closes_ticket} ({held.quantity} lots) -- the ticket's own "
                "direction; a close trades against it"
            )
        if order.quantity > abs(held.quantity):
            raise SimRejectionError(
                f"{order.symbol}: order {order.client_order_id} closes {order.quantity} lots "
                f"of ticket {order.closes_ticket}, which holds {abs(held.quantity)}"
            )
        return order.closes_ticket

    def positions(self) -> list[Position]:
        return list(self._portfolio.positions().values())

    def account(self) -> AccountState:
        return AccountState(balance=self._portfolio.balance, equity=self._portfolio.equity)

    def is_market_open(self, symbol: str) -> bool:  # noqa: ARG002 -- see docstring
        """True whenever a bar is being processed.

        Stored data contains bars only for periods the venue was actually
        open (Appendix B.6: gaps are absent rows, not synthesised ones),
        so in a replay the existence of a bar is itself the evidence that
        the market was open, for any symbol. A live adapter has to answer
        this from the venue instead.
        """
        return True

    def pending_orders(self) -> list[Order]:
        """Orders queued and not yet filled. Empty except between a
        decision and the next bar -- unless the run ended on a decision,
        in which case the last order never filled and this is how the
        harness reports it rather than losing it silently."""
        return list(self._pending.values())

    def fills(self) -> list[Fill]:
        return list(self._fills)
