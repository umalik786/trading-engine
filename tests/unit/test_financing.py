"""Tests for overnight financing. See docs/trading-engine-architecture.md
§2.8, Appendix C.1 and `engine.costs.configured`.

Rates are chosen round and asymmetric so the arithmetic is checkable and
so a mechanism that swapped the two sides, or dropped a sign, could not
pass by coincidence: XAUUSD long -10.0 points, short +4.0 points, with
`point x contract_size` equal to 1, so one night on one lot is -10.00 for
a long and +4.00 for a short.

February 2025 is US winter, so the server runs UTC+2 and each rollover
falls at 22:00 UTC the day before.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from engine.core.instruments import InstrumentSpec
from engine.core.portfolio import Position
from engine.costs.configured import ConfiguredCostModel
from engine.costs.profile import CostProfile

SYMBOL = "XAUUSD"
SPECS = {
    SYMBOL: InstrumentSpec(
        contract_size=Decimal(100), point=Decimal("0.01"), quote_currency="USD"
    )
}
LONG_NIGHT = Decimal("-10.00")
SHORT_NIGHT = Decimal("4.00")
OPENED_LONG_AGO = datetime(2025, 1, 1, tzinfo=UTC)


def _model(
    *,
    shape: str = "points",
    long_rate: str = "-10.0",
    short_rate: str = "4.0",
    triple_weekday: str | None = "Wednesday",
) -> ConfiguredCostModel:
    profile = CostProfile.model_validate(
        {
            "profile": "financing-unit-test",
            "price_basis": "bid",
            "account_currency": "USD",
            "server_clock": {
                "shape": "dst_switched_offsets",
                "winter_offset_hours": 2,
                "summer_offset_hours": 3,
                "dst_calendar": "America/New_York",
            },
            "financing": {
                "instruments": {
                    SYMBOL: {
                        "shape": shape,
                        "long_rate": long_rate,
                        "short_rate": short_rate,
                        "triple_weekday": triple_weekday,
                    }
                }
            },
            "instruments": {
                SYMBOL: {"commission": {"shape": "per_lot_per_side", "value": "0"}}
            },
        }
    )
    return ConfiguredCostModel(profile, SPECS)


def _position(quantity: str = "1", opened_at: datetime = OPENED_LONG_AGO) -> Position:
    return Position(
        symbol=SYMBOL,
        quantity=Decimal(quantity),
        cost=Decimal(quantity) * Decimal("2000.00"),
        opened_at=opened_at,
    )


def _window(day: int, *, hours: int = 24) -> tuple[datetime, datetime]:
    """A window starting at 12:00 UTC on 2025-02-`day`, long enough to
    contain that evening's rollover at 22:00 UTC."""
    start = datetime(2025, 2, day, 12, 0, tzinfo=UTC)
    return start, start + timedelta(hours=hours)


class TestOneNight:
    def test_a_long_pays_its_rate_for_one_rollover(self) -> None:
        # Monday 2025-02-10 ends at 22:00 UTC; one ordinary night
        start, end = _window(10, hours=11)

        assert _model().financing(_position("1"), start, end) == LONG_NIGHT

    def test_a_short_is_paid_its_rate_for_one_rollover(self) -> None:
        """A positive rate is a credit and the mechanism must pay it. Two
        of five instruments on this venue credit a short today."""
        start, end = _window(10, hours=11)

        assert _model().financing(_position("-1"), start, end) == SHORT_NIGHT

    def test_the_charge_scales_with_lots(self) -> None:
        start, end = _window(10, hours=11)

        assert _model().financing(_position("3"), start, end) == LONG_NIGHT * 3

    def test_a_short_of_three_lots_is_credited_three_times(self) -> None:
        start, end = _window(10, hours=11)

        assert _model().financing(_position("-3"), start, end) == SHORT_NIGHT * 3

    def test_no_rollover_in_the_window_costs_nothing(self) -> None:
        start = datetime(2025, 2, 10, 12, 0, tzinfo=UTC)
        end = datetime(2025, 2, 10, 20, 0, tzinfo=UTC)

        assert _model().financing(_position(), start, end) == Decimal(0)

    def test_holding_longer_within_one_night_changes_nothing(self) -> None:
        """Charged per rollover crossed, never per bar or per hour."""
        narrow = _model().financing(
            _position(),
            datetime(2025, 2, 10, 21, 59, tzinfo=UTC),
            datetime(2025, 2, 10, 22, 1, tzinfo=UTC),
        )
        wide = _model().financing(
            _position(),
            datetime(2025, 2, 10, 12, 0, tzinfo=UTC),
            datetime(2025, 2, 10, 23, 0, tzinfo=UTC),
        )

        assert narrow == wide == LONG_NIGHT


