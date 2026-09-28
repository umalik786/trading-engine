"""Streaming technical indicators. See docs/trading-engine-architecture.md
§2.3 (FeatureSet protocol), P2 in §1 (causality by construction) and
Appendix B.6 (no gap-filling -- what that implies for rolling windows).

Every indicator here is fed one bar at a time through `update()` and reads
nothing else -- no reference to a full dataset, no lookahead, no history
buffer beyond its own bounded window. That is what makes the streaming
contract genuine rather than a convention: a component that only ever sees
`update(bar)` calls, one at a time, in the order the engine makes them,
cannot see a bar it hasn't been given yet.

WINDOWS ARE OVER BARS, NOT CLOCK TIME (Appendix B.6). Stored data is never
gap-filled -- weekends, holidays and index session breaks are absent rows,
not synthesised ones. A period-N window here is the last N bars actually
ingested, however much or little clock time separates them. Neither
indicator below assumes or requires even spacing between bars; both are
well-defined across an arbitrary gap. If a future indicator's meaning DID
depend on even spacing (e.g. anything annualising a per-bar quantity by
assuming a fixed bars-per-day), that assumption would need to be stated
explicitly and the gap handled on purpose -- neither SMA nor ATR needs
that here.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from engine.core.types import Bar
from engine.features.base import FeatureSet


class SimpleMovingAverage:
    """Simple moving average of close, over the last `period` bars.

    Bounded rolling window: a `deque(maxlen=period)` holds only the closes
    currently in the window, and a running sum is maintained incrementally
    (added to on arrival, subtracted from on eviction) so `update()` is
    O(1) per bar rather than O(period) -- never O(history), per §2.3.

    The window is a window over BARS, not clock time -- see the module
    docstring. A 20-bar SMA spanning a weekend averages the 20 actual bars
    on either side of the gap; it makes no claim about elapsed time and
    needs none, since it is simply the mean of the last `period` closes
    this instance has been shown, whatever gap separates them.
    """

    def __init__(self, period: int) -> None:
        if period <= 0:
            raise ValueError(f"period must be positive, got {period}")
        self._period = period
        self._key = f"sma_{period}"
        self._window: deque[Decimal] = deque(maxlen=period)
        self._sum = Decimal(0)

    def update(self, bar: Bar) -> None:
        if len(self._window) == self._period:
            self._sum -= self._window[0]
        self._window.append(bar.close)
        self._sum += bar.close

    def snapshot(self) -> Mapping[str, Any]:
        if not self.is_ready:
            return {self._key: None}
        return {self._key: self._sum / self._period}

    @property
    def is_ready(self) -> bool:
        return len(self._window) == self._period


class AverageTrueRange:
    """Wilder's Average True Range over `period` bars.

    True range needs the previous bar's close, so this indicator carries
    state beyond a plain rolling window: it remembers the last close it
    saw, not just the values inside a window.

    SEEDING RULE -- a deliberate choice, stated explicitly rather than left
    implicit. Spec §12 names "how ta.atr seeds its first value" as one of
    the three places a Pine-to-Python parity check fails first; an
    unstated seeding choice here would be exactly that trap, discovered
    only when a parity check disagreed with no explanation on hand.

    - The first bar ever ingested has no previous close, so its true range
      is simply high - low (the only leg that can be computed).
    - Once `period` bars have been ingested, ATR is seeded as the simple
      arithmetic mean of those `period` true-range values. This matches
      Wilder's original method, and matches the seeding TradingView's
      `ta.rma` uses (which `ta.atr` is built on).
    - Every bar after that uses Wilder's smoothing, not a plain moving
      average of true range:
          atr[t] = (atr[t-1] * (period - 1) + tr[t]) / period
      A different, equally defensible seeding choice -- e.g. seeding from
      only the first bar's true range and smoothing from bar 2 -- would
      produce a different numeric series from this point on. If this is
      ever checked against a Pine `ta.atr` reference for parity, this
      seeding rule is the first place to compare.

    Window is over BARS, not clock time -- see the module docstring. True
    range is simply the bar-to-bar move; it is well-defined across a gap
    of any size and makes no assumption of even spacing.
    """

    def __init__(self, period: int) -> None:
        if period <= 0:
            raise ValueError(f"period must be positive, got {period}")
        self._period = period
        self._key = f"atr_{period}"
        self._previous_close: Decimal | None = None
        self._seed_window: list[Decimal] = []
        self._atr: Decimal | None = None

    def update(self, bar: Bar) -> None:
        if self._previous_close is None:
            true_range = bar.high - bar.low
        else:
            true_range = max(
                bar.high - bar.low,
                abs(bar.high - self._previous_close),
                abs(bar.low - self._previous_close),
            )
        self._previous_close = bar.close

        if self._atr is None:
            self._seed_window.append(true_range)
            if len(self._seed_window) == self._period:
                self._atr = sum(self._seed_window, Decimal(0)) / self._period
                self._seed_window = []  # no longer needed once seeded
        else:
            self._atr = (self._atr * (self._period - 1) + true_range) / self._period

    def snapshot(self) -> Mapping[str, Any]:
        return {self._key: self._atr}

    @property
    def is_ready(self) -> bool:
        return self._atr is not None


class TechnicalFeatureSet:
    """A FeatureSet composed of several member indicators.

    `update()` forwards each bar to every member, in the order given.
    `snapshot()` merges every member's own snapshot into one flat mapping
    -- each indicator names its own key(s) (e.g. "sma_20", "atr_14"), so
    the composite does no renaming of its own; two members that happen to
    produce the same key overwrite each other exactly as a plain dict
    merge would, and choosing distinct keys is the caller's responsibility.

    `is_ready` is true only once every member reports ready -- the
    composite reflects whether ALL the features it offers are valid, not
    some of them.
    """

    def __init__(self, features: Iterable[FeatureSet]) -> None:
        self._features = list(features)

    def update(self, bar: Bar) -> None:
        for feature in self._features:
            feature.update(bar)

    def snapshot(self) -> Mapping[str, Any]:
        merged: dict[str, Any] = {}
        for feature in self._features:
            merged.update(feature.snapshot())
        return merged

    @property
    def is_ready(self) -> bool:
        return all(feature.is_ready for feature in self._features)
