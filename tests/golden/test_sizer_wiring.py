"""The 3c.3 sizer, wired into the bar loop (approved 2026-11-23).

- The sizer receives the deciding bar, the COMMITTED quantity (held plus
  ordered-but-not-filled) and the instrument spec (spec §2.5, decision B).
- Stops are not executed yet (decision D). Rather than let a backtest run
  past a stop as if it were not there, the loop raises the moment a price
  crosses the stop of a position it holds.
- What the sizer adjusted (a cap, a size below the minimum) reaches the
  run's result, so it is visible.

Test instrument: contract size 100, minimum 0.10, step 0.05, maximum 5.00.
Starting balance 100,000 and a deciding close of 2000 make one unit of
weight 0.50 lots.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from harness import NoBarForTargetError, StopNotExecutedError, run_backtest

from engine.core.instruments import InstrumentSpec
from engine.core.portfolio import PortfolioView
from engine.core.types import Bar, TargetPosition
from engine.costs.zero import ZeroCostModel
from engine.sizing.equity import EquitySizer, SizingConfig
from engine.strategies.reference.always_long import AlwaysLong
from engine.strategies.reference.always_short import AlwaysShort

GOLD, SILVER = "XAUUSD", "XAGUSD"
SPECS = {
    GOLD: InstrumentSpec(
        contract_size=Decimal(100),
        point=Decimal("0.01"),
        volume_min=Decimal("0.10"),
        volume_step=Decimal("0.05"),
        volume_max=Decimal("5.00"),
    ),
    SILVER: InstrumentSpec(
        contract_size=Decimal(5000),
        point=Decimal("0.001"),
        volume_min=Decimal("0.10"),
        volume_step=Decimal("0.05"),
        volume_max=Decimal("5.00"),
    ),
}
SIZES = {symbol: spec.contract_size for symbol, spec in SPECS.items()}
START = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
WIDTH = timedelta(minutes=15)


def _bar(  # noqa: PLR0913 -- one keyword per bar field a test varies
    i: int, *, low="2000", high="2000", close="2000", symbol=GOLD, spread="0"
) -> Bar:
    return Bar(
        symbol=symbol,
        ts_open=START + i * WIDTH,
        ts_close=START + (i + 1) * WIDTH,
        open=Decimal(close),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(1),
        is_final=True,
        spread=Decimal(spread),
    )


class AskCostModel(ZeroCostModel):
    """Zero costs, except that a buy happens at the ask (bid + spread), so a
    short's stop can be shown to be checked against the ask."""

    def executable_price(self, side, bar, reference_price):
        return reference_price + bar.spread if side == "buy" else reference_price


def _run(bars, strategy, *, cost_model=None, balance="100000", sizer=None):
    return run_backtest(
        bars,
        strategy,
        position_mode="hedging",
        contract_sizes=SIZES,
        instruments=SPECS,
        starting_balance=Decimal(balance),
        cost_model=cost_model,
        sizer=sizer or EquitySizer(SizingConfig(risk_fraction=Decimal("0.01"))),
    )


def _long_with_stop(stop="1980"):
    return AlwaysLong(GOLD, weight=Decimal(1), stop_price=Decimal(stop))


# --- the stop guard (decision D) ----------------------------------------------


def test_a_long_stop_crossed_after_entry_stops_the_run() -> None:
    bars = [_bar(0), _bar(1), _bar(2, low="1979.99")]
    with pytest.raises(StopNotExecutedError, match="stop execution is not built"):
        _run(bars, _long_with_stop())


def test_a_long_stop_crossed_on_the_fill_bar_stops_the_run() -> None:
    # The order fills at bar 1's open; the position is live for the rest of it.
    bars = [_bar(0), _bar(1, low="1980.00"), _bar(2)]
    with pytest.raises(StopNotExecutedError):
        _run(bars, _long_with_stop())


def test_a_stop_not_reached_lets_the_run_finish() -> None:
    bars = [_bar(0), _bar(1, low="1980.01"), _bar(2, low="1980.01")]
    result = _run(bars, _long_with_stop())
    assert [o.quantity for o in result.orders] == [Decimal("0.50")]


def test_a_cross_on_the_deciding_bar_itself_does_not_count() -> None:
    # The stop is given at bar 0's close; nothing was held while bar 0 traded.
    bars = [_bar(0, low="1970"), _bar(1), _bar(2)]
    _run(bars, _long_with_stop())


def test_a_short_stop_is_checked_against_the_ask() -> None:
    # Bid high 2019.90 is below the 2020 stop; the ask, 2019.90 + 0.20 =
    # 2020.10, is above it -- and a short is closed by buying at the ask.
    strategy = AlwaysShort(GOLD, weight=Decimal(1), stop_price=Decimal("2020"))
    bars = [_bar(0), _bar(1), _bar(2, high="2019.90", spread="0.20")]
    with pytest.raises(StopNotExecutedError):
        _run(bars, strategy, cost_model=AskCostModel())
    calm = [_bar(0), _bar(1), _bar(2, high="2019.70", spread="0.20")]
    _run(calm, strategy, cost_model=AskCostModel())


def test_a_stop_target_sized_to_zero_holds_nothing_to_stop() -> None:
    # Balance 100: 0.01 x 100 / (100 x 20) = 0.0005 lots -> 0. No position.
    bars = [_bar(0), _bar(1, low="1900"), _bar(2)]
    result = _run(bars, _long_with_stop(), balance="100")
    assert result.orders == ()


# --- the committed quantity reaches the sizer ---------------------------------


