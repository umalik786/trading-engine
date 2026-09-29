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
from engine.core.types import Bar, Fill, Order
from engine.costs.base import CostModel


class SimBroker:
    def __init__(self, cost_model: CostModel, portfolio: Portfolio) -> None:
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
            fill_price = self._cost_model.fill_price(order, bar, None)
            fill = Fill(
                order_id=f"sim-{order.client_order_id}",
                client_order_id=order.client_order_id,
                symbol=order.symbol,
                quantity=order.quantity if order.side == "buy" else -order.quantity,
                price=fill_price,
                fees=self._cost_model.fees(order, fill_price),
                ts=bar.ts_open,
            )
            del self._pending[order.client_order_id]
            self._portfolio.apply_fill(fill)
            fills.append(fill)
        self._fills.extend(fills)
        return fills

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
