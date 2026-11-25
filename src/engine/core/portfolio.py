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

TICKETS (spec v3.12, §2.10; phase PC.1). Positions are keyed by ticket.
Under NETTING there is one position per symbol, its ticket is the symbol,
and everything above applies unchanged: average cost, one bounded division
on a partial close, a flip through zero in one fill. Under HEDGING every
opening fill is its own ticket with its own open price, a closing fill
names the ticket it reduces, and P&L is realised against that ticket's own
price -- no averaging at all. The ledger never holds both directions in a
symbol, under either mode (`BothDirectionsError`). Equity is identical
under both modes for any sequence of fills; only the split between
realised and unrealised differs.

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
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from engine.core.types import Fill, PositionMode, require_decimal, require_utc


class BothDirectionsError(RuntimeError):
    """The ledger was asked to hold a long and a short in one symbol at once
    (spec v3.12, §2.10). The engine never does that under either mode, so it
    halts: on a hedging account it means an order that should have named
    the ticket it closes opened an opposite position instead."""


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
    # Spec v3.12. Which position this is. Under hedging, one per opening fill
    # (the broker's ticket); under netting there is one per symbol and its
    # ticket is the symbol.
    ticket: str
    quantity: Decimal
    cost: Decimal
    # When the position was first opened, from the fill that opened it.
    # Financing needs it: a rollover that happened before the position
    # existed is not charged, and "before" is a question about instants,
    # not about calendar days. The position-conventions step will need it
    # too, for closing the oldest ticket first.
    opened_at: datetime
    # Overnight financing charged so far on what is still open, signed.
    # Held on the position rather than in realised P&L because that is
    # what the venue does: MT5 adds swap to the open position, so it moves
    # equity immediately, and books it to balance only on close.
    financing_accrued: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        require_decimal("quantity", self.quantity)
        require_decimal("cost", self.cost)
        require_decimal("financing_accrued", self.financing_accrued)
        require_utc("opened_at", self.opened_at)

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

    @property
    def position_mode(self) -> PositionMode:
        """How the account holds positions (spec v3.12, §2.10)."""
        ...

    def position_quantity(self, symbol: str) -> Decimal:
        """Signed lots currently open in `symbol`, summed over its tickets;
        zero if flat."""
        ...

    def positions(self) -> Mapping[str, Position]:
        """Every open position, keyed by TICKET (v3.12). Under netting the
        ticket is the symbol, so this is keyed by symbol as before."""
        ...

    def tickets(self, symbol: str) -> list[Position]:
        """`symbol`'s open positions in close order: oldest first by open
        time, the ticket number breaking ties (§2.10, §5.4). Empty if flat."""
        ...


