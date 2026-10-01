"""Tests for the reference strategies. See docs/trading-engine-architecture.md
§7.1.

These check the strategies honour the §2.4 contract -- constant targets,
no declared features, no warmup. What they are worth as engine tests is
measured end to end, in tests/golden/.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from engine.core.portfolio import Portfolio
from engine.core.types import Bar, Fill
from engine.strategies.reference.always_flat import AlwaysFlat
from engine.strategies.reference.always_long import AlwaysLong
from engine.strategies.reference.always_short import AlwaysShort

SYMBOL = "XAUUSD"
CONTRACT_SIZES = {SYMBOL: Decimal(100)}


def _bar(index: int, close: str) -> Bar:
    ts_open = datetime(2026, 1, 5, 0, 0, tzinfo=UTC) + index * timedelta(minutes=15)
    price = Decimal(close)
    return Bar(
        symbol=SYMBOL,
        ts_open=ts_open,
        ts_close=ts_open + timedelta(minutes=15),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal(1),
        is_final=True,
    )


def _portfolio() -> Portfolio:
    return Portfolio(starting_balance=Decimal(0), contract_sizes=CONTRACT_SIZES)


class TestAlwaysLong:
    def test_returns_the_configured_target_on_every_bar(self) -> None:
        strategy = AlwaysLong(symbol=SYMBOL, quantity=Decimal("2.5"))
        portfolio = _portfolio()

        for index, close in enumerate(["2000", "2100", "1900"]):
            targets = strategy.on_bar(_bar(index, close), {}, portfolio)
            assert len(targets) == 1
            assert targets[0].symbol == SYMBOL
            assert targets[0].quantity == Decimal("2.5")

    def test_the_target_is_unchanged_by_what_is_already_held(self) -> None:
        """A target position says where to be, not what to do, so it must
        not depend on the current book -- that is what lets the engine
        turn a constant target into exactly one order."""
        strategy = AlwaysLong(symbol=SYMBOL, quantity=Decimal(1))
        flat = _portfolio()
        holding = _portfolio()
        holding.apply_fill(
            Fill(
                order_id="o",
                client_order_id="c",
                symbol=SYMBOL,
                quantity=Decimal(1),
                price=Decimal("2000"),
                fees=Decimal(0),
                ts=datetime(2026, 1, 5, tzinfo=UTC),
            )
        )

        assert strategy.on_bar(_bar(0, "2000"), {}, flat) == strategy.on_bar(
            _bar(0, "2000"), {}, holding
        )

    def test_states_a_reason(self) -> None:
        """Every target is logged with its rationale (§2.9), including one
        this obvious."""
        strategy = AlwaysLong(symbol=SYMBOL, quantity=Decimal(1))
        assert strategy.on_bar(_bar(0, "2000"), {}, _portfolio())[0].reason

    def test_needs_no_features_and_no_warmup(self) -> None:
        strategy = AlwaysLong(symbol=SYMBOL, quantity=Decimal(1))
        assert strategy.required_features == set()
        assert strategy.warmup_bars == 0

    def test_zero_or_negative_size_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive lots"):
            AlwaysLong(symbol=SYMBOL, quantity=Decimal(0))
        with pytest.raises(ValueError, match="positive lots"):
            AlwaysLong(symbol=SYMBOL, quantity=Decimal(-1))

    def test_float_size_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="Decimal"):
            AlwaysLong(symbol=SYMBOL, quantity=1.0)  # type: ignore[arg-type]


class TestAlwaysShort:
    def test_returns_the_negative_of_the_configured_size_on_every_bar(self) -> None:
        strategy = AlwaysShort(symbol=SYMBOL, quantity=Decimal("2.5"))
        portfolio = _portfolio()

        for index, close in enumerate(["2000", "2100", "1900"]):
            targets = strategy.on_bar(_bar(index, close), {}, portfolio)
            assert len(targets) == 1
            assert targets[0].symbol == SYMBOL
            assert targets[0].quantity == Decimal("-2.5")

    def test_the_target_is_negative_whatever_the_price_does(self) -> None:
        """A rising market does not turn this strategy long. The sign is a
        property of the strategy, not of the data."""
        strategy = AlwaysShort(symbol=SYMBOL, quantity=Decimal(1))
        portfolio = _portfolio()

        for index, close in enumerate(["2000", "2400", "1600", "2800"]):
            assert strategy.on_bar(_bar(index, close), {}, portfolio)[0].quantity < 0

    def test_the_target_is_unchanged_by_what_is_already_held(self) -> None:
        """A target position says where to be, not what to do, so it must
        not depend on the current book -- that is what lets the engine
        turn a constant target into exactly one order."""
        strategy = AlwaysShort(symbol=SYMBOL, quantity=Decimal(1))
        flat = _portfolio()
        holding = _portfolio()
        holding.apply_fill(
            Fill(
                order_id="o",
                client_order_id="c",
                symbol=SYMBOL,
                quantity=Decimal(-1),
                price=Decimal("2000"),
                fees=Decimal(0),
                ts=datetime(2026, 1, 5, tzinfo=UTC),
            )
        )

        assert strategy.on_bar(_bar(0, "2000"), {}, flat) == strategy.on_bar(
            _bar(0, "2000"), {}, holding
        )

    def test_states_a_reason(self) -> None:
        strategy = AlwaysShort(symbol=SYMBOL, quantity=Decimal(1))
        assert strategy.on_bar(_bar(0, "2000"), {}, _portfolio())[0].reason

    def test_needs_no_features_and_no_warmup(self) -> None:
        strategy = AlwaysShort(symbol=SYMBOL, quantity=Decimal(1))
        assert strategy.required_features == set()
        assert strategy.warmup_bars == 0

    def test_zero_or_negative_size_is_rejected(self) -> None:
        """A negative argument is rejected rather than accepted as "short
        one lot": the caller passes how many lots to be short, and the
        strategy applies the sign. Accepting both would make
        AlwaysShort(-1) and AlwaysShort(1) equally plausible at the call
        site while meaning different things."""
        with pytest.raises(ValueError, match="positive lots"):
            AlwaysShort(symbol=SYMBOL, quantity=Decimal(0))
        with pytest.raises(ValueError, match="positive lots"):
            AlwaysShort(symbol=SYMBOL, quantity=Decimal(-1))

    def test_float_size_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="Decimal"):
            AlwaysShort(symbol=SYMBOL, quantity=1.0)  # type: ignore[arg-type]

    def test_it_is_the_exact_mirror_of_always_long(self) -> None:
        """The two differ in the sign of the target and nothing else."""
        long_target = AlwaysLong(symbol=SYMBOL, quantity=Decimal(2)).on_bar(
            _bar(0, "2000"), {}, _portfolio()
        )[0]
        short_target = AlwaysShort(symbol=SYMBOL, quantity=Decimal(2)).on_bar(
            _bar(0, "2000"), {}, _portfolio()
        )[0]

        assert short_target.quantity == -long_target.quantity
        assert short_target.symbol == long_target.symbol
        assert short_target.stop_price == long_target.stop_price
        assert short_target.take_profit == long_target.take_profit
        assert short_target.confidence == long_target.confidence


class TestAlwaysFlat:
    def test_targets_zero_lots_on_every_bar(self) -> None:
        strategy = AlwaysFlat(symbol=SYMBOL)
        portfolio = _portfolio()

        for index, close in enumerate(["2000", "2400", "1600"]):
            targets = strategy.on_bar(_bar(index, close), {}, portfolio)
            assert len(targets) == 1
            assert targets[0].quantity == Decimal(0)

    def test_returns_a_zero_target_rather_than_an_empty_list(self) -> None:
        """An empty list means "no change from current" (§2.4). Zero lots
        means "be flat", which is a claim the engine can act on."""
        targets = AlwaysFlat(symbol=SYMBOL).on_bar(_bar(0, "2000"), {}, _portfolio())
        assert targets != []

    def test_needs_no_features_and_no_warmup(self) -> None:
        strategy = AlwaysFlat(symbol=SYMBOL)
        assert strategy.required_features == set()
        assert strategy.warmup_bars == 0
