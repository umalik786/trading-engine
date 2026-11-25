"""Tests for the sizers. See docs/trading-engine-architecture.md §2.5.

Phase 3c.3 rules, approved 2026-11-23 (docs/state.md, 3c.3). Every figure is
worked by hand beside it, on a test instrument whose volume minimum, step
and maximum all differ -- the real venue's are 0.01 / 0.01, which cannot tell
a step from a minimum:

    contract size 100, volume minimum 0.10, step 0.05, maximum 5.00

With equity 100,000 and a close of 2000, one unit of weight is
    100,000 / (100 x 2000) = 0.5 lots
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from engine.core.instruments import InstrumentSpec
from engine.core.portfolio import Portfolio, Position
from engine.core.types import Bar, TargetPosition
from engine.sizing.base import SizingContext
from engine.sizing.equity import EquitySizer, SizingConfig, load_sizing_config
from engine.sizing.fixed import FixedQuantitySizer

SYMBOL = "XAUUSD"
SPEC = InstrumentSpec(
    contract_size=Decimal(100),
    point=Decimal("0.01"),
    volume_min=Decimal("0.10"),
    volume_step=Decimal("0.05"),
    volume_max=Decimal("5.00"),
)
TS = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)


class Book:
    """A PortfolioView with balance and equity set directly, so a test can
    make them differ without staging fills."""

    def __init__(self, equity: str = "100000", balance: str = "100000") -> None:
        self._equity = Decimal(equity)
        self._balance = Decimal(balance)

    @property
    def balance(self) -> Decimal:
        return self._balance

    @property
    def equity(self) -> Decimal:
        return self._equity

    def position_quantity(self, symbol: str) -> Decimal:  # noqa: ARG002
        return Decimal(0)

    def positions(self) -> Mapping[str, Position]:
        return {}


def _bar(open_: str = "2000", close: str = "2000") -> Bar:
    o, c = Decimal(open_), Decimal(close)
    return Bar(
        symbol=SYMBOL,
        ts_open=TS,
        ts_close=TS + timedelta(minutes=15),
        open=o,
        high=max(o, c),
        low=min(o, c),
        close=c,
        volume=Decimal(1),
        is_final=True,
        spread=Decimal("0.20"),
    )


def _target(quantity=None, weight=None, stop=None) -> TargetPosition:
    return TargetPosition(
        symbol=SYMBOL,
        quantity=None if quantity is None else Decimal(quantity),
        weight=None if weight is None else Decimal(weight),
        stop_price=None if stop is None else Decimal(stop),
        take_profit=None,
        reason="unit test",
        confidence=None,
    )


def _context(bar: Bar | None = None, committed: str = "0", spec=SPEC) -> SizingContext:
    return SizingContext(bar=bar or _bar(), committed=Decimal(committed), spec=spec)


def _sizer(risk: str = "0.01") -> EquitySizer:
    return EquitySizer(SizingConfig(risk_fraction=Decimal(risk)))


def _size(  # noqa: PLR0913 -- one keyword per input a test varies
    target, *, book=None, bar=None, committed="0", sizer=None, spec=SPEC
) -> Decimal:
    sizer = sizer or _sizer()
    return sizer.size(target, book or Book(), {}, _context(bar, committed, spec))


# --- FixedQuantitySizer (unchanged behaviour, new contract) -------------------


def _portfolio() -> Portfolio:
    return Portfolio(
        starting_balance=Decimal(0), contract_sizes={SYMBOL: Decimal(100)}, position_mode="netting"
    )


class TestFixedQuantitySizer:
    def test_it_returns_the_targets_own_quantity(self) -> None:
        sizer = FixedQuantitySizer()
        assert sizer.size(_target("2.5"), _portfolio(), {}, _context()) == Decimal("2.5")

    def test_it_preserves_a_short_targets_sign(self) -> None:
        """Direction belongs to the strategy. A sizer that flipped the
        sign would be originating a position rather than sizing one."""
        sizer = FixedQuantitySizer()
        assert sizer.size(_target("-2.5"), _portfolio(), {}, _context()) == Decimal("-2.5")

    def test_it_passes_a_flat_target_through_as_zero(self) -> None:
        sizer = FixedQuantitySizer()
        assert sizer.size(_target("0"), _portfolio(), {}, _context()) == Decimal(0)

    def test_it_ignores_the_book_and_the_features(self) -> None:
        """A pass-through must not depend on either, or the reference
        strategies' hand-computed figures would stop being predictable."""
        sizer = FixedQuantitySizer()
        flat = _portfolio()
        with_features = {"sma_20": Decimal("2000")}
        assert sizer.size(_target("1"), flat, {}, _context()) == sizer.size(
            _target("1"), flat, with_features, _context()
        )

    def test_it_does_not_round_or_limit(self) -> None:
        """Unchanged from phase 2: the quantity asked for is the quantity
        ordered. 0.07 is below the test minimum and off its step."""
        sizer = FixedQuantitySizer()
        assert sizer.size(_target("0.07"), _portfolio(), {}, _context()) == Decimal("0.07")

    def test_it_refuses_a_weight(self) -> None:
        """A weight needs converting to lots, which a pass-through cannot do."""
        with pytest.raises(ValueError, match="weight"):
            FixedQuantitySizer().size(_target(weight="1"), _portfolio(), {}, _context())