class TestWeekendsAndTripleDay:
    def test_saturday_and_sunday_cost_nothing(self) -> None:
        """2025-02-08 and 02-09 are Saturday and Sunday. Their rollovers
        happen while the market is shut; the triple day collects them."""
        start = datetime(2025, 2, 7, 23, 0, tzinfo=UTC)  # after Friday's rollover
        end = datetime(2025, 2, 9, 23, 0, tzinfo=UTC)  # before Monday's

        assert _model().financing(_position(), start, end) == Decimal(0)

    def test_a_whole_weekend_hold_costs_one_night(self) -> None:
        """Friday close to Monday open crosses three rollovers -- Saturday,
        Sunday and Monday -- of which only Monday's is charged."""
        start = datetime(2025, 2, 7, 22, 0, tzinfo=UTC)
        end = datetime(2025, 2, 10, 23, 0, tzinfo=UTC)

        assert _model().financing(_position(), start, end) == LONG_NIGHT

    def test_the_configured_weekday_is_charged_three_times(self) -> None:
        """2025-02-05 is a Wednesday, so its 22:00 UTC rollover is the
        Wednesday-night one."""
        start, end = _window(5, hours=11)

        assert _model(triple_weekday="Wednesday").financing(
            _position(), start, end
        ) == LONG_NIGHT * 3

    def test_the_triple_day_is_configuration_not_a_constant(self) -> None:
        """Thursday instead: the Wednesday rollover becomes a single and
        Thursday's becomes the triple."""
        model = _model(triple_weekday="Thursday")
        wednesday_start, wednesday_end = _window(5, hours=11)
        thursday_start, thursday_end = _window(6, hours=11)

        assert model.financing(_position(), wednesday_start, wednesday_end) == LONG_NIGHT
        assert (
            model.financing(_position(), thursday_start, thursday_end) == LONG_NIGHT * 3
        )

    def test_no_triple_day_means_every_weekday_is_single(self) -> None:
        start, end = _window(5, hours=11)

        assert _model(triple_weekday=None).financing(_position(), start, end) == LONG_NIGHT

    def test_a_triple_credit_is_paid_three_times(self) -> None:
        start, end = _window(5, hours=11)

        assert _model().financing(_position("-1"), start, end) == SHORT_NIGHT * 3

    def test_a_full_week_held_charges_five_nights_plus_the_double(self) -> None:
        """Wednesday triple, Thursday, Friday, Monday, Tuesday = 7 nights
        across a week, with Saturday and Sunday free."""
        start = datetime(2025, 2, 4, 23, 0, tzinfo=UTC)  # after Tuesday's rollover
        end = datetime(2025, 2, 11, 23, 0, tzinfo=UTC)  # after Tuesday's, a week on

        assert _model().financing(_position(), start, end) == LONG_NIGHT * 7


class TestPositionMustHaveBeenOpen:
    def test_a_rollover_before_the_position_opened_is_not_charged(self) -> None:
        """The comparison is against the instant, not its calendar day. A
        position filled at 23:00 did not exist at the 22:00 rollover even
        though both fall on the same day and in the same session -- which
        is exactly the case the golden fixture contains."""
        opened_after = _position(opened_at=datetime(2025, 2, 10, 23, 0, tzinfo=UTC))
        start, end = _window(10, hours=12)

        assert _model().financing(opened_after, start, end) == Decimal(0)

    def test_a_position_opened_at_exactly_the_rollover_is_not_charged(self) -> None:
        """Stated in the harness docstring as a rule: opened at the
        instant means not charged for it. You do not owe for a night that
        ended as you came in."""
        rollover = datetime(2025, 2, 10, 22, 0, tzinfo=UTC)
        opened_then = _position(opened_at=rollover)
        start, end = _window(10, hours=12)

        assert _model().financing(opened_then, start, end) == Decimal(0)

    def test_a_rollover_after_the_position_opened_is_charged(self) -> None:
        opened_before = _position(opened_at=datetime(2025, 2, 10, 21, 0, tzinfo=UTC))
        start, end = _window(10, hours=12)

        assert _model().financing(opened_before, start, end) == LONG_NIGHT


