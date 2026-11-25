"""Phase 3c.4 harness wiring: merging several instruments' bars into one run,
and the per-instrument P&L breakdown in the run result.

These check the harness, not a hand figure. The 3c.4 fixture is used because
it is the only multi-instrument data in the repository; no amount it
produces is printed or asserted against a written number here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from harness import FIXTURE_DIR, INSTRUMENTS_CONFIG, load_bars_from_csv, merge_bars, run_backtest

from engine.core.instruments import load_contract_sizes, load_instrument_specs
from engine.core.types import Bar
from engine.sizing.equity import EquitySizer, load_sizing_config
from engine.strategies.reference.always_flat import AlwaysFlat
from engine.strategies.reference.constant_weights import ConstantWeights

ORDER = ("EURUSD", "NAS100", "XAGUSD")
SPAN = "2026-08-25T2100_2026-08-31T0100"


def _series() -> dict[str, list[Bar]]:
    return {
        symbol: load_bars_from_csv(FIXTURE_DIR / f"{symbol.lower()}_m15_{SPAN}.csv", symbol)
        for symbol in ORDER
    }


def _bar(symbol: str, minute: int) -> Bar:
    ts = datetime(2026, 1, 5, tzinfo=UTC) + timedelta(minutes=minute)
    price = Decimal("1.00000")
    return Bar(
        symbol=symbol,
        ts_open=ts,
        ts_close=ts + timedelta(minutes=15),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal(1),
        is_final=True,
        spread=Decimal(0),
    )


class TestMergeBars:
    def test_by_time_then_by_the_stated_symbol_order(self) -> None:
        merged = merge_bars(
            {"B": [_bar("B", 0), _bar("B", 15)], "A": [_bar("A", 15)], "C": [_bar("C", 0)]},
            order=("C", "A", "B"),
        )
        assert [(b.symbol, b.ts_open.minute) for b in merged] == [
            ("C", 0),
            ("B", 0),
            ("A", 15),
            ("B", 15),
        ]

    def test_the_order_must_name_every_symbol_exactly_once(self) -> None:
        with pytest.raises(ValueError, match="processing order"):
            merge_bars({"A": [_bar("A", 0)], "B": [_bar("B", 0)]}, order=("A",))
        with pytest.raises(ValueError, match="processing order"):
            merge_bars({"A": [_bar("A", 0)]}, order=("A", "A"))

    def test_a_series_filed_under_another_symbol_is_refused(self) -> None:
        with pytest.raises(ValueError, match="filed under"):
            merge_bars({"A": [_bar("B", 0)]}, order=("A",))

    def test_a_duplicate_timestamp_within_one_symbol_is_refused(self) -> None:
        with pytest.raises(ValueError, match="twice"):
            merge_bars({"A": [_bar("A", 0), _bar("A", 0)]}, order=("A",))


def _run(strategy, cost_model=None):
    specs = load_instrument_specs(INSTRUMENTS_CONFIG)
    return run_backtest(
        merge_bars(_series(), order=ORDER),
        strategy,
        contract_sizes=load_contract_sizes(INSTRUMENTS_CONFIG),
        starting_balance=Decimal("100000.00"),
        cost_model=cost_model,
        sizer=EquitySizer(load_sizing_config(FIXTURE_DIR / "sizing_test.yaml")),
        instruments=specs,
    )


class TestPnlBySymbol:
    @pytest.mark.parametrize("sign", [1, -1], ids=["long", "short"])
    def test_each_leg_is_its_own_buy_and_hold_without_costs(self, sign: int) -> None:
        """With no costs, each leg is lots x (last close - fill open) x
        contract size, computed here from the bars, not from the engine."""
        series = _series()
        sizes = load_contract_sizes(INSTRUMENTS_CONFIG)
        result = _run(ConstantWeights(dict.fromkeys(ORDER, sign * Decimal(1))))

        assert set(result.pnl_by_symbol) == set(ORDER)
        for fill in result.fills:
            bars = series[fill.symbol]
            fill_bar = next(b for b in bars if b.ts_open == fill.ts)
            assert fill.price == fill_bar.open
            expected = fill.quantity * (bars[-1].close - fill_bar.open) * sizes[fill.symbol]
            assert result.pnl_by_symbol[fill.symbol] == expected, fill.symbol

    def test_the_legs_sum_to_the_total_exactly(self) -> None:
        result = _run(ConstantWeights(dict.fromkeys(ORDER, Decimal(1))))
        assert sum(result.pnl_by_symbol.values()) == result.total_pnl

    def test_a_run_that_never_trades_has_no_legs(self) -> None:
        result = run_backtest(
            _series()["EURUSD"],
            AlwaysFlat(symbol="EURUSD"),
            contract_sizes=load_contract_sizes(INSTRUMENTS_CONFIG),
        )
        assert result.pnl_by_symbol == {}
