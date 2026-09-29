"""Strategy plugin protocol. See docs/trading-engine-architecture.md §2.4.

This protocol is the whole of what the engine knows about a strategy. P3:
the engine imports no strategy module, has no knowledge of indicators,
regimes, levels or setups, and loads real strategies by import string from
configuration.

TARGET POSITIONS, NOT TRADES. `on_bar` returns where the strategy wants to
be, not what it wants to do. The engine works out the difference between
that and where it actually is, and that difference -- if any -- is the
order. A strategy that wants to stay long returns the same target on every
bar and produces exactly one order at the start of the run, with no
"am I already in?" bookkeeping of its own.

This also makes a duplicate fill self-correcting rather than catastrophic
(Appendix A.5): the next bar's target is unchanged, so the engine sees the
oversized position and trims it. It costs the spread twice; it does not
leave silent double size.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from engine.core.portfolio import PortfolioView
from engine.core.types import Bar, TargetPosition


class Strategy(Protocol):
    def on_bar(
        self,
        bar: Bar,
        features: Mapping[str, Any],
        portfolio: PortfolioView,
    ) -> list[TargetPosition]:
        """Return desired positions. Empty list = no change from current.

        Called once per final bar, at that bar's close.

        MUST be a pure function of its arguments.
        MUST NOT: read the clock, perform I/O, call a broker, mutate global
                  state, or use randomness without an injected seeded
                  generator.

        The purity constraint is what makes everything else possible: the
        strategy is testable in isolation, identical in backtest and live,
        and replayable. Reading the clock is the subtle one -- a strategy
        that asks what time it is behaves differently in a replay of
        January than it did in January.
        """
        ...

    @property
    def required_features(self) -> set[str]:
        """Declared upfront so the engine can validate wiring at startup."""
        ...

    @property
    def warmup_bars(self) -> int:
        """How many bars before the strategy should be allowed to trade."""
        ...
