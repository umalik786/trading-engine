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
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from engine.core.clock import (
    DstSwitchedServerClock,
    IanaServerClock,
    ServerClock,
)
from engine.core.instruments import InstrumentSpec
from engine.core.portfolio import Position
from engine.core.types import Bar, Order
from engine.costs.base import BookSnapshot
from engine.costs.profile import CostProfile, InstrumentCosts, ServerClockConfig, SwapRates

_TWO = Decimal(2)


def build_server_clock(config: ServerClockConfig | None) -> ServerClock | None:
    """Turn clock configuration into a clock. Mechanism here, shape there."""
    if config is None:
        return None
    if config.shape == "iana":
        return IanaServerClock(zone=config.zone)  # type: ignore[arg-type]
    return DstSwitchedServerClock(
        winter_offset=timedelta(hours=config.winter_offset_hours),  # type: ignore[arg-type]
        summer_offset=timedelta(hours=config.summer_offset_hours),  # type: ignore[arg-type]
        dst_calendar=config.dst_calendar,  # type: ignore[arg-type]
    )


class ConfiguredCostModel:
    """Cost model whose every number comes from a `CostProfile`.

    Constructed with contract sizes as well as the profile, because
    `pct_notional` commission needs notional, and notional needs the
    contract size. That keeps §2.8's `fees(order, fill_price)` signature
    intact rather than widening the protocol to pass instrument data that
    the model can perfectly well hold.
    """

    def __init__(self, profile: CostProfile, instruments: Mapping[str, InstrumentSpec]) -> None:
        self._profile = profile
        self._instruments = dict(instruments)
        self._clock = build_server_clock(profile.server_clock)
        self._check_currencies()

    def _check_currencies(self) -> None:
        """Every money figure this model produces is in the account
        currency. An instrument quoted in anything else would need an FX
        rate, and there is none in this project, so this raises at
        construction rather than converting at some unexamined rate or --
        worse -- not converting and reporting the number anyway.

        All five instruments on this venue are USD-quoted against a USD
        account, so this is an assumption made checkable rather than a
        conversion deferred.
        """
        account = self._profile.account_currency
        mismatched = {
            symbol: spec.quote_currency
            for symbol, spec in self._instruments.items()
            if spec.quote_currency != account
        }
        if mismatched:
            raise ValueError(
                f"account currency is {account!r} but these instruments are quoted "
                f"otherwise: {mismatched}. Converting would need an FX rate this "
                "project does not have, so costs for them cannot be expressed"
            )

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
        notional = lots * self._spec_for(order.symbol).contract_size * fill_price
        return notional * value / Decimal(100)

    def financing(
        self,
        position: Position,
        window_start: datetime,
        window_end: datetime,
    ) -> Decimal:
        """Signed financing for every rollover in (window_start, window_end].

        A rollover is charged only if the position was already open at
        that instant -- `position.opened_at` is compared against the
        instant itself, not against its calendar day, because a position
        filled at 23:00 did not exist at the 22:00 rollover even though
        both fall on the same day and in the same session.

        Weekends cost nothing and one configured weekday costs triple. A
        rollover is labelled by the server day that is ENDING, so the
        rollover from Wednesday into Thursday is the "Wednesday night"
        one. Labelling it by the day beginning would move every triple
        charge by a day; the convention is recorded as unverified in
        docs/state.md until it is read off a real deal record.
        """
        rates = self._financing_for(position.symbol)
        if rates.shape == "disabled":
            return Decimal(0)

        nights = Decimal(0)
        for instant in self._clock.rollover_instants(window_start, window_end):
            if instant <= position.opened_at:
                # The position did not exist yet. `<=` rather than `<`
                # because a position opened at exactly the rollover
                # instant is not charged for it -- you do not owe for a
                # night that ended as you came in. The engine loop also
                # arrives at this answer, by evaluating the pre-fill
                # window before applying the fill, but the rule belongs
                # here too: this is the component that owns rollover
                # decisions, and a different caller must not be able to
                # get it wrong by slicing its windows differently.
                continue
            weekday = self._clock.server_date_ending(instant).strftime("%A")
            if weekday in ("Saturday", "Sunday"):
                continue  # market shut; the triple day collects these
            nights += Decimal(3) if weekday == rates.triple_weekday else Decimal(1)

        if nights == 0:
            return Decimal(0)
        rate = rates.long_rate if position.quantity > 0 else rates.short_rate
        return nights * abs(position.quantity) * self._rate_to_money(position.symbol, rates, rate)

    def _rate_to_money(self, symbol: str, rates: SwapRates, rate: Decimal) -> Decimal:
        """One lot, one night, in account currency. Sign preserved.

        `points` is MT5's mode 1, which every instrument on this venue
        uses. The money value of one point per lot is
        `point x contract_size`, which the 2026-09-11 verification run
        confirms equals the broker's own `tick_value` for all five -- two
        independent routes to the same figure.
        """
        if rates.shape == "currency_per_lot":
            return rate
        spec = self._spec_for(symbol)
        return rate * spec.point * spec.contract_size

    def _costs_for(self, symbol: str) -> InstrumentCosts:
        try:
            return self._profile.instruments[symbol]
        except KeyError:
            raise KeyError(
                f"cost profile {self._profile.profile!r} has no entry for {symbol!r} -- "
                "there is deliberately no default, because a missing entry would "
                "silently price that instrument as free to trade"
            ) from None

    def _financing_for(self, symbol: str) -> SwapRates:
        """The swap configuration for a symbol, or an error.

        A MISSING ENTRY IS NOT ZERO. The same rule as a missing commission
        entry and a missing fallback spread: a gap in configuration must
        never make trading cheaper than it is. Holding a position
        overnight costs something on every instrument this venue offers,
        so silence here would be the most flattering possible reading of
        an omission -- and the resulting backtest would look better than
        reality for a reason no test would surface.

        "This instrument has no swap" is a real and legitimate claim. It
        is made by writing `shape: disabled`, which someone has to type.
        """
        try:
            return self._profile.financing.instruments[symbol]
        except KeyError:
            raise KeyError(
                f"cost profile {self._profile.profile!r} has no financing entry for "
                f"{symbol!r}. There is deliberately no default: an omission would "
                "price overnight holding as free. If the instrument genuinely has no "
                "swap, say so with shape: disabled"
            ) from None

    def _spec_for(self, symbol: str) -> InstrumentSpec:
        try:
            return self._instruments[symbol]
        except KeyError:
            raise KeyError(
                f"no instrument specification configured for {symbol!r} -- contract "
                "size and point size come from config/instruments.yaml, and there is "
                "deliberately no default for either"
            ) from None
