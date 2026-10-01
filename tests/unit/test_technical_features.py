"""Tests for the streaming technical indicators. See
docs/trading-engine-architecture.md §2.3.

The SMA and ATR fixtures below are hand-calculated -- the arithmetic is
written out in each test as a comment, verifiable with a calculator,
independent of technical.py's own implementation.
"""

from __future__ import annotations

import gc
import tracemalloc
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from engine.core.types import Bar
from engine.features.technical import AverageTrueRange, SimpleMovingAverage, TechnicalFeatureSet

_BASE_TS = datetime(2024, 1, 2, 0, 0, tzinfo=UTC)
_BAR_WIDTH = timedelta(minutes=15)


def _bar(index: int, open_: str, high: str, low: str, close: str) -> Bar:
    ts_open = _BASE_TS + index * _BAR_WIDTH
    return Bar(
        symbol="TEST",
        ts_open=ts_open,
        ts_close=ts_open + _BAR_WIDTH,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(1),
        is_final=True,
        spread=Decimal("0.20"),
    )


# --- SMA(3) fixture -- closes chosen as multiples of 3 so every 3-bar sum
# divides evenly, keeping the arithmetic exact rather than repeating. ---
_SMA_BARS = [
    _bar(0, "9", "10", "8", "9"),
    _bar(1, "12", "13", "11", "12"),
    _bar(2, "15", "16", "14", "15"),
    _bar(3, "12", "13", "11", "12"),
    _bar(4, "9", "10", "8", "9"),
    _bar(5, "15", "16", "14", "15"),
]

# --- ATR(2) fixture -- period 2 keeps every division exact (base-10
# division by 2 always terminates), so the whole series is hand-checkable
# without repeating decimals. ---
_ATR_BARS = [
    _bar(0, "100", "105", "95", "100"),
    _bar(1, "103", "108", "98", "103"),
    _bar(2, "107", "110", "104", "107"),
    _bar(3, "108", "112", "105", "108"),
    _bar(4, "105", "109", "103", "105"),
]


class TestSmaHandCalculated:
    """period=3, closes = [9, 12, 15, 12, 9, 15].

    SMA at bar k (1-indexed) is the mean of closes[k-3:k]:
        bar3: (9 + 12 + 15) / 3  = 36 / 3 = 12
        bar4: (12 + 15 + 12) / 3 = 39 / 3 = 13
        bar5: (15 + 12 + 9) / 3  = 36 / 3 = 12
        bar6: (12 + 9 + 15) / 3  = 36 / 3 = 12
    """

    def test_hand_calculated_values(self) -> None:
        sma = SimpleMovingAverage(period=3)
        expected = [None, None, Decimal(12), Decimal(13), Decimal(12), Decimal(12)]

        for bar, expected_value in zip(_SMA_BARS, expected, strict=True):
            sma.update(bar)
            assert sma.snapshot()["sma_3"] == expected_value


class TestAtrHandCalculated:
    """period=2, bars (high, low, close):
        bar1: 105, 95, 100
        bar2: 108, 98, 103
        bar3: 110, 104, 107
        bar4: 112, 105, 108
        bar5: 109, 103, 105

    True range:
        tr1 = high1 - low1 = 105 - 95 = 10                          (no prior close)
        tr2 = max(108-98, |108-100|, |98-100|)  = max(10, 8, 2) = 10
        tr3 = max(110-104, |110-103|, |104-103|) = max(6, 7, 1)  = 7
        tr4 = max(112-105, |112-107|, |105-107|) = max(7, 5, 2)  = 7
        tr5 = max(109-103, |109-108|, |103-108|) = max(6, 1, 5)  = 6

    Seed at bar2 (mean of tr1, tr2): (10 + 10) / 2 = 10
    Wilder smoothing, atr[t] = (atr[t-1] * (period-1) + tr[t]) / period, period=2:
        atr3 = (10 * 1 + 7) / 2 = 17 / 2   = 8.5
        atr4 = (8.5 * 1 + 7) / 2 = 15.5 / 2 = 7.75
        atr5 = (7.75 * 1 + 6) / 2 = 13.75 / 2 = 6.875
    """

    def test_hand_calculated_values(self) -> None:
        atr = AverageTrueRange(period=2)
        expected = [None, Decimal(10), Decimal("8.5"), Decimal("7.75"), Decimal("6.875")]

        for bar, expected_value in zip(_ATR_BARS, expected, strict=True):
            atr.update(bar)
            assert atr.snapshot()["atr_2"] == expected_value


