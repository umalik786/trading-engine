"""Portfolio accounting: positions, realised and unrealised P&L, equity.

See docs/trading-engine-architecture.md §2.4 (`PortfolioView` is what a
strategy is handed) and §3 (`core/portfolio.py` -- "PortfolioView, position
accounting").

This module is the engine's own ledger, and it is built from one input:
the stream of `Fill` objects the broker reports, plus a mark price per
symbol for valuing whatever is still open. That is deliberate. Fills
arrive identically in a backtest (from `SimBroker`) and live (from a real
broker), so the accounting above them is the same code in both wirings --
which is P1, one engine, two wirings.

P&L CONVENTION. Quantity is in lots, signed: positive is long, negative
is short. A position's value moves by

    lots x contract_size x price change

so `contract_size` is the multiplier that turns a price move into money.
It is configuration per instrument (see `engine.core.instruments`), never
a constant in this file -- 1 for the indices, 100,000 for EURUSD, 100 for
XAUUSD, 5,000 for XAGUSD on this venue, and a different broker would use
different numbers. A hardcoded multiplier scales every P&L figure the
system ever reports, and no test would notice.

NOTHING IS ROUNDED HERE, AND ALMOST NOTHING IS DIVIDED. Every value in
and out is `Decimal`, and nothing is quantized to a currency precision.

Addition, subtraction and multiplication of `Decimal` are exact. Division
is not: `Decimal` rounds a non-terminating quotient to the process
context's precision, 28 significant digits by default. That is why this
ledger stores a position's total COST -- the running sum of
`lots x price` -- and never its average price. One lot at 2000.00 plus
two at 2001.00 average 6002/3, which has no finite decimal expansion, so
any P&L computed through that average is a rounded figure. Computed from
the total cost, the same P&L is exact:

    unrealised = (lots x mark - cost) x contract_size

`Position.avg_price` still exists, derived on demand, but it is for
reading and reporting only. No P&L passes through it.

One division remains, and only on a partial close: allocating cost basis
between the lots being closed and the lots left open is proportional, and
a proportion is a division. It is bounded -- `realised` takes the
allocated share and the position keeps `cost` minus that same share, so
the rounding cancels exactly in the sum. Equity and total P&L are
unaffected; only the split between realised and unrealised can differ in
the last digits. A first-in-first-out cost basis would remove even that,
at the cost of changing what "average price" means.

INVARIANT. A position only ever comes into existence through
`apply_fill()`, and `apply_fill()` records that fill's price as the
symbol's mark. So an open position always has a mark price, and
`unrealised_pnl` indexes the mark straight out of the dict rather than
guarding for a missing one: valuing an open position at cost because no
price was on hand would be a silent understatement of equity, and equity
is what a firm's drawdown limit watches.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from engine.core.types import Fill, require_decimal


@dataclass(frozen=True)
class ExitPrices:
    """The two prices at which a position in one symbol could be closed.

    A long exits by selling and a short by buying, so on any venue with a
    spread those are two different prices. The ledger knows which way it
    is positioned; it does not know what a spread is, which side of it
    each direction pays, or what venue it is trading on. So the caller --
    the engine loop -- computes both candidates from the cost model and
    hands them over, and the ledger picks by the sign of what it holds.

    Two named fields rather than two bare `Decimal` arguments, because two
    prices in a row are exactly the kind of pair that gets passed the
    wrong way round, and the resulting error is a plausible-looking P&L.
    """

    long_exit: Decimal
    short_exit: Decimal

    def __post_init__(self) -> None:
        require_decimal("long_exit", self.long_exit)
        require_decimal("short_exit", self.short_exit)

    @classmethod
    def unadjusted(cls, price: Decimal) -> ExitPrices:
        """Both sides at the same price -- no spread, no side. Used where a
        single quoted price is all that exists."""
        return cls(long_exit=price, short_exit=price)

    def for_quantity(self, quantity: Decimal) -> Decimal:
        """The exit price that applies to a signed position."""
        return self.long_exit if quantity > 0 else self.short_exit


@dataclass(frozen=True)
class Position:
    """One open position in one symbol.

    `quantity` is signed lots. `cost` is the signed sum of `lots x price`
    over the fills that opened what is currently held -- not over
    everything ever traded in this symbol, and not a money amount: it is
    in price units, and becomes money when multiplied by the contract
    size. Both are signed the same way, so a short has negative quantity
    and negative cost.

    Cost rather than average price, because cost is only ever added to,
    subtracted from and multiplied, which `Decimal` does exactly. See the
    module docstring. A `Position` with quantity 0 is never stored: a
    closed position is removed outright.
    """

    symbol: str
    quantity: Decimal
    cost: Decimal

    def __post_init__(self) -> None:
        require_decimal("quantity", self.quantity)
        require_decimal("cost", self.cost)

    @property
    def avg_price(self) -> Decimal:
        """The volume-weighted average price of what is open.

        FOR READING AND REPORTING ONLY. This divides, so it is a rounded
        figure whenever the division does not terminate. No P&L in this
        engine is computed through it.
        """
        return self.cost / self.quantity


class PortfolioView(Protocol):
    """The read-only face of the portfolio, and the only one a strategy sees.

    §2.4 hands a strategy `portfolio: PortfolioView`. The two methods that
    change the ledger -- `apply_fill` and `mark` -- are deliberately
    absent from this protocol, so a strategy that reaches for its own
    position fails type checking instead of quietly corrupting a
    backtest. At runtime it is the same `Portfolio` object; the protocol
    is the contract, not a defensive wrapper.
    """

    @property
    def balance(self) -> Decimal:
        """Cash-basis account value: starting balance plus realised P&L,
        less fees. Excludes anything still open."""
        ...

    @property
    def equity(self) -> Decimal:
        """Balance plus the unrealised P&L of open positions at their last
        mark price."""
        ...

    def position_quantity(self, symbol: str) -> Decimal:
        """Signed lots currently open in `symbol`; zero if flat."""
        ...

    def positions(self) -> Mapping[str, Position]:
        """Every open position, keyed by symbol. Flat symbols are absent."""
        ...


class Portfolio:
    """The engine's mutable ledger. Satisfies `PortfolioView` for reading.

    Fed by `apply_fill()` as fills arrive and `mark()` as bars close. It
    holds no opinion about where fills come from, which is exactly why the
    same instance serves a backtest and a live run.
    """

    def __init__(self, starting_balance: Decimal, contract_sizes: Mapping[str, Decimal]) -> None:
        require_decimal("starting_balance", starting_balance)
        for symbol, contract_size in contract_sizes.items():
            require_decimal(f"contract_sizes[{symbol!r}]", contract_size)
        self._starting_balance = starting_balance
        self._contract_sizes = dict(contract_sizes)
        self._positions: dict[str, Position] = {}
        self._marks: dict[str, ExitPrices] = {}
        self._realised_pnl = Decimal(0)

    @property
    def starting_balance(self) -> Decimal:
        return self._starting_balance

    @property
    def balance(self) -> Decimal:
        return self._starting_balance + self._realised_pnl

    @property
    def equity(self) -> Decimal:
        return self.balance + self.unrealised_pnl

    @property
    def realised_pnl(self) -> Decimal:
        """P&L booked by closing lots, less every fee charged so far."""
        return self._realised_pnl

    @property
    def unrealised_pnl(self) -> Decimal:
        """P&L of open positions at their last mark price."""
        total = Decimal(0)
        for symbol, position in self._positions.items():
            exit_price = self._marks[symbol].for_quantity(position.quantity)
            value_now = position.quantity * exit_price
            total += (value_now - position.cost) * self._contract_size(symbol)
        return total

    def position_quantity(self, symbol: str) -> Decimal:
        position = self._positions.get(symbol)
        return position.quantity if position is not None else Decimal(0)

    def positions(self) -> Mapping[str, Position]:
        return dict(self._positions)

    def mark(self, symbol: str, prices: ExitPrices) -> None:
        """Set the prices at which open lots in `symbol` are valued.

        The engine calls this as each bar closes, having asked the cost
        model what a long and a short could each exit at. Unrealised P&L,
        and therefore equity, move only when this is called: there is no
        implicit notion of "the current price" anywhere in the engine,
        because a component that could ask for one could ask at the wrong
        time.
        """
        if not isinstance(prices, ExitPrices):
            raise TypeError(
                f"mark() takes an ExitPrices, got {type(prices).__name__}. A position's "
                "exit price depends on its direction; pass both candidates, or "
                "ExitPrices.unadjusted(price) where there is only one quoted price."
            )
        self._marks[symbol] = prices

    def apply_fill(self, fill: Fill) -> None:
        """Apply one fill to the ledger.

        `fill.quantity` is SIGNED: positive bought, negative sold. §2.1's
        `Fill` carries no `side` field, so the sign is where direction
        lives. `SimBroker` writes it from the order's side and a live
        adapter must do the same.

        Three cases, and the middle one is where accounting bugs hide:

        - Opening, or adding in the same direction. The fill's
          `lots x price` is added to the position's cost. Nothing is
          realised, and no division occurs.
        - Reducing, or closing exactly. The share of cost belonging to the
          closed lots is removed, and the difference between what those
          lots fetched and what they cost is realised. Closing everything
          removes all of the cost exactly; closing part of it is the one
          proportional step in this file, and the position keeps precisely
          what was not removed.
        - Flipping past flat in a single fill. The old position realises
          in full at its own cost, and the leftover opens fresh at this
          fill's price -- the only price the leftover ever traded at.

        Fees are subtracted from realised P&L in all three cases.
        """
        contract_size = self._contract_size(fill.symbol)
        existing = self._positions.get(fill.symbol)
        old_quantity = existing.quantity if existing is not None else Decimal(0)
        old_cost = existing.cost if existing is not None else Decimal(0)
        new_quantity = old_quantity + fill.quantity

        opening_or_adding = old_quantity == 0 or (old_quantity > 0) == (fill.quantity > 0)
        if opening_or_adding:
            new_cost = old_cost + fill.quantity * fill.price
        else:
            closed_lots = min(abs(fill.quantity), abs(old_quantity))
            closing_direction = Decimal(1) if old_quantity > 0 else Decimal(-1)
            if closed_lots == abs(old_quantity):
                cost_removed = old_cost  # exact: everything open is being closed
            else:
                cost_removed = old_cost * closed_lots / abs(old_quantity)
            proceeds = closing_direction * closed_lots * fill.price
            self._realised_pnl += (proceeds - cost_removed) * contract_size
            # Flipping opens the leftover at this fill's price; otherwise
            # the position keeps exactly the cost that was not removed.
            new_cost = (
                new_quantity * fill.price
                if abs(fill.quantity) > abs(old_quantity)
                else old_cost - cost_removed
            )

        self._realised_pnl -= fill.fees
        # A provisional mark, so that an open position always has a price
        # to be valued at. It is the fill's own price on both sides, which
        # ignores the spread -- and that is fine only because the engine
        # loop marks properly from the same bar immediately afterwards,
        # before anything reads equity. The invariant being protected is
        # that a position can never exist unmarked; see the module
        # docstring.
        self._marks[fill.symbol] = ExitPrices.unadjusted(fill.price)

        if new_quantity == 0:
            del self._positions[fill.symbol]
        else:
            self._positions[fill.symbol] = Position(
                symbol=fill.symbol, quantity=new_quantity, cost=new_cost
            )

    def _contract_size(self, symbol: str) -> Decimal:
        try:
            return self._contract_sizes[symbol]
        except KeyError:
            raise KeyError(
                f"no contract size configured for {symbol!r} -- contract sizes are "
                "configuration (config/instruments.yaml) and there is deliberately no "
                "default, because guessing a multiplier silently scales every P&L figure"
            ) from None
