"""Tests for the sizer. See docs/trading-engine-architecture.md §2.5."""

from __future__ import annotations

from decimal import Decimal

from engine.core.portfolio import Portfolio
from engine.core.types import TargetPosition
from engine.sizing.fixed import FixedQuantitySizer

SYMBOL = "XAUUSD"


def _portfolio() -> Portfolio:
    return Portfolio(starting_balance=Decimal(0), contract_sizes={SYMBOL: Decimal(100)})


def _target(quantity: str) -> TargetPosition:
    return TargetPosition(
        symbol=SYMBOL,
        quantity=Decimal(quantity),
        weight=None,
        stop_price=None,
        take_profit=None,
        reason="unit test",
        confidence=None,
    )


class TestFixedQuantitySizer:
    def test_it_returns_the_targets_own_quantity(self) -> None:
        sizer = FixedQuantitySizer()

        assert sizer.size(_target("2.5"), _portfolio(), {}) == Decimal("2.5")

    def test_it_preserves_a_short_targets_sign(self) -> None:
        """Direction belongs to the strategy. A sizer that flipped the
        sign would be originating a position rather than sizing one."""
        sizer = FixedQuantitySizer()

        assert sizer.size(_target("-2.5"), _portfolio(), {}) == Decimal("-2.5")

    def test_it_passes_a_flat_target_through_as_zero(self) -> None:
        sizer = FixedQuantitySizer()

        assert sizer.size(_target("0"), _portfolio(), {}) == Decimal(0)

    def test_it_ignores_the_book_and_the_features(self) -> None:
        """A pass-through must not depend on either, or the reference
        strategies' hand-computed figures would stop being predictable."""
        sizer = FixedQuantitySizer()
        flat = _portfolio()
        with_features = {"sma_20": Decimal("2000")}

        assert sizer.size(_target("1"), flat, {}) == sizer.size(_target("1"), flat, with_features)