class TestIsReadyBoundary:
    def test_sma_false_at_w_minus_1_true_at_w(self) -> None:
        sma = SimpleMovingAverage(period=3)
        sma.update(_SMA_BARS[0])
        sma.update(_SMA_BARS[1])
        assert sma.is_ready is False  # 2 bars ingested, W=3

        sma.update(_SMA_BARS[2])
        assert sma.is_ready is True  # 3rd bar ingested

    def test_atr_false_at_w_minus_1_true_at_w(self) -> None:
        atr = AverageTrueRange(period=2)
        atr.update(_ATR_BARS[0])
        assert atr.is_ready is False  # 1 bar ingested, W=2

        atr.update(_ATR_BARS[1])
        assert atr.is_ready is True  # 2nd bar ingested

    def test_composite_ready_only_once_every_member_is_ready(self) -> None:
        composite = TechnicalFeatureSet(
            [SimpleMovingAverage(period=3), AverageTrueRange(period=2)]
        )
        composite.update(_SMA_BARS[0])
        composite.update(_SMA_BARS[1])
        # ATR(2) is ready after 2 bars, but SMA(3) is not -- composite must
        # reflect the slower member, not the faster one.
        assert composite.is_ready is False

        composite.update(_SMA_BARS[2])
        assert composite.is_ready is True


class TestComposite:
    def test_snapshot_merges_member_outputs(self) -> None:
        composite = TechnicalFeatureSet(
            [SimpleMovingAverage(period=3), AverageTrueRange(period=2)]
        )
        for bar in _SMA_BARS[:3]:
            composite.update(bar)

        snapshot = composite.snapshot()
        assert set(snapshot.keys()) == {"sma_3", "atr_2"}
        assert snapshot["sma_3"] == Decimal(12)


class TestNoForwardLookingInformation:
    def test_snapshot_at_step_k_unaffected_by_later_bars(self) -> None:
        # Record the snapshot after every bar in a full run...
        full_run = SimpleMovingAverage(period=3)
        snapshots_by_step: list[Decimal | None] = []
        for bar in _SMA_BARS:
            full_run.update(bar)
            snapshots_by_step.append(full_run.snapshot()["sma_3"])

        # ...then build a second, independent instance that only ever sees
        # the first 4 bars, and confirm it agrees with what was already
        # recorded at that step in the full run -- feeding bars 5 and 6
        # afterward must not retroactively change what step 4 already saw.
        prefix_only = SimpleMovingAverage(period=3)
        for bar in _SMA_BARS[:4]:
            prefix_only.update(bar)

        assert prefix_only.snapshot()["sma_3"] == snapshots_by_step[3]

    def test_feeding_the_same_bars_twice_gives_identical_output(self) -> None:
        composite_a = TechnicalFeatureSet(
            [SimpleMovingAverage(period=3), AverageTrueRange(period=2)]
        )
        composite_b = TechnicalFeatureSet(
            [SimpleMovingAverage(period=3), AverageTrueRange(period=2)]
        )
        for bar in _SMA_BARS:
            composite_a.update(bar)
        for bar in _SMA_BARS:
            composite_b.update(bar)

        assert composite_a.snapshot() == composite_b.snapshot()


class TestMemoryBoundedness:
    def test_sma_window_does_not_grow_with_bars_ingested(self) -> None:
        sma = SimpleMovingAverage(period=20)
        ts = _BASE_TS
        for i in range(5000):
            bar = Bar(
                symbol="TEST",
                ts_open=ts,
                ts_close=ts + _BAR_WIDTH,
                open=Decimal(100 + i % 7),
                high=Decimal(105 + i % 7),
                low=Decimal(95 + i % 7),
                close=Decimal(100 + i % 7),
                volume=Decimal(1),
                is_final=True,
                spread=Decimal("0.20"),
            )
            sma.update(bar)
            ts += _BAR_WIDTH

        assert len(sma._window) == 20  # structural check, this is the point

    def test_peak_memory_does_not_scale_with_bars_ingested(self) -> None:
        def feed(n: int) -> int:
            gc.collect()
            tracemalloc.start()
            composite = TechnicalFeatureSet(
                [SimpleMovingAverage(period=20), AverageTrueRange(period=14)]
            )
            ts = _BASE_TS
            for i in range(n):
                bar = Bar(
                    symbol="TEST",
                    ts_open=ts,
                    ts_close=ts + _BAR_WIDTH,
                    open=Decimal(100 + i % 7),
                    high=Decimal(105 + i % 7),
                    low=Decimal(95 + i % 7),
                    close=Decimal(100 + i % 7),
                    volume=Decimal(1),
                    is_final=True,
                    spread=Decimal("0.20"),
                )
                composite.update(bar)
                ts += _BAR_WIDTH
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            return peak

        small_peak = feed(200)
        large_peak = feed(20_000)

        # Not an exact-equality claim -- allocator/bookkeeping noise means
        # these will never match exactly. The claim is that peak memory
        # for 100x the bars is nowhere near 100x the size.
        assert large_peak < small_peak * 3
