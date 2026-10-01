"""Cost model protocol. See docs/trading-engine-architecture.md §2.8 and
Appendix C.

P6: costs are a first-class model, not a constant. Spread, slippage,
commission and financing all come from here, so that the assumptions
behind a backtest's costs can be examined and argued with rather than
being a number buried in the fill logic. Appendix A.1 makes the same point
about why MT5's own Strategy Tester is not used: its fill simulation is a
black box that cannot be inspected or replaced.

Two implementations are required by §2.8. `ZeroCostModel`, for engine
testing only and never for evaluation, and `SpreadAwareCostModel`, with
spread as a function of time-of-day and volatility rather than a constant.
Only the first exists in phase 2; the second is phase 3.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Protocol

from engine.core.portfolio import Position
from engine.core.types import Bar, Order


class BookSnapshot:
    """Placeholder for order-book depth at the moment of a fill.

    Nothing populates this yet, and every `fill_price` call in phases 2
    and 3 receives `None`. It is named in the §2.8 signature and kept here
    so the signature does not have to change when a venue that offers
    depth arrives. Deliberately empty: inventing fields before there is a
    feed to fill them would be guessing at another system's shape.
    """


class CostModel(Protocol):
    def executable_price(
        self,
        side: Literal["buy", "sell"],
        bar: Bar,
        reference_price: Decimal,
    ) -> Decimal:
        """The price a trade in `side` actually executes at, given a quoted
        reference price on `bar`.

        ADDED IN SPEC v3.8, and the reason is drift. Two separate places
        need the same answer: what a fill costs, and what an open position
        could be closed at. Those are the same question -- "if I traded
        this direction now, at what price?" -- and if each place works it
        out for itself they will disagree eventually, in a way no test
        catches, because both will look locally correct.

        So this is the single rule. `fill_price` is a wrapper over it using
        `bar.open`, and position valuation calls it with `bar.close`, once
        per direction. A long is valued at the price it could SELL at; a
        short at the price it could BUY at. Whether the quoted price is a
        bid or a mid, and how much of the spread each side pays, lives in
        the implementation and nowhere else.

        `reference_price` is passed separately rather than read off `bar`
        because the caller chooses which price is being quoted -- the open
        for a fill, the close for a valuation. `bar` is still needed in
        full: the spread comes from it, and so does the date a zero spread
        is judged against.
        """
        ...

    def fill_price(self, order: Order, bar: Bar, book: BookSnapshot | None) -> Decimal:
        """Model the realistic fill, including spread and market impact.

        `bar` is the bar the fill happens on -- for a market order decided
        at the previous bar's close, that is the bar whose open the order
        is being filled against. The spread used is therefore the FILL
        bar's, never the deciding bar's: the deciding bar's spread is a
        price that was already gone by the time the order existed.
        """
        ...

    def fees(self, order: Order, fill_price: Decimal) -> Decimal:
        """Commission and any per-order charge. Positive means charged."""
        ...

    def financing(self, position: Position, bar: Bar) -> Decimal:
        """Overnight/swap costs. Zero for cash equities intraday."""
        ...