# --- EquitySizer: weight -----------------------------------------------------


class TestWeight:
    def test_weight_converts_equity_to_lots(self) -> None:
        # 1 x 100,000 / (100 x 2000) = 0.50 exactly.
        assert _size(_target(weight="1")) == Decimal("0.50")

    def test_rounds_down_to_the_step_not_to_nearest(self) -> None:
        # 1.19 x 0.5 = 0.595 = 11.9 steps -> 11 -> 0.55 (nearest would be 0.60).
        assert _size(_target(weight="1.19")) == Decimal("0.55")

    def test_sizes_from_the_deciding_bars_close_not_its_open(self) -> None:
        # Close 2500: 100,000 / 250,000 = 0.40. The open, 2000, would give 0.50.
        assert _size(_target(weight="1"), bar=_bar(open_="2000", close="2500")) == Decimal("0.40")

    def test_a_short_keeps_its_sign(self) -> None:
        assert _size(_target(weight="-1")) == Decimal("-0.50")

    def test_a_short_rounds_toward_zero(self) -> None:
        # -0.595 -> -0.55, not -0.60: smaller in size, as for a long.
        assert _size(_target(weight="-1.19")) == Decimal("-0.55")

    def test_uses_equity_not_balance(self) -> None:
        # Equity 120,000: 120,000 / 200,000 = 0.60. Balance would give 0.50.
        book = Book(equity="120000", balance="100000")
        assert _size(_target(weight="1"), book=book) == Decimal("0.60")

    def test_a_zero_weight_is_flat(self) -> None:
        assert _size(_target(weight="0")) == Decimal(0)


# --- EquitySizer: stop (risk-based) ------------------------------------------