class BothMetals:
    """Asks for a long weight in BOTH symbols on every bar, whichever
    symbol's bar it is. With bars interleaving, a bar for one symbol cannot
    fill the other's pending order -- the phase 2 double-ordering case."""

    def on_bar(
        self,
        bar: Bar,  # noqa: ARG002 -- the targets ignore every input, by design
        features: Mapping[str, Any],  # noqa: ARG002
        portfolio: PortfolioView,  # noqa: ARG002
    ) -> list[TargetPosition]:
        return [
            TargetPosition(
                symbol=symbol,
                quantity=None,
                weight=Decimal("0.5"),
                stop_price=None,
                take_profit=None,
                reason="test",
                confidence=None,
            )
            for symbol in (GOLD, SILVER)
        ]

    @property
    def required_features(self) -> set[str]:
        return set()

    @property
    def warmup_bars(self) -> int:
        return 0


def test_an_order_in_flight_is_held_not_resized() -> None:
    bars = []
    for i in range(3):
        bars += [_bar(i), _bar(i, symbol=SILVER, low="30", high="30", close="30")]
    result = _run(bars, BothMetals())
    assert sorted(o.symbol for o in result.orders) == [SILVER, GOLD]


# --- what the sizer adjusted is visible ---------------------------------------


def test_a_cap_reaches_the_result() -> None:
    # 12 x 0.50 = 6.00 lots -> capped at 5.00, once (later bars hold).
    result = _run([_bar(0), _bar(1), _bar(2)], AlwaysLong(GOLD, weight=Decimal(12)))
    assert [o.quantity for o in result.orders] == [Decimal("5.00")]
    assert [(n.kind, n.final) for n in result.sizing_notes] == [
        ("capped_at_maximum", Decimal("5.00"))
    ]


def test_specs_that_disagree_with_the_contract_sizes_are_refused() -> None:
    with pytest.raises(ValueError, match="contract size"):
        run_backtest(
            [_bar(0)],
            AlwaysLong(GOLD, quantity=Decimal(1)),
            position_mode="hedging",
            contract_sizes={GOLD: Decimal(1), SILVER: Decimal(5000)},
            instruments=SPECS,
        )


# --- the deciding bar is the TARGET's symbol's latest bar (operator, 2026-11-23) --


class GoldOnSilverBars:
    """Asks for gold only when called on a SILVER bar, so gold is always
    entered on another symbol's bar."""

    def __init__(self, weight: str) -> None:
        self._weight = Decimal(weight)

    def on_bar(
        self,
        bar: Bar,
        features: Mapping[str, Any],  # noqa: ARG002
        portfolio: PortfolioView,  # noqa: ARG002
    ) -> list[TargetPosition]:
        if bar.symbol != SILVER:
            return []
        return [
            TargetPosition(
                symbol=GOLD,
                quantity=None,
                weight=self._weight,
                stop_price=None,
                take_profit=None,
                reason="test",
                confidence=None,
            )
        ]

    @property
    def required_features(self) -> set[str]:
        return set()

    @property
    def warmup_bars(self) -> int:
        return 0


def _silver(i: int) -> Bar:
    return _bar(i, symbol=SILVER, low="30", high="30", close="30")


def test_a_target_is_sized_from_its_own_symbols_last_close() -> None:
    # Decided on silver's bar 0 (close 30), with gold's last close 2000:
    # 0.4 x 100,000 / (100 x 2000) = 0.20 lots. Sized from silver's close it
    # would be 13.3 lots, capped at 5.00. Flat when decided: no hold rule.
    bars = [_bar(0), _silver(0), _bar(1), _silver(1), _bar(2)]
    result = _run(bars, GoldOnSilverBars("0.4"))
    assert [(o.symbol, o.quantity) for o in result.orders] == [(GOLD, Decimal("0.20"))]
    assert result.sizing_notes == ()


class GoldAndSilver:
    """Gold weight 0.4 and silver weight 0.6, asked for on every bar."""

    def on_bar(
        self,
        bar: Bar,  # noqa: ARG002
        features: Mapping[str, Any],  # noqa: ARG002
        portfolio: PortfolioView,  # noqa: ARG002
    ) -> list[TargetPosition]:
        return [
            TargetPosition(
                symbol=symbol,
                quantity=None,
                weight=Decimal(weight),
                stop_price=None,
                take_profit=None,
                reason="test",
                confidence=None,
            )
            for symbol, weight in ((GOLD, "0.4"), (SILVER, "0.6"))
        ]

    @property
    def required_features(self) -> set[str]:
        return set()

    @property
    def warmup_bars(self) -> int:
        return 0


def test_a_target_for_a_symbol_with_no_bar_yet_waits() -> None:
    # Gold's bar 0 comes first: silver has no bar, so its target waits -- no
    # order, one note. On silver's bar 0 it is sized from silver's close:
    # 0.6 x 100,000 / (5000 x 30) = 0.40. Gold: 0.4 x 100,000 / (100 x 2000) = 0.20.
    bars = [_bar(0), _silver(0), _bar(1), _silver(1), _bar(2), _silver(2)]
    result = _run(bars, GoldAndSilver())
    assert [(o.symbol, o.quantity) for o in result.orders] == [
        (GOLD, Decimal("0.20")),
        (SILVER, Decimal("0.40")),
    ]
    (note,) = result.sizing_notes
    assert (note.symbol, note.kind, note.final, note.ts) == (
        SILVER,
        "no_bar_yet",
        Decimal(0),
        _bar(0).ts_close,
    )


def test_a_targeted_symbol_that_never_gets_a_bar_stops_the_run_at_the_end() -> None:
    # Only gold bars: silver's target waits on every bar and is never sized.
    # Waiting is right bar by bar; a whole run of it means the feed and the
    # strategy disagree about the instruments, which must not pass silently.
    with pytest.raises(NoBarForTargetError, match="XAGUSD"):
        _run([_bar(0), _bar(1), _bar(2)], GoldAndSilver())
