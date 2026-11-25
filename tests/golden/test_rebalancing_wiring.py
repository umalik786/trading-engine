"""Rebalancing through the harness, under both modes (PC.2, decision 2).

A strategy restates a WEIGHT target in XAUUSD every bar; the EquitySizer
turns it into lots. Zero costs and a flat price of 2000.00, so equity stays
at the starting 100,000.00 and every size can be checked by hand:

    lots = weight x equity / (contract size x close), toward zero to 0.05
    0.50 -> 0.5 x 100000 / (100 x 2000) = 0.25
    1.00 ->                               0.50
    0.30 ->                               0.15

    bar   weight   committed   what happens
    0     0.50     0           sized 0.25: buy 0.25
    1     0.50     0.25        identical target: held, no order
    2     1.00     0.25        changed: re-sized to 0.50, buy the 0.25 difference
    3     1.00     0.50        identical: held
    4     0.30     0.50        changed: re-sized to 0.15, reduce by 0.35
    5     0.30     0.15        identical: held

Hedging: the increase at bar 2 is a second ticket; the reduction at bar 4
closes oldest first -- all 0.25 of ticket 1, then 0.10 of ticket 2.
Netting: one order per change.

Until PC.2 the sizer held any same-direction position, so bars 2 and 4
did nothing (the limit recorded in 3c.3).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from harness import run_backtest

from engine.core.instruments import InstrumentSpec
from engine.core.types import Bar, PositionMode, TargetPosition
from engine.sizing.equity import EquitySizer, SizingConfig

GOLD = "XAUUSD"
SPEC = InstrumentSpec(
    contract_size=Decimal(100),
    point=Decimal("0.01"),
    volume_min=Decimal("0.10"),
    volume_step=Decimal("0.05"),
    volume_max=Decimal("5.00"),
)
START = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
WIDTH = timedelta(minutes=15)
D = Decimal

EXPECTED: Mapping[PositionMode, list[tuple]] = {
    "hedging": [
        ("buy", D("0.25"), None),
        ("buy", D("0.25"), None),
        ("sell", D("0.25"), "1"),
        ("sell", D("0.10"), "2"),
    ],
    "netting": [
        ("buy", D("0.25"), None),
        ("buy", D("0.25"), None),
        ("sell", D("0.35"), None),
    ],
}


class _Weights:
    """One weight target per bar, by bar index."""

    warmup_bars = 0

    def __init__(self, weights: Sequence[str]) -> None:
        self._weights = list(weights)
        self._seen = 0

    def on_bar(
        self,
        bar: Bar,  # noqa: ARG002 -- the strategy contract's arguments; a script needs none
        features: object,  # noqa: ARG002
        portfolio: object,  # noqa: ARG002
    ) -> list[TargetPosition]:
        index, self._seen = self._seen, self._seen + 1
        if index >= len(self._weights):
            return []
        return [
            TargetPosition(
                symbol=GOLD,
                quantity=None,
                weight=Decimal(self._weights[index]),
                stop_price=None,
                take_profit=None,
                reason="scripted weight",
                confidence=None,
            )
        ]


def _bars(closes: Sequence[str]) -> list[Bar]:
    return [
        Bar(
            symbol=GOLD,
            ts_open=START + k * WIDTH,
            ts_close=START + (k + 1) * WIDTH,
            open=Decimal(close),
            high=Decimal(close),
            low=Decimal(close),
            close=Decimal(close),
            volume=Decimal(1),
            is_final=True,
            spread=Decimal(0),
        )
        for k, close in enumerate(closes)
    ]


def _run(mode: PositionMode, weights: Sequence[str], closes: Sequence[str]):
    return run_backtest(
        _bars(closes),
        _Weights(weights),
        position_mode=mode,
        contract_sizes={GOLD: SPEC.contract_size},
        instruments={GOLD: SPEC},
        starting_balance=Decimal("100000.00"),
        sizer=EquitySizer(SizingConfig(risk_fraction=Decimal("0.01"))),
    )


@pytest.mark.parametrize("mode", ["hedging", "netting"])
def test_a_changed_weight_is_resized_and_an_identical_one_held(mode: PositionMode) -> None:
    result = _run(mode, ["0.50", "0.50", "1.00", "1.00", "0.30", "0.30"], ["2000.00"] * 7)
    orders = [(o.side, o.quantity, o.closes_ticket) for o in result.orders]
    assert orders == EXPECTED[mode], result.describe()
    assert result.unfilled_orders == ()


@pytest.mark.parametrize("mode", ["hedging", "netting"])
def test_an_identical_target_is_not_resized_as_equity_moves(mode: PositionMode) -> None:
    """The reason the hold exists: without it every move in equity would
    re-size the position, a small trade every bar. The price rises 100.00 a
    bar, equity with it, and the one order stays the only one."""
    closes = ["2000.00", "2100.00", "2200.00", "2300.00"]
    result = _run(mode, ["0.50"] * 4, closes)
    assert [(o.side, o.quantity) for o in result.orders] == [("buy", D("0.25"))]
