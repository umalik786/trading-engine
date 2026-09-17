"""Feed adapter protocol. See docs/trading-engine-architecture.md §2.2."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from engine.core.types import Bar


class Feed(Protocol):
    def stream(self) -> Iterator[Bar]:
        """Yield final bars in strictly ascending ts_close order.

        ReplayFeed: reads historical data from disk/API.
        LiveFeed:   blocks until each bar closes, then yields.

        Both MUST yield identical Bar objects for the same market period.
        Neither may yield a bar whose ts_close is in the future.
        """
        ...

    def warmup(self, n: int) -> list[Bar]:
        """Bars before the run start, for feature initialisation only.
        These are never passed to the strategy."""
        ...
