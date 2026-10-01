"""ConfiguredCostModel -- spread and commission mechanics, driven by a profile.

See docs/trading-engine-architecture.md §2.8 and Appendix C.1. This is the
mechanical cost model: it applies spread and commission exactly where they
belong, using values and formula shapes from configuration. The statistical
spread model of C.1 -- spread as a distribution over time-of-day and
volatility -- is phase 3c and lives elsewhere; this model uses the spread
each bar actually carries.

THE PLACEMENT RULE
------------------
On a `bid` basis the stored prices are bids, and the ask is bid + spread.
You trade at whichever side is worse for you:

    buy          -> reference + spread        (lifting the ask)
    sell         -> reference                 (hitting the bid, as quoted)
    long valued  -> close                     (exit is a sell, at the bid)
    short valued -> close + spread            (exit is a buy, at the ask)

On a `mid` basis the stored prices are midpoints and each side is half a
spread away: buy +s/2, sell -s/2, long valued at close - s/2, short at
close + s/2.

Halving is exact in base 10 for any finite decimal, so no rounding enters
here. The prohibition on division in the accounting path is about
non-terminating quotients like thirds, which this is not.

WHY THIS CHARGES ONE SPREAD PER CROSSING, NOT ONE PER BAR
---------------------------------------------------------
A long on a bid basis pays the whole spread at entry and nothing on exit,
because the quoted price IS where it sells. A short pays nothing at entry
and carries the cost in its valuation, because closing needs the ask. Add
the two legs of a round trip and you get one spread, however many bars the
position was held for. Nothing in this model is applied per bar.

One consequence is worth stating because the two directions are not
symmetric. A long's spread cost is fixed at entry and comes from the FILL
bar. A short's is an unrealised estimate of a crossing that has not
happened, so it is re-priced every bar and comes from the VALUATION bar.
Two different bars, deliberately.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Literal

from engine.core.portfolio import Position
from engine.core.types import Bar, Order
from engine.costs.base import BookSnapshot
from engine.costs.profile import CostProfile, InstrumentCosts

_TWO = Decimal(2)


class ConfiguredCostModel:
    """Cost model whose every number comes from a `CostProfile`.

    Constructed with contract sizes as well as the profile, because
    `pct_notional` commission needs notional, and notional needs the
    contract size. That keeps §2.8's `fees(order, fill_price)` signature
    intact rather than widening the protocol to pass instrument data that
    the model can perfectly well hold.
    """

    def __init__(self, profile: CostProfile, contract_sizes: Mapping[str, Decimal]) -> None:
        self._profile = profile
        self._contract_sizes = dict(contract_sizes)

    def resolved_spread(self, bar: Bar) -> Decimal:
        """The spread to use for `bar`, after deciding what a zero means.

        A zero spread is treated as MISSING DATA unless the bar's UTC open
        date falls inside a configured `zero_spread_genuine` range. With no
        ranges configured, every zero is missing.

        The default runs that way round on purpose. Zero spreads are not
        rare in the stored history -- they are 100% of XAUUSD bars before
        2010 and 100% of the index bars from 2017 to 2020, because the
        broker did not record spread that far back. Treating those as real
        would make every trade in those years free, which is the most
        flattering possible error and invisible in a result. So declaring a
        zero genuine is the only way to loosen this, it has to be done per
        date range, and it is a claim someone has checked.

        If a zero resolves to missing and the profile has no
        `fallback_spread` for the instrument, this raises. Missing data
        must never make a trade free.
        """
        costs = self._costs_for(bar.symbol)
        if bar.spread > 0:
            return bar.spread
        if any(window.contains(bar.ts_open.date()) for window in costs.zero_spread_genuine):
            return Decimal(0)
        if costs.fallback_spread is None:
            raise ValueError(
                f"{bar.symbol} has a zero spread at {bar.ts_open.isoformat()}, which is "
                "treated as missing data, but no fallback_spread is configured for it. "
                "Either set fallback_spread, or declare this date genuine via "
                "zero_spread_genuine -- missing data must not make a trade free"
            )
        return costs.fallback_spread

    def executable_price(
        self,
        side: Literal["buy", "sell"],
        bar: Bar,
        reference_price: Decimal,
    ) -> Decimal:
        """Where a trade in `side` actually executes. The single rule --
        see the module docstring, and §2.8 on why it is not duplicated."""
        costs = self._costs_for(bar.symbol)
        spread = self.resolved_spread(bar)
        slippage = costs.slippage_price_units

        if self._profile.price_basis == "bid":
            # The quoted price is the bid, so a sell needs no spread
            # adjustment at all and a buy pays the whole thing.
            spread_component = spread if side == "buy" else Decimal(0)
        else:
            spread_component = spread / _TWO

        # Slippage always moves against the trader, whichever side.
        if side == "buy":
            return reference_price + spread_component + slippage
        return reference_price - spread_component - slippage

    def fill_price(
        self,
        order: Order,
        bar: Bar,
        book: BookSnapshot | None = None,  # noqa: ARG002 -- no depth source yet
    ) -> Decimal:
        """The fill price for a market order, against the bar it fills on.

        The spread comes from `bar`, which is the FILL bar. The deciding
        bar's spread is irrelevant: it described a market that had already
        moved on by the time this order existed.
        """
        return self.executable_price(order.side, bar, bar.open)

    def fees(self, order: Order, fill_price: Decimal) -> Decimal:
        """Commission on one fill, per the profile's configured shape.

        `per_lot_round_turn` charges the full round turn here, at the fill.
        For the reference strategies that is exactly right, because they
        only ever enter. A strategy that closes a position would be charged
        again on the way out, which over-charges: telling an entry from an
        exit needs position state, and §2.8 hands this method only the
        order and the price. Resolving it belongs with the position
        conventions step, which is where open-versus-close becomes
        explicit. Recorded rather than silently approximated.
        """
        costs = self._costs_for(order.symbol)
        lots = abs(order.quantity)
        shape = costs.commission.shape
        value = costs.commission.value

        if shape in ("per_lot_per_side", "per_lot_round_turn"):
            return lots * value
        notional = lots * self._contract_size_for(order.symbol) * fill_price
        return notional * value / Decimal(100)

    def financing(
        self,
        position: Position,  # noqa: ARG002 -- phase 3b
        bar: Bar,  # noqa: ARG002
    ) -> Decimal:
        """Zero until phase 3b. Appendix C.1 is explicit that returning
        zero here permanently would be a mistake: anything held across
        days pays financing, and a strategy that looks profitable without
        it may not be."""
        return Decimal(0)

    def _costs_for(self, symbol: str) -> InstrumentCosts:
        try:
            return self._profile.instruments[symbol]
        except KeyError:
            raise KeyError(
                f"cost profile {self._profile.profile!r} has no entry for {symbol!r} -- "
                "there is deliberately no default, because a missing entry would "
                "silently price that instrument as free to trade"
            ) from None

    def _contract_size_for(self, symbol: str) -> Decimal:
        try:
            return self._contract_sizes[symbol]
        except KeyError:
            raise KeyError(
                f"no contract size configured for {symbol!r}, needed for pct_notional "
                "commission"
            ) from None