class TestStop:
    def test_long_risk_formula(self) -> None:
        # 0.01 x 100,000 / (100 x |2000 - 1980|) = 1000 / 2000 = 0.50.
        assert _size(_target(weight="1", stop="1980")) == Decimal("0.50")

    def test_short_risk_formula(self) -> None:
        assert _size(_target(weight="-1", stop="2020")) == Decimal("-0.50")

    @pytest.mark.parametrize(
        ("weight", "stop"),
        [("0.3", "1980"), ("2", "1980"), ("-0.5", "2020"), ("-1.0001", "2020")],
        ids=["long-0.3", "long-2", "short-0.5", "short-1.0001"],
    )
    def test_a_stop_with_a_weight_other_than_plus_or_minus_one_is_refused(
        self, weight: str, stop: str
    ) -> None:
        # Operator, 2026-11-23 (decision C): a stop sizes by risk, so a weight
        # other than +1 or -1 would be a second answer to "how big".
        with pytest.raises(ValueError, match="two answers"):
            _size(_target(weight=weight, stop=stop))

    def test_a_stop_with_a_weight_of_exactly_one_written_differently_is_accepted(self) -> None:
        # 1.00 is +1: the rule is about the value, not how it is written.
        assert _size(_target(weight="1.00", stop="1980")) == Decimal("0.50")

    def test_risk_rounds_down(self) -> None:
        # 1000 / (100 x 17) = 0.588... = 11.76 steps -> 0.55.
        assert _size(_target(weight="1", stop="1983")) == Decimal("0.55")

    def test_risk_uses_the_close_not_the_open(self) -> None:
        # Close 2020, stop 2000: 1000 / (100 x 20) = 0.50. The open (2000)
        # would make the distance zero.
        bar = _bar(open_="2000", close="2020")
        assert _size(_target(weight="1", stop="2000"), bar=bar) == Decimal("0.50")

    def test_risk_uses_equity(self) -> None:
        # 0.01 x 120,000 / 2000 = 0.60.
        book = Book(equity="120000", balance="100000")
        assert _size(_target(weight="1", stop="1980"), book=book) == Decimal("0.60")

    def test_risk_fraction_comes_from_config(self) -> None:
        # 0.02 x 100,000 / 2000 = 1.00.
        assert _size(_target(weight="1", stop="1980"), sizer=_sizer("0.02")) == Decimal("1.00")


# --- the volume limits --------------------------------------------------------


class TestLimits:
    def test_below_the_minimum_is_zero(self) -> None:
        # 0.15 x 0.5 = 0.075 -> 0.05 on the step, below the 0.10 minimum -> 0.
        assert _size(_target(weight="0.15")) == Decimal(0)

    def test_exactly_the_minimum_is_kept(self) -> None:
        # 0.2 x 0.5 = 0.10.
        assert _size(_target(weight="0.2")) == Decimal("0.10")

    def test_exactly_on_a_step_is_unchanged(self) -> None:
        # 1.3 x 0.5 = 0.65 = 13 steps exactly.
        assert _size(_target(weight="1.3")) == Decimal("0.65")

    def test_above_the_maximum_is_capped(self) -> None:
        # 12 x 0.5 = 6.00 -> 5.00.
        assert _size(_target(weight="12")) == Decimal("5.00")

    def test_a_short_above_the_maximum_is_capped(self) -> None:
        assert _size(_target(weight="-12")) == Decimal("-5.00")

    def test_exactly_the_maximum_is_kept_without_a_note(self) -> None:
        sizer = _sizer()
        assert _size(_target(weight="10"), sizer=sizer) == Decimal("5.00")
        assert sizer.notes == []

    def test_a_cap_is_recorded(self) -> None:
        sizer = _sizer()
        _size(_target(weight="12"), sizer=sizer)
        (note,) = sizer.notes
        assert (note.symbol, note.kind, note.rounded, note.final) == (
            SYMBOL,
            "capped_at_maximum",
            Decimal("6.00"),
            Decimal("5.00"),
        )
        assert note.ts == _bar().ts_close

    def test_a_size_below_the_minimum_is_recorded(self) -> None:
        sizer = _sizer()
        _size(_target(weight="0.15"), sizer=sizer)
        (note,) = sizer.notes
        assert (note.kind, note.rounded, note.final) == (
            "below_minimum",
            Decimal("0.05"),
            Decimal(0),
        )

    def test_equity_at_or_below_zero_sizes_to_zero_and_is_recorded(self) -> None:
        sizer = _sizer()
        assert _size(_target(weight="1"), book=Book(equity="0"), sizer=sizer) == Decimal(0)
        assert _size(_target(weight="1"), book=Book(equity="-5"), sizer=sizer) == Decimal(0)
        assert [n.kind for n in sizer.notes] == ["equity_not_positive"] * 2


# --- the hold rule (decision A: weight and stop targets only) -----------------


