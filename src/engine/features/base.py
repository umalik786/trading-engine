"""Feature pipeline protocol. See docs/trading-engine-architecture.md §2.3."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from engine.core.types import Bar


class FeatureSet(Protocol):
    def update(self, bar: Bar) -> None:
        """Ingest one bar. MUST be O(1) or O(window), never O(history)."""
        ...

    def snapshot(self) -> Mapping[str, Any]:
        """Current feature values. Contains NO forward-looking information."""
        ...

    @property
    def is_ready(self) -> bool:
        """False until enough bars have been ingested for all features to be valid."""
        ...
