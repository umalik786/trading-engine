"""The 3c.2 spread correction, wired into ConfiguredCostModel.

Approved 2026-11-20 (docs/state.md, 3c.2, "Wiring the correction into the
cost model"). Every figure is worked by hand beside it. XAUUSD, point 0.01,
so 1 point = 0.01 in price.

The test table's per-hour corrections are the hour itself, in points
(hour 13 -> +13), except hour 15, which is -4. So the server hour a bar is
filed under can be read straight off the charged spread.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from engine.core.instruments import InstrumentSpec
from engine.core.types import Bar, Order
from engine.costs.configured import ConfiguredCostModel
from engine.costs.correction_table import SpreadCorrectionTable
from engine.costs.profile import CostProfile

SYMBOL = "XAUUSD"
SPECS = {
    SYMBOL: InstrumentSpec(
        contract_size=Decimal(100),
        point=Decimal("0.01"),
        volume_min=Decimal("0.01"),
        volume_step=Decimal("0.01"),
        volume_max=Decimal(100),
    )
}
CUTOFF = datetime(2025, 1, 1, tzinfo=UTC)
WIDTH = timedelta(minutes=15)
# June: New York on summer time -> server UTC+3. 10:00 UTC = server 13:00.
JUNE_10UTC = datetime(2025, 6, 10, 10, 0, tzinfo=UTC)


def _method(form="points", structure="per_hour", percentile=90, weeks=12):
    return {
        "form": form,
        "structure": structure,
        "percentile": percentile,
        "min_fit_weeks": weeks,
        "source": "unit test",
    }


def _profile(*, method=None, genuine=None, clock=True, slippage="0") -> CostProfile:
    instrument: dict = {
        "commission": {"shape": "per_lot_per_side", "value": "0"},
        "fallback_spread": "0.50",
        "slippage": {"shape": "spread_multiple", "value": slippage},
    }
    if method is not None:
        instrument["spread_correction"] = method
    if genuine is not None:
        instrument["zero_spread_genuine"] = genuine
    raw: dict = {
        "profile": "unit-test",
        "price_basis": "bid",
        "financing": {"instruments": {SYMBOL: {"shape": "disabled"}}},
        "instruments": {SYMBOL: instrument},
    }
    if clock:
        raw["server_clock"] = {
            "shape": "dst_switched_offsets",
            "winter_offset_hours": 2,
            "summer_offset_hours": 3,
            "dst_calendar": "America/New_York",
        }
    return CostProfile.model_validate(raw)


def _hourly() -> dict[int, str]:
    values = {h: str(h) for h in range(24)}
    values[15] = "-4"
    return values


def _table(*, form="points", structure="per_hour", percentile=90, weeks=12, corrections=None):
    return SpreadCorrectionTable.model_validate(
        {
            "fit_until": CUTOFF,
            "fitted_at": CUTOFF,
            "source_server": "FTMO-Demo",
            "provenance": {"commit": "test"},
            "instruments": {
                SYMBOL: {
                    "form": form,
                    "structure": structure,
                    "percentile": percentile,
                    "weeks": weeks,
                    "corrections": corrections or _hourly(),
                }
            },
        }
    )


def _model(*, method=None, table=None, **profile_kwargs) -> ConfiguredCostModel:
    method = _method() if method is None else method
    table = _table() if table is None else table
    return ConfiguredCostModel(_profile(method=method, **profile_kwargs), SPECS, table)


def _bar(ts: datetime = JUNE_10UTC, spread: str = "0.30") -> Bar:
    return Bar(
        symbol=SYMBOL,
        ts_open=ts,
        ts_close=ts + WIDTH,
        open=Decimal("2000.00"),
        high=Decimal("2010.00"),
        low=Decimal("2000.00"),
        close=Decimal("2010.00"),
        volume=Decimal(100),
        is_final=True,
        spread=Decimal(spread),
    )


# --- the correction, by server hour -------------------------------------------


def test_points_correction_is_looked_up_by_server_hour() -> None:
    # 10:00 UTC in June = server 13:00 -> +13 points: 0.30 + 0.13 = 0.43.
    assert _model().resolved_spread(_bar()) == Decimal("0.43")


def test_winter_bar_uses_the_winter_offset() -> None:
    # January: server UTC+2. 10:00 UTC = server 12:00 -> 0.30 + 0.12 = 0.42.
    assert _model().resolved_spread(_bar(datetime(2025, 1, 15, 10, tzinfo=UTC))) == Decimal("0.42")


def test_the_hour_follows_the_us_calendar_not_the_european() -> None:
    # 20 March 2025: New York already on summer time (since 9 March), Europe
    # not until 30 March. US calendar: UTC+3 -> server 13:00 -> 0.43. A
    # European-calendar clock would say 12:00 -> 0.42.
    assert _model().resolved_spread(_bar(datetime(2025, 3, 20, 10, tzinfo=UTC))) == Decimal("0.43")


def test_a_negative_correction_never_charges_below_the_minimum() -> None:
    # 12:00 UTC in June = server 15:00 -> -4 points, floored at the minimum.
    assert _model().resolved_spread(_bar(datetime(2025, 6, 10, 12, tzinfo=UTC))) == Decimal("0.30")


def test_percentage_charge_is_rounded_up_to_a_whole_point() -> None:
    # 31 points x (1 + 1/3) = 41.33... points -> rounded UP to 42 -> 0.42.
    model = _model(
        method=_method(form="percentage", structure="constant"),
        table=_table(
            form="percentage", structure="constant", corrections=dict.fromkeys(range(24), "1/3")
        ),
    )
    assert model.resolved_spread(_bar(spread="0.31")) == Decimal("0.42")
    # 30 x 4/3 = 40 exactly: no rounding needed, none applied.
    assert model.resolved_spread(_bar(spread="0.30")) == Decimal("0.40")


# --- zeros and fallbacks ------------------------------------------------------


def test_a_fallback_spread_is_not_corrected() -> None:
    # A zero with no genuine range is missing data -> fallback 0.50, as is.
    assert _model().resolved_spread(_bar(spread="0")) == Decimal("0.50")


def test_a_genuine_zero_gets_the_points_correction() -> None:
    # Genuine from 2022-01-01, open-ended. 0 + 13 points = 0.13.
    model = _model(genuine=[{"from": "2022-01-01"}])
    assert model.resolved_spread(_bar(spread="0")) == Decimal("0.13")


def test_a_genuine_zero_under_percentage_stays_zero() -> None:
    model = _model(
        method=_method(form="percentage", structure="constant"),
        table=_table(
            form="percentage", structure="constant", corrections=dict.fromkeys(range(24), "1/3")
        ),
        genuine=[{"from": "2022-01-01"}],
    )
    assert model.resolved_spread(_bar(spread="0")) == Decimal(0)


# --- the correction reaches fills and slippage --------------------------------


def test_a_buy_fill_pays_the_corrected_spread() -> None:
    order = Order(
        client_order_id="c1",
        symbol=SYMBOL,
        side="buy",
        quantity=Decimal(1),
        order_type="market",
        limit_price=None,
        stop_price=None,
        intent_id="i1",
    )
    assert _model().fill_price(order, _bar()) == Decimal("2000.43")


def test_slippage_scales_the_corrected_spread() -> None:
    # 0.5 x 0.43 = 0.215.
    assert _model(slippage="0.5").slippage(_bar()) == Decimal("0.215")


# --- refusals -----------------------------------------------------------------


def test_a_bar_before_the_tables_cutoff_is_refused() -> None:
    with pytest.raises(ValueError, match="before the table's cutoff"):
        _model().resolved_spread(_bar(CUTOFF - WIDTH))


def test_a_bar_opening_exactly_at_the_cutoff_is_allowed() -> None:
    # 1 January, winter: 00:00 UTC = server 02:00 -> 0.30 + 0.02 = 0.32.
    assert _model().resolved_spread(_bar(CUTOFF)) == Decimal("0.32")


def test_a_method_without_a_table_is_refused() -> None:
    with pytest.raises(ValueError, match="needs a spread-correction table"):
        ConfiguredCostModel(_profile(method=_method()), SPECS)


def test_a_table_missing_the_instrument_is_refused() -> None:
    table = _table().model_copy(update={"instruments": {}})
    with pytest.raises(ValueError, match="has no entry for XAUUSD"):
        _model(table=table)


@pytest.mark.parametrize(
    "mismatch",
    [{"form": "percentage"}, {"structure": "constant"}, {"percentile": 95}],
    ids=["form", "structure", "percentile"],
)
def test_a_table_disagreeing_with_the_profile_method_is_refused(mismatch) -> None:
    kwargs = {"form": "points", "structure": "per_hour", "percentile": 90} | mismatch
    corrections = dict.fromkeys(range(24), "1") if "form" not in mismatch else None
    with pytest.raises(ValueError, match="does not match"):
        _model(table=_table(**kwargs, corrections=corrections))


def test_a_table_fitted_on_too_few_weeks_is_refused() -> None:
    with pytest.raises(ValueError, match="11 sampled weeks"):
        _model(table=_table(weeks=11))


def test_a_method_without_a_server_clock_is_refused() -> None:
    with pytest.raises(ValueError, match="server clock"):
        _model(clock=False)


def test_no_method_means_no_table_needed_and_no_correction() -> None:
    model = ConfiguredCostModel(_profile(), SPECS)
    assert model.resolved_spread(_bar()) == Decimal("0.30")
