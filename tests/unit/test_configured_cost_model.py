"""Tests for ConfiguredCostModel. See docs/trading-engine-architecture.md
§2.8 and Appendix C.1.

Numbers are deliberately round so the arithmetic can be checked by eye:
XAUUSD at 2000.00 with a 0.30 spread and a contract size of 100.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from engine.core.instruments import InstrumentSpec
from engine.core.types import Bar, Order
from engine.costs.configured import ConfiguredCostModel
from engine.costs.profile import CostProfile

SYMBOL = "XAUUSD"
SPECS = {
    SYMBOL: InstrumentSpec(
        contract_size=Decimal(100), point=Decimal("0.01"), quote_currency="USD"
    )
}
_TS = datetime(2025, 6, 10, 12, 0, tzinfo=UTC)
_BAR_WIDTH = timedelta(minutes=15)


def _profile(  # noqa: PLR0913 -- one keyword per profile field under test
    *,
    basis: str = "bid",
    shape: str = "per_lot_per_side",
    value: str = "0",
    fallback: str | None = "0.50",
    slippage: str = "0",
    genuine: list[dict] | None = None,
) -> CostProfile:
    instrument: dict = {
        "commission": {"shape": shape, "value": value},
        "slippage_price_units": slippage,
    }
    if fallback is not None:
        instrument["fallback_spread"] = fallback
    if genuine is not None:
        instrument["zero_spread_genuine"] = genuine
    return CostProfile.model_validate(
        {
            "profile": "unit-test",
            "price_basis": basis,
            # Stated rather than omitted: a profile that covers an
            # instrument must say something about its swap, and these
            # tests are about spread and commission. `disabled` needs no
            # server clock.
            "financing": {"instruments": {SYMBOL: {"shape": "disabled"}}},
            "instruments": {SYMBOL: instrument},
        }
    )


def _model(**kwargs: object) -> ConfiguredCostModel:
    return ConfiguredCostModel(_profile(**kwargs), SPECS)  # type: ignore[arg-type]


def _bar(
    *,
    open_price: str = "2000.00",
    close_price: str = "2010.00",
    spread: str = "0.30",
    ts: datetime = _TS,
) -> Bar:
    prices = [Decimal(open_price), Decimal(close_price)]
    return Bar(
        symbol=SYMBOL,
        ts_open=ts,
        ts_close=ts + _BAR_WIDTH,
        open=prices[0],
        high=max(prices),
        low=min(prices),
        close=prices[1],
        volume=Decimal(1),
        is_final=True,
        spread=Decimal(spread),
    )


def _order(side: str = "buy", quantity: str = "1") -> Order:
    return Order(
        client_order_id="c1",
        symbol=SYMBOL,
        side=side,  # type: ignore[arg-type]
        quantity=Decimal(quantity),
        order_type="market",
        limit_price=None,
        stop_price=None,
        intent_id="i1",
    )


class TestBidBasisPlacement:
    """Stored prices are bids; the ask is bid + spread."""

    def test_a_buy_lifts_the_ask(self) -> None:
        # 2000.00 + 0.30
        assert _model().executable_price("buy", _bar(), Decimal("2000.00")) == Decimal("2000.30")

    def test_a_sell_hits_the_bid_unchanged(self) -> None:
        assert _model().executable_price("sell", _bar(), Decimal("2000.00")) == Decimal("2000.00")

    def test_a_long_is_valued_at_the_close_unchanged(self) -> None:
        """Exiting a long means selling, and the quoted price already is
        the bid."""
        bar = _bar()
        assert _model().executable_price("sell", bar, bar.close) == Decimal("2010.00")

    def test_a_short_is_valued_above_the_close_by_the_spread(self) -> None:
        """Exiting a short means buying, at the ask. This is the case a
        model that only adjusts buys at fill time gets wrong."""
        bar = _bar()
        assert _model().executable_price("buy", bar, bar.close) == Decimal("2010.30")

    def test_the_whole_spread_lands_on_the_buy_side(self) -> None:
        bar = _bar()
        buy = _model().executable_price("buy", bar, Decimal("2000.00"))
        sell = _model().executable_price("sell", bar, Decimal("2000.00"))

        assert buy - sell == bar.spread


class TestMidBasisPlacement:
    """Stored prices are midpoints; each side is half a spread away."""

    def test_a_buy_pays_half_the_spread(self) -> None:
        model = _model(basis="mid")
        # 2000.00 + 0.15
        assert model.executable_price("buy", _bar(), Decimal("2000.00")) == Decimal("2000.15")

    def test_a_sell_gives_up_half_the_spread(self) -> None:
        model = _model(basis="mid")
        assert model.executable_price("sell", _bar(), Decimal("2000.00")) == Decimal("1999.85")

    def test_a_long_is_valued_half_a_spread_below_the_close(self) -> None:
        model = _model(basis="mid")
        bar = _bar()
        assert model.executable_price("sell", bar, bar.close) == Decimal("2009.85")

    def test_a_short_is_valued_half_a_spread_above_the_close(self) -> None:
        model = _model(basis="mid")
        bar = _bar()
        assert model.executable_price("buy", bar, bar.close) == Decimal("2010.15")

    def test_the_two_sides_still_differ_by_one_whole_spread(self) -> None:
        model = _model(basis="mid")
        bar = _bar()
        buy = model.executable_price("buy", bar, Decimal("2000.00"))
        sell = model.executable_price("sell", bar, Decimal("2000.00"))

        assert buy - sell == bar.spread

    def test_halving_an_odd_spread_stays_exact(self) -> None:
        """Dividing a finite decimal by 2 is exact in base 10, so no
        rounding enters the price path."""
        model = _model(basis="mid")
        bar = _bar(spread="0.03")

        assert model.executable_price("buy", bar, Decimal("2000.00")) == Decimal("2000.015")


class TestFillPriceUsesTheFillBar:
    def test_the_fill_price_comes_from_the_bars_own_open_and_spread(self) -> None:
        fill_bar = _bar(open_price="2100.00", spread="0.40")
        # 2100.00 + 0.40
        assert _model().fill_price(_order("buy"), fill_bar) == Decimal("2100.40")

    def test_a_sell_fills_at_the_bars_open(self) -> None:
        fill_bar = _bar(open_price="2100.00", spread="0.40")
        assert _model().fill_price(_order("sell"), fill_bar) == Decimal("2100.00")

    def test_the_deciding_bars_spread_cannot_reach_the_fill(self) -> None:
        """Two bars with different spreads: the fill price depends only on
        the bar handed to fill_price. Nothing in this model can see the
        bar a decision was taken on, which is what makes the wrong-bar
        bug impossible here rather than merely untested."""
        wide = _bar(open_price="2000.00", spread="5.00")
        narrow = _bar(open_price="2000.00", spread="0.10")

        assert _model().fill_price(_order("buy"), wide) == Decimal("2005.00")
        assert _model().fill_price(_order("buy"), narrow) == Decimal("2000.10")


class TestCommissionShapes:
    def test_per_lot_per_side_charges_per_lot(self) -> None:
        model = _model(shape="per_lot_per_side", value="3.50")

        assert model.fees(_order(quantity="1"), Decimal("2000.00")) == Decimal("3.50")
        assert model.fees(_order(quantity="2"), Decimal("2000.00")) == Decimal("7.00")

    def test_per_lot_per_side_charges_a_sell_the_same_as_a_buy(self) -> None:
        model = _model(shape="per_lot_per_side", value="3.50")

        buy = model.fees(_order("buy", "1"), Decimal("2000.00"))
        sell = model.fees(_order("sell", "1"), Decimal("2000.00"))
        assert buy == sell == Decimal("3.50")

    def test_per_lot_round_turn_charges_the_whole_round_turn_at_the_fill(self) -> None:
        """Pessimistic and common broker practice: the full in-and-out
        cost is taken at entry rather than split across two fills."""
        model = _model(shape="per_lot_round_turn", value="7.00")

        assert model.fees(_order(quantity="1"), Decimal("2000.00")) == Decimal("7.00")
        assert model.fees(_order(quantity="3"), Decimal("2000.00")) == Decimal("21.00")

    def test_pct_notional_is_a_percentage_of_lots_times_contract_size_times_price(self) -> None:
        model = _model(shape="pct_notional", value="0.01")

        # notional = 1 x 100 x 2000.00 = 200000.00; 0.01% of that = 20.00
        assert model.fees(_order(quantity="1"), Decimal("2000.00")) == Decimal("20.00")

    def test_pct_notional_scales_with_price(self) -> None:
        model = _model(shape="pct_notional", value="0.01")

        # notional = 1 x 100 x 4000.00 = 400000.00; 0.01% = 40.00
        assert model.fees(_order(quantity="1"), Decimal("4000.00")) == Decimal("40.00")

    def test_commission_is_charged_on_absolute_size(self) -> None:
        """Order quantities are magnitudes, but a negative one must not
        produce a negative fee -- a rebate nobody granted."""
        model = _model(shape="per_lot_per_side", value="3.50")

        assert model.fees(_order(quantity="-2"), Decimal("2000.00")) == Decimal("7.00")

    def test_zero_commission_is_zero(self) -> None:
        assert _model(value="0").fees(_order(), Decimal("2000.00")) == Decimal(0)


class TestZeroSpreadResolution:
    def test_a_non_zero_spread_is_used_as_is(self) -> None:
        assert _model().resolved_spread(_bar(spread="0.30")) == Decimal("0.30")

    def test_a_zero_falls_back_when_no_ranges_are_configured(self) -> None:
        """The pessimistic default. Zeros are 100% of XAUUSD bars before
        2010 because the broker did not record spread, and treating those
        as free is the most flattering error available."""
        model = _model(fallback="0.50")

        assert model.resolved_spread(_bar(spread="0")) == Decimal("0.50")

    def test_a_zero_inside_a_genuine_range_stays_zero(self) -> None:
        model = _model(
            fallback="0.50",
            genuine=[{"from": "2025-06-01", "to": "2025-06-30"}],
        )
        bar = _bar(spread="0", ts=datetime(2025, 6, 10, 12, 0, tzinfo=UTC))

        assert model.resolved_spread(bar) == Decimal(0)

    def test_a_zero_outside_every_genuine_range_falls_back(self) -> None:
        model = _model(
            fallback="0.50",
            genuine=[{"from": "2025-06-01", "to": "2025-06-30"}],
        )
        bar = _bar(spread="0", ts=datetime(2025, 7, 1, 12, 0, tzinfo=UTC))

        assert model.resolved_spread(bar) == Decimal("0.50")

    @pytest.mark.parametrize("day", [1, 30])
    def test_genuine_ranges_include_both_end_dates(self, day: int) -> None:
        model = _model(
            fallback="0.50",
            genuine=[{"from": "2025-06-01", "to": "2025-06-30"}],
        )
        bar = _bar(spread="0", ts=datetime(2025, 6, day, 12, 0, tzinfo=UTC))

        assert model.resolved_spread(bar) == Decimal(0)

    def test_the_date_compared_is_the_bars_utc_open_date(self) -> None:
        """A bar opening at 23:45 UTC on the 30th belongs to the 30th, not
        to the 1st it closes on."""
        model = _model(
            fallback="0.50",
            genuine=[{"from": "2025-06-01", "to": "2025-06-30"}],
        )
        bar = _bar(spread="0", ts=datetime(2025, 6, 30, 23, 45, tzinfo=UTC))

        assert bar.ts_close.date() != bar.ts_open.date()
        assert model.resolved_spread(bar) == Decimal(0)

    def test_a_missing_zero_with_no_fallback_raises(self) -> None:
        """Missing data must never make a trade free, so this is an error
        rather than a silent zero."""
        model = _model(fallback=None)

        with pytest.raises(ValueError, match="must not make a trade free"):
            model.resolved_spread(_bar(spread="0"))

    def test_the_fallback_reaches_the_executable_price(self) -> None:
        """Resolution is not merely reported -- it is what gets charged."""
        model = _model(fallback="0.50")
        bar = _bar(spread="0")

        assert model.executable_price("buy", bar, Decimal("2000.00")) == Decimal("2000.50")


class TestSlippageIsWiredNotDecorative:
    def test_it_is_zero_on_a_profile_that_configures_zero(self) -> None:
        model = _model(slippage="0")

        assert model.executable_price("buy", _bar(), Decimal("2000.00")) == Decimal("2000.30")

    def test_a_non_zero_slippage_moves_a_buy_up(self) -> None:
        """The test that makes the zero meaningful: a zero that is never
        exercised cannot be told apart from one that was never connected."""
        model = _model(slippage="0.05")

        # 2000.00 + 0.30 spread + 0.05 slippage
        assert model.executable_price("buy", _bar(), Decimal("2000.00")) == Decimal("2000.35")

    def test_a_non_zero_slippage_moves_a_sell_down(self) -> None:
        model = _model(slippage="0.05")

        assert model.executable_price("sell", _bar(), Decimal("2000.00")) == Decimal("1999.95")

    def test_slippage_is_adverse_on_both_sides(self) -> None:
        model = _model(slippage="0.05")
        bar = _bar()
        buy = model.executable_price("buy", bar, Decimal("2000.00"))
        sell = model.executable_price("sell", bar, Decimal("2000.00"))

        assert buy > Decimal("2000.00")
        assert sell < Decimal("2000.00")


class TestCurrencyGuard:
    def test_an_instrument_quoted_in_another_currency_raises(self) -> None:
        """Converting would need an FX rate this project does not have, so
        the mismatch is refused at construction rather than producing a
        money figure in the wrong currency."""
        specs = {
            SYMBOL: InstrumentSpec(
                contract_size=Decimal(100), point=Decimal("0.01"), quote_currency="EUR"
            )
        }

        with pytest.raises(ValueError, match="quoted"):
            ConfiguredCostModel(_profile(), specs)


class TestMissingConfiguration:
    def test_an_instrument_absent_from_the_profile_raises(self) -> None:
        model = _model()
        bar = Bar(
            symbol="EURUSD",
            ts_open=_TS,
            ts_close=_TS + _BAR_WIDTH,
            open=Decimal("1.1000"),
            high=Decimal("1.1010"),
            low=Decimal("1.0990"),
            close=Decimal("1.1005"),
            volume=Decimal(1),
            is_final=True,
            spread=Decimal("0.00007"),
        )

        with pytest.raises(KeyError, match="no entry for"):
            model.resolved_spread(bar)