class TestClosingPositions:
    """The mirror of the opening rule, and the reason the engine loop
    charges rollovers in two windows around each bar's fills."""

    def test_a_position_closed_before_a_rollover_is_not_charged_for_it(self) -> None:
        """Closed at Monday 21:00, an hour before the 22:00 rollover. The
        loop's window for the closing bar ends at that bar's open, so the
        rollover never falls inside a window while the position is held."""
        model = _model()
        held = _position(opened_at=datetime(2025, 2, 7, 23, 0, tzinfo=UTC))
        # The window the loop would evaluate before the closing fill.
        start = datetime(2025, 2, 10, 20, 0, tzinfo=UTC)
        closed_at = datetime(2025, 2, 10, 21, 0, tzinfo=UTC)

        assert model.financing(held, start, closed_at) == Decimal(0)

    def test_a_position_held_through_a_rollover_is_charged_for_it(self) -> None:
        model = _model()
        held = _position(opened_at=datetime(2025, 2, 7, 23, 0, tzinfo=UTC))
        start = datetime(2025, 2, 10, 20, 0, tzinfo=UTC)
        closed_at = datetime(2025, 2, 10, 23, 0, tzinfo=UTC)  # after the rollover

        assert model.financing(held, start, closed_at) == LONG_NIGHT

    def test_a_position_closed_at_exactly_the_rollover_is_charged(self) -> None:
        """The window's upper bound is inclusive and the loop evaluates it
        BEFORE applying the bar's fills, so a position closing at that
        instant was still held when the day turned. You owe for the night
        you held."""
        model = _model()
        held = _position(opened_at=datetime(2025, 2, 7, 23, 0, tzinfo=UTC))
        rollover = datetime(2025, 2, 10, 22, 0, tzinfo=UTC)

        start = rollover - timedelta(hours=2)
        assert model.financing(held, start, rollover) == LONG_NIGHT


class TestShapes:
    def test_points_converts_through_point_and_contract_size(self) -> None:
        """One point on one XAUUSD lot is 0.01 x 100 = 1.00, which the
        broker's own tick_value confirms independently."""
        start, end = _window(10, hours=11)

        assert _model(long_rate="-83.0").financing(_position(), start, end) == Decimal("-83.00")

    def test_currency_per_lot_uses_the_rate_as_money_directly(self) -> None:
        start, end = _window(10, hours=11)
        model = _model(shape="currency_per_lot", long_rate="-7.25")

        assert model.financing(_position(), start, end) == Decimal("-7.25")

    def test_currency_per_lot_ignores_point_and_contract_size(self) -> None:
        """The distinction between the two shapes: a points rate is scaled
        by the instrument's specification, a currency rate is not."""
        start, end = _window(10, hours=11)
        points = _model(shape="points", long_rate="-7.25")
        currency = _model(shape="currency_per_lot", long_rate="-7.25")

        assert points.financing(_position(), start, end) == Decimal("-7.25")  # x1 for XAUUSD
        assert currency.financing(_position(), start, end) == Decimal("-7.25")

    def test_disabled_charges_nothing(self) -> None:
        start, end = _window(5, hours=11)  # a triple day, so clearly not a no-op window

        assert _model(shape="disabled").financing(_position(), start, end) == Decimal(0)

    def test_an_instrument_with_no_financing_configured_raises(self) -> None:
        """A gap in configuration must never make trading cheaper. The same
        rule as a missing commission entry or a missing fallback spread:
        holding overnight costs something on every instrument this venue
        offers, so silence would be the most flattering reading of an
        omission. "No swap" has to be stated, with shape: disabled."""
        model = _model()
        other = Position(
            symbol="EURUSD",
            quantity=Decimal(1),
            cost=Decimal("1.1000"),
            opened_at=OPENED_LONG_AGO,
        )
        start, end = _window(10, hours=11)

        with pytest.raises(KeyError, match="no financing entry"):
            model.financing(other, start, end)

    def test_disabled_is_how_no_swap_is_stated(self) -> None:
        """The distinction the previous test rests on: zero is reachable,
        but only by someone writing it down."""
        start, end = _window(5, hours=11)

        assert _model(shape="disabled").financing(_position(), start, end) == Decimal(0)


class TestLongAndShortAreDistinct:
    def test_the_two_rates_are_not_interchangeable(self) -> None:
        """Guards against the sides being swapped. The rates differ in
        magnitude and in sign, so a swap cannot cancel out."""
        start, end = _window(10, hours=11)
        model = _model()

        assert model.financing(_position("1"), start, end) == LONG_NIGHT
        assert model.financing(_position("-1"), start, end) == SHORT_NIGHT
        assert LONG_NIGHT != SHORT_NIGHT
        assert LONG_NIGHT != -SHORT_NIGHT


class TestConfigurationGuards:
    def test_financing_without_a_server_clock_is_rejected(self) -> None:
        """The rollover instant is midnight on the server's clock. There
        is no default for which clock that is."""
        with pytest.raises(ValueError, match="server_clock"):
            CostProfile.model_validate(
                {
                    "profile": "no-clock",
                    "price_basis": "bid",
                    "financing": {
                        "instruments": {SYMBOL: {"shape": "points", "long_rate": "-1"}}
                    },
                    "instruments": {
                        SYMBOL: {"commission": {"shape": "per_lot_per_side", "value": "0"}}
                    },
                }
            )

    def test_disabled_financing_needs_no_clock(self) -> None:
        profile = CostProfile.model_validate(
            {
                "profile": "disabled-financing",
                "price_basis": "bid",
                "financing": {"instruments": {SYMBOL: {"shape": "disabled"}}},
                "instruments": {
                    SYMBOL: {"commission": {"shape": "per_lot_per_side", "value": "0"}}
                },
            }
        )

        assert profile.server_clock is None
