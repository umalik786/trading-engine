"""The position book wired through the harness, under both modes (PC.1).

One scripted sequence of QUANTITY targets in XAUUSD, zero costs, decided at
each bar's close and filled at the next bar's open:

    bar   decides   fills at next open
    0     +0.30     bar 1, 2000.00
    1     +0.50     bar 2, 2010.00
    2     +0.10     bar 3, 2020.00
    3     -0.20     bar 4, 2015.00
    4     -0.20     (held: nothing to do)
    5      0        bar 6, 2005.00

Hand figures (contract size 100), hedging, per ticket:
    ticket 1, long 0.30 @ 2000, closed @ 2020:            0.30 x 20 x 100 = 600
    ticket 2, long 0.20 @ 2010, 0.10 closed @ 2020:        0.10 x 10 x 100 = 100
                                0.10 closed @ 2015:        0.10 x  5 x 100 =  50
    ticket 3, short 0.20 @ 2015, closed @ 2005:            0.20 x 10 x 100 = 200
                                                                     total   950
Netting, average cost:
    0.50 held at cost 0.30 x 2000 + 0.20 x 2010 = 1002.00
    sell 0.40 @ 2020: 808.00 - 1002.00 x 0.40/0.50 (801.60) = 6.40 -> 640
    sell 0.30 @ 2015: closes 0.10 (201.50 - 200.40 = 1.10 -> 110),
                      opens 0.20 short @ 2015
    buy 0.20 @ 2005:  (2015 - 2005) x 0.20 x 100 = 200
                                                                     total   950
Same total, as §2.10 requires; the orders differ, and that is the point.

COMMISSION (PC.2). Lots that OPEN: hedging 0.30 + 0.20 + 0.20 (ticket 3)
= 0.70, every close opening nothing; netting 0.30 + 0.20 + 0.20 (the
opening part of the 0.30 flip; its other 0.10 closes) = 0.70. Lots traded:
1.40 under both. So a round turn of 7.00 per lot on the opening part,
0.70 x 7.00 = 4.90, and a per-side 3.50 on every lot, 1.40 x 3.50 = 4.90,
both give 950.00 - 4.90 = 945.10, under either mode.

This is one concrete example, not the cross-convention property: that test
is the operator's (tests/properties/, PC.5).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from harness import run_backtest

from engine.core.types import Bar, Order, PositionMode, TargetPosition
from engine.costs.base import CostModel
from engine.costs.zero import ZeroCostModel

SYMBOL = "XAUUSD"
OPENS = ["1990.00", "2000.00", "2010.00", "2020.00", "2015.00", "2012.00", "2005.00"]
SCRIPT = ["0.30", "0.50", "0.10", "-0.20", "-0.20", "0"]  # decided at bars 0..5
_T0 = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
_W = timedelta(minutes=15)

D = Decimal
EXPECTED_ORDERS: Mapping[PositionMode, list[tuple]] = {
    "hedging": [
        ("buy", D("0.30"), None),
        ("buy", D("0.20"), None),
        ("sell", D("0.30"), "1"),
        ("sell", D("0.10"), "2"),
        ("sell", D("0.10"), "2"),
        ("sell", D("0.20"), None),
        ("buy", D("0.20"), "3"),
    ],
    "netting": [
        ("buy", D("0.30"), None),
        ("buy", D("0.20"), None),
        ("sell", D("0.40"), None),
        ("sell", D("0.30"), None),
        ("buy", D("0.20"), None),
    ],
}


class _Scripted:
    """A quantity target per bar, by bar index. Inline because the
    reference `ScriptedTargets` (§7.1) is built for the PC.5 exit."""

    warmup_bars = 0

    def __init__(self, script: Sequence[str]) -> None:
        self._script = list(script)
        self._seen = 0

    def on_bar(
        self,
        bar: Bar,  # noqa: ARG002 -- the strategy contract's arguments; a script needs none
        features: object,  # noqa: ARG002
        portfolio: object,  # noqa: ARG002
    ) -> list[TargetPosition]:
        index, self._seen = self._seen, self._seen + 1
        if index >= len(self._script):
            return []
        return [
            TargetPosition(
                symbol=SYMBOL,
                quantity=Decimal(self._script[index]),
                weight=None,
                stop_price=None,
                take_profit=None,
                reason="scripted",
                confidence=None,
            )
        ]


def _bars() -> list[Bar]:
    return [
        Bar(
            symbol=SYMBOL,
            ts_open=_T0 + k * _W,
            ts_close=_T0 + (k + 1) * _W,
            open=Decimal(price),
            high=Decimal(price),
            low=Decimal(price),
            close=Decimal(price),
            volume=Decimal(1),
            is_final=True,
            spread=Decimal(0),
        )
        for k, price in enumerate(OPENS)
    ]


class _RoundTurn(ZeroCostModel):
    """7.00 per lot, charged once, on the opening part of a fill."""

    def fees(self, order: Order, fill_price: Decimal, opening_quantity: Decimal) -> Decimal:  # noqa: ARG002
        return opening_quantity * Decimal("7.00")


class _PerSide(ZeroCostModel):
    """3.50 per lot on every fill, opening or closing."""

    def fees(self, order: Order, fill_price: Decimal, opening_quantity: Decimal) -> Decimal:  # noqa: ARG002
        return order.quantity * Decimal("3.50")


def _run(mode: PositionMode, cost_model: CostModel | None = None):
    return run_backtest(
        _bars(),
        _Scripted(SCRIPT),
        position_mode=mode,
        contract_sizes={SYMBOL: Decimal(100)},
        cost_model=cost_model,
    )


@pytest.mark.parametrize("mode", ["hedging", "netting"])
def test_the_orders_follow_the_modes_rules(mode: PositionMode) -> None:
    result = _run(mode)
    assert [(o.side, o.quantity, o.closes_ticket) for o in result.orders] == EXPECTED_ORDERS[
        mode
    ], result.describe()


@pytest.mark.parametrize("mode", ["hedging", "netting"])
def test_the_total_matches_the_hand_figure(mode: PositionMode) -> None:
    result = _run(mode)
    assert result.total_pnl == Decimal("950.00"), result.describe()
    assert result.unfilled_orders == ()


def test_hedging_fills_name_their_tickets() -> None:
    result = _run("hedging")
    assert [f.ticket for f in result.fills] == ["1", "2", "1", "2", "2", "3", "3"]


@pytest.mark.parametrize("mode", ["hedging", "netting"])
@pytest.mark.parametrize("commission", [_RoundTurn, _PerSide], ids=["round_turn", "per_side"])
def test_commission_is_the_same_under_either_mode(mode: PositionMode, commission: type) -> None:
    result = _run(mode, commission())
    assert sum(f.fees for f in result.fills) == Decimal("4.90"), result.describe()
    assert result.total_pnl == Decimal("945.10"), result.describe()