class TestHold:
    def test_a_weight_target_holds_a_same_direction_position(self) -> None:
        assert _size(_target(weight="1"), committed="0.30") == Decimal("0.30")

    def test_a_stop_target_holds_a_same_direction_position(self) -> None:
        assert _size(_target(weight="-1", stop="2020"), committed="-0.30") == Decimal("-0.30")

    def test_a_weight_target_resizes_from_the_opposite_direction(self) -> None:
        assert _size(_target(weight="1"), committed="-0.30") == Decimal("0.50")
        assert _size(_target(weight="-1"), committed="0.30") == Decimal("-0.50")

    def test_a_flat_weight_closes_a_position(self) -> None:
        assert _size(_target(weight="0"), committed="0.30") == Decimal(0)

    def test_a_quantity_target_is_not_held(self) -> None:
        # Ordering the difference, exactly as before: 0.70 is asked, 0.70 is sized.
        assert _size(_target("0.70"), committed="0.30") == Decimal("0.70")


# --- quantity targets under the equity sizer ----------------------------------


class TestQuantity:
    def test_a_quantity_is_rounded_down_to_the_step(self) -> None:
        assert _size(_target("0.73")) == Decimal("0.70")
        assert _size(_target("-0.73")) == Decimal("-0.70")

    def test_a_quantity_below_the_minimum_is_zero(self) -> None:
        assert _size(_target("0.07")) == Decimal(0)

    def test_a_quantity_above_the_maximum_is_capped(self) -> None:
        assert _size(_target("9")) == Decimal("5.00")

    def test_a_quantity_ignores_equity(self) -> None:
        assert _size(_target("0.50"), book=Book(equity="0")) == Decimal("0.50")


# --- refusals ----------------------------------------------------------------


class TestRefusals:
    @pytest.mark.parametrize("stop", ["2000", "2010"], ids=["at-close", "above-close"])
    def test_a_long_stop_at_or_above_the_close(self, stop: str) -> None:
        with pytest.raises(ValueError, match="wrong side"):
            _size(_target(weight="1", stop=stop))

    @pytest.mark.parametrize("stop", ["2000", "1990"], ids=["at-close", "below-close"])
    def test_a_short_stop_at_or_below_the_close(self, stop: str) -> None:
        with pytest.raises(ValueError, match="wrong side"):
            _size(_target(weight="-1", stop=stop))

    def test_a_stop_with_a_quantity(self) -> None:
        with pytest.raises(ValueError, match=r"stop.*quantity"):
            _size(_target("0.50", stop="1980"))

    def test_a_stop_on_a_flat_target(self) -> None:
        with pytest.raises(ValueError, match="flat"):
            _size(_target(weight="0", stop="1980"))

    def test_a_missing_instrument_spec(self) -> None:
        with pytest.raises(ValueError, match="instrument spec"):
            _size(_target(weight="1"), spec=None)


# --- sizing configuration ----------------------------------------------------


class TestSizingConfig:
    def test_risk_fraction_is_required(self) -> None:
        with pytest.raises(ValidationError):
            SizingConfig.model_validate({})

    @pytest.mark.parametrize("value", ["0", "-0.01", "1.01"])
    def test_risk_fraction_must_be_above_zero_and_at_most_one(self, value: str) -> None:
        with pytest.raises(ValidationError):
            SizingConfig.model_validate({"risk_fraction": value})

    def test_a_float_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="quote"):
            SizingConfig.model_validate({"risk_fraction": 0.01})

    def test_unknown_keys_are_refused(self) -> None:
        with pytest.raises(ValidationError):
            SizingConfig.model_validate({"risk_fraction": "0.01", "max_weight": "2"})

    def test_load_from_file(self, tmp_path) -> None:
        path = tmp_path / "sizing.yaml"
        path.write_text('sizing:\n  risk_fraction: "0.005"\n', encoding="utf-8")
        assert load_sizing_config(path).risk_fraction == Decimal("0.005")