class Portfolio:
    """The engine's mutable ledger. Satisfies `PortfolioView` for reading.

    Fed by `apply_fill()` as fills arrive and `mark()` as bars close. It
    holds no opinion about where fills come from, which is exactly why the
    same instance serves a backtest and a live run.
    """

    def __init__(
        self,
        starting_balance: Decimal,
        contract_sizes: Mapping[str, Decimal],
        *,
        position_mode: PositionMode,
    ) -> None:
        if position_mode not in ("netting", "hedging"):
            raise ValueError(f"position_mode must be 'netting' or 'hedging', got {position_mode!r}")
        self._position_mode: PositionMode = position_mode
        require_decimal("starting_balance", starting_balance)
        for symbol, contract_size in contract_sizes.items():
            require_decimal(f"contract_sizes[{symbol!r}]", contract_size)
        self._starting_balance = starting_balance
        self._contract_sizes = dict(contract_sizes)
        self._positions: dict[str, Position] = {}
        self._marks: dict[str, ExitPrices] = {}
        self._realised_pnl = Decimal(0)
        # The same realised P&L, split by symbol (3c.4: the per-instrument
        # breakdown). Every amount booked goes to both, in _realise.
        self._realised_by_symbol: dict[str, Decimal] = {}

    @property
    def position_mode(self) -> PositionMode:
        return self._position_mode

    def tickets(self, symbol: str) -> list[Position]:
        """`symbol`'s open positions, oldest first by open time, the ticket
        number breaking ties -- the order a hedging reduction closes them
        in (§2.10). Compared as NUMBERS: as text, "10" sorts before "9".
        Under netting there is at most one, so there is nothing to order."""
        held = [p for p in self._positions.values() if p.symbol == symbol]
        if self._position_mode == "netting":
            return held
        return sorted(held, key=lambda p: (p.opened_at, int(p.ticket)))

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
        symbols = dict.fromkeys(p.symbol for p in self._positions.values())
        return sum((self.unrealised_pnl_for(symbol) for symbol in symbols), Decimal(0))

    def realised_pnl_for(self, symbol: str) -> Decimal:
        """The part of `realised_pnl` booked against `symbol`: its closed
        lots, its released financing and its fees. Zero if never traded."""
        return self._realised_by_symbol.get(symbol, Decimal(0))

    def unrealised_pnl_for(self, symbol: str) -> Decimal:
        """The part of `unrealised_pnl` belonging to `symbol`'s open
        positions -- every ticket -- at its last mark. Zero if flat."""
        return sum((self._unrealised(position) for position in self.tickets(symbol)), Decimal(0))

    def _unrealised(self, position: Position) -> Decimal:
        """One position's open P&L at its symbol's last mark."""
        symbol = position.symbol
        exit_price = self._marks[symbol].for_quantity(position.quantity)
        value_now = position.quantity * exit_price
        # Accrued financing sits in unrealised, so equity moves the moment
        # it is charged while balance does not -- which is what MT5 does,
        # and why the two diverge on a position held for days. §6.5.3
        # records which of the two each firm's daily loss limit watches, so
        # the distinction decides whether financing counts against the
        # limit yet.
        return (value_now - position.cost) * self._contract_size(symbol) + (
            position.financing_accrued
        )

    def position_quantity(self, symbol: str) -> Decimal:
        return sum((p.quantity for p in self.tickets(symbol)), Decimal(0))

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
        if self._position_mode == "hedging":
            self._apply_hedging_fill(fill)
            return
        if fill.ticket != fill.symbol:
            raise ValueError(
                f"under netting there is one position per symbol and its ticket is the "
                f"symbol; a {fill.symbol} fill named ticket {fill.ticket!r}"
            )
        contract_size = self._contract_size(fill.symbol)
        existing = self._positions.get(fill.symbol)
        old_quantity = existing.quantity if existing is not None else Decimal(0)
        old_cost = existing.cost if existing is not None else Decimal(0)
        old_accrued = existing.financing_accrued if existing is not None else Decimal(0)
        new_quantity = old_quantity + fill.quantity
        # Preserved across adds and partial closes: the position's age is
        # the age of the oldest lot still open. A flip resets it below,
        # because nothing of the old position survives.
        opened_at = existing.opened_at if existing is not None else fill.ts
        new_accrued = old_accrued

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
            self._realise(fill.symbol, (proceeds - cost_removed) * contract_size)
            # Accrued financing follows the lots it belongs to. The closed
            # share is booked to realised, which is MT5's behaviour: swap
            # sits in the open position until the position closes, then
            # lands on balance. The remainder is defined by subtraction, so
            # the proportional step's rounding cancels in equity exactly as
            # it does for the cost basis.
            if closed_lots == abs(old_quantity):
                accrued_released = old_accrued
            else:
                accrued_released = old_accrued * closed_lots / abs(old_quantity)
            self._realise(fill.symbol, accrued_released)
            new_accrued = old_accrued - accrued_released
            # Flipping opens the leftover at this fill's price; otherwise
            # the position keeps exactly the cost that was not removed.
            flipping = abs(fill.quantity) > abs(old_quantity)
            new_cost = new_quantity * fill.price if flipping else old_cost - cost_removed
            if flipping:
                # Nothing of the old position survives, so the new leg is a
                # new position: it starts now and has accrued nothing.
                opened_at = fill.ts
                new_accrued = Decimal(0)

        self._realise(fill.symbol, -fill.fees)
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
                symbol=fill.symbol,
                ticket=fill.symbol,
                quantity=new_quantity,
                cost=new_cost,
                opened_at=opened_at,
                financing_accrued=new_accrued,
            )

    def _apply_hedging_fill(self, fill: Fill) -> None:
        """One fill under hedging (spec v3.12, §2.10).

        A fill naming a ticket that is not open OPENS it, at this fill's
        price and time. A fill naming an open ticket must REDUCE it -- the
        opposite direction, no more lots than it holds -- and realises
        against that ticket's own open price. Every refusal is checked
        before anything changes, so a refused fill leaves the book exactly
        as it was.

        No averaging, and the only division is the bounded one on a partial
        close: a ticket has one open price, so its cost is lots x price and
        cost x closed / lots is that price times the closed lots, exact. The
        accrued swap is split in the same proportion until the venue check
        in docs/state.md (Blocked) says how MT5 books it; the remainder is
        defined by subtraction, so equity is exact either way.
        """
        contract_size = self._contract_size(fill.symbol)
        existing = self._positions.get(fill.ticket)
        if existing is None:
            opposite = [
                p.ticket
                for p in self.tickets(fill.symbol)
                if (p.quantity > 0) != (fill.quantity > 0)
            ]
            if opposite:
                raise BothDirectionsError(
                    f"{fill.symbol}: a {fill.quantity} fill would open ticket {fill.ticket} "
                    f"against open ticket(s) {opposite} in the other direction. The engine "
                    "never holds both directions in a symbol; on a hedging account this means "
                    "an order that should have named the ticket it closes did not"
                )
            self._positions[fill.ticket] = Position(
                symbol=fill.symbol,
                ticket=fill.ticket,
                quantity=fill.quantity,
                cost=fill.quantity * fill.price,
                opened_at=fill.ts,
            )
        else:
            if existing.symbol != fill.symbol:
                raise ValueError(
                    f"ticket {fill.ticket} is a {existing.symbol} position; a {fill.symbol} "
                    "fill cannot touch it"
                )
            if (existing.quantity > 0) == (fill.quantity > 0):
                raise ValueError(
                    f"{fill.symbol}: a {fill.quantity} fill named open ticket {fill.ticket} "
                    f"({existing.quantity} lots) in its own direction. Under hedging an add "
                    "is a new ticket, so the broker and the ledger disagree"
                )
            closed_lots = abs(fill.quantity)
            if closed_lots > abs(existing.quantity):
                raise ValueError(
                    f"{fill.symbol}: a {fill.quantity} fill would close more than ticket "
                    f"{fill.ticket} holds ({existing.quantity} lots)"
                )
            if closed_lots == abs(existing.quantity):
                cost_removed = existing.cost
                accrued_released = existing.financing_accrued
            else:
                cost_removed = existing.cost * closed_lots / abs(existing.quantity)
                accrued_released = existing.financing_accrued * closed_lots / abs(existing.quantity)
            direction = Decimal(1) if existing.quantity > 0 else Decimal(-1)
            proceeds = direction * closed_lots * fill.price
            self._realise(fill.symbol, (proceeds - cost_removed) * contract_size)
            self._realise(fill.symbol, accrued_released)
            remaining = existing.quantity + fill.quantity
            if remaining == 0:
                del self._positions[fill.ticket]
            else:
                self._positions[fill.ticket] = replace(
                    existing,
                    quantity=remaining,
                    cost=existing.cost - cost_removed,
                    financing_accrued=existing.financing_accrued - accrued_released,
                )
        self._realise(fill.symbol, -fill.fees)
        # Provisional mark, as under netting: see apply_fill.
        self._marks[fill.symbol] = ExitPrices.unadjusted(fill.price)

    def _realise(self, symbol: str, amount: Decimal) -> None:
        """Book `amount` to realised P&L, in total and against `symbol`."""
        self._realised_pnl += amount
        self._realised_by_symbol[symbol] = self.realised_pnl_for(symbol) + amount

    def accrue_financing(self, ticket: str, amount: Decimal) -> None:
        """Add overnight financing to one open position, signed. `ticket`
        names the position (v3.12); under netting it is the symbol.

        Negative is charged to the account, positive is paid to it. It
        lands on the position, so it moves equity at once and balance only
        when the position closes.

        Raises if the symbol is flat: financing on a position that does not
        exist is a question the caller should not have asked, and silently
        discarding it would hide a rollover being charged to nothing.
        """
        require_decimal("amount", amount)
        position = self._positions.get(ticket)
        if position is None:
            raise KeyError(
                f"cannot accrue financing on {ticket!r}: no open position. A rollover "
                "charged against a flat book means the caller's idea of what was held "
                "disagrees with the ledger's"
            )
        self._positions[ticket] = replace(
            position, financing_accrued=position.financing_accrued + amount
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
