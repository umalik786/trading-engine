from __future__ import annotations

import random
from datetime import UTC, datetime
from decimal import Decimal
from itertools import islice

from engine.core.types import Bar
from engine.feeds.replay import ReplayFeed
from engine.features.technical import SimpleMovingAverage

SHUFFLE_SEED = 20260128  # arbitrary, fixed -- reproducibility is the point
SHUFFLE_FROM = 500      # bars from here on are shuffled
RECORD_THROUGH = 500    # snapshots recorded for the comparison
PERIOD = 50


def load_first_1000_bars() -> list[Bar]:
    """First 1000 XAUUSD M15 bars at or after 2026-01-01T00:00:00Z."""
    feed = ReplayFeed(
        instrument="XAUUSD",
        timeframe="M15",
        range_start=datetime(2026, 1, 1, tzinfo=UTC),
        range_end=datetime(2026, 3, 1, tzinfo=UTC),  # comfortably >1000 M15 bars
    )
    bars = list(islice(feed.stream(), 1000))
    if len(bars) != 1000:
        raise AssertionError(
            f"expected 1000 bars starting 2026-01-01, got {len(bars)} -- "
            "widen range_end or check the data"
        )
    return bars


class CleanIndicator:
    """Adapter around the REAL `SimpleMovingAverage`, not a reimplementation.

    Adds no indicator logic of its own: update() and the SMA computation
    are entirely the shipped engine.features.technical class. This only
    unwraps its snapshot dict down to the single "sma_50" value, so
    run_instance's uniform update()/snapshot() shape works the same for
    both Clean and Leaky.
    """

    def __init__(self, period: int = PERIOD) -> None:
        self._sma = SimpleMovingAverage(period=period)
        self._key = f"sma_{period}"

    def update(self, bar: Bar) -> None:
        self._sma.update(bar)

    def snapshot(self) -> Decimal | None:
        return self._sma.snapshot()[self._key]


class LeakyMovingAverage:
    """Deliberately acausal mutant: constructed with the FULL bar list up
    front. At the Nth update() call, snapshot() averages closes of bars
    N+1..N+period from that list -- bars update() has not been given yet.
    This is what the future-shuffle test exists to catch."""

    def __init__(self, all_bars: list[Bar], period: int = PERIOD) -> None:
        self._all_bars = all_bars
        self._period = period
        self._n = 0  # count of update() calls so far

    def update(self, bar: Bar) -> None:
        self._n += 1

    def snapshot(self) -> Decimal | None:
        window = self._all_bars[self._n : self._n + self._period]
        if len(window) < self._period:
            return None  # matches SimpleMovingAverage's not-ready convention
        return sum((b.close for b in window), Decimal(0)) / self._period


def run_instance(bars: list[Bar], indicator: object, record_through: int) -> list[Decimal | None]:
    """Feed every bar in `bars`, in order, through `indicator`, recording
    snapshot() after each of the first `record_through` update() calls."""
    snapshots: list[Decimal | None] = []
    for i, bar in enumerate(bars):
        indicator.update(bar)  # type: ignore[attr-defined]
        if i < record_through:
            snapshots.append(indicator.snapshot())  # type: ignore[attr-defined]
    return snapshots


def shuffled_future(bars: list[Bar], split: int, seed: int) -> list[Bar]:
    """bars[:split] unchanged; bars[split:] shuffled with a fixed seed."""
    past = bars[:split]
    future = bars[split:]
    shuffled = future.copy()
    random.Random(seed).shuffle(shuffled)
    return past + shuffled


def test_clean_indicator_is_unaffected_by_future_shuffle() -> None:
    bars = load_first_1000_bars()
    shuffled_bars = shuffled_future(bars, split=SHUFFLE_FROM, seed=SHUFFLE_SEED)

    instance_a = CleanIndicator(period=PERIOD)
    instance_b = CleanIndicator(period=PERIOD)  # fresh, no shared state

    snapshots_a = run_instance(bars, instance_a, record_through=RECORD_THROUGH)
    snapshots_b = run_instance(shuffled_bars, instance_b, record_through=RECORD_THROUGH)

    # Guard against an empty comparison silently passing.
    assert len(snapshots_a) == RECORD_THROUGH
    assert len(snapshots_b) == RECORD_THROUGH

    assert snapshots_a == snapshots_b


def test_leaky_indicator_is_caught_by_future_shuffle() -> None:
    bars = load_first_1000_bars()
    shuffled_bars = shuffled_future(bars, split=SHUFFLE_FROM, seed=SHUFFLE_SEED)

    instance_a = LeakyMovingAverage(bars, period=PERIOD)
    instance_b = LeakyMovingAverage(shuffled_bars, period=PERIOD)  # fresh, no shared state

    snapshots_a = run_instance(bars, instance_a, record_through=RECORD_THROUGH)
    snapshots_b = run_instance(shuffled_bars, instance_b, record_through=RECORD_THROUGH)

    assert len(snapshots_a) == RECORD_THROUGH
    assert len(snapshots_b) == RECORD_THROUGH

    boundary = RECORD_THROUGH - PERIOD  # 450: last N whose N+1..N+50 window stays inside bars 1-500
    identical_a, differing_a = snapshots_a[:boundary], snapshots_a[boundary:]
    identical_b, differing_b = snapshots_b[:boundary], snapshots_b[boundary:]

    # Guard against an empty comparison silently passing.
    assert len(identical_a) == boundary
    assert len(differing_a) == PERIOD

    assert identical_a == identical_b
    assert all(a != b for a, b in zip(differing_a, differing_b, strict=True))


if __name__ == "__main__":
    test_clean_indicator_is_unaffected_by_future_shuffle()
    print("Clean indicator: PASS -- all 500 snapshots identical under future shuffle")
    test_leaky_indicator_is_caught_by_future_shuffle()
    print("Leaky indicator: PASS -- snapshots 1-450 identical, 451-500 differ")
