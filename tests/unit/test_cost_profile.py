"""Tests for cost profile configuration loading. See
docs/trading-engine-architecture.md §2.8 and §6.5.6.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine.costs.profile import CostProfile, DateRange, load_cost_profile

REPO_ROOT = Path(__file__).resolve().parents[2]
FTMO_PROFILE = REPO_ROOT / "config" / "cost_ftmo_demo.yaml"
TEST_PROFILE = REPO_ROOT / "tests" / "golden" / "fixtures" / "cost_test_profile.yaml"


class TestShippedProfiles:
    def test_the_ftmo_profile_warns_because_nothing_in_it_is_verified(self) -> None:
        """Every number in it is a placeholder, so rules_verified is unset
        and the load must say so (§6.5.6)."""
        with pytest.warns(UserWarning, match="verification is incomplete"):
            profile = load_cost_profile(FTMO_PROFILE)

        assert profile.rules_verified is None
        assert profile.price_basis == "bid"

    def test_the_ftmo_profile_covers_every_traded_instrument(self) -> None:
        with pytest.warns(UserWarning, match="verification is incomplete"):
            profile = load_cost_profile(FTMO_PROFILE)

        assert set(profile.instruments) == {"NAS100", "US500", "EURUSD", "XAUUSD", "XAGUSD"}

    def test_the_ftmo_profile_declares_no_zero_spread_as_genuine(self) -> None:
        """The pessimistic default: with no ranges declared, every zero
        spread in the stored history is treated as missing data."""
        with pytest.warns(UserWarning, match="verification is incomplete"):
            profile = load_cost_profile(FTMO_PROFILE)

        assert all(not costs.zero_spread_genuine for costs in profile.instruments.values())

    def test_the_test_profile_is_the_one_the_golden_tests_describe(self) -> None:
        with pytest.warns(UserWarning, match="verification is incomplete"):
            profile = load_cost_profile(TEST_PROFILE)

        assert profile.price_basis == "bid"
        commission = profile.instruments["XAUUSD"].commission
        assert commission.shape == "per_lot_per_side"
        assert commission.value == Decimal("3.50")

    def test_decimal_values_load_as_decimal_not_float(self) -> None:
        with pytest.warns(UserWarning, match="verification is incomplete"):
            profile = load_cost_profile(TEST_PROFILE)

        costs = profile.instruments["XAUUSD"]
        assert isinstance(costs.commission.value, Decimal)
        assert isinstance(costs.fallback_spread, Decimal)
        assert isinstance(costs.slippage_price_units, Decimal)


class TestDateRanges:
    def test_both_ends_are_inclusive(self) -> None:
        window = DateRange(**{"from": "2020-01-01", "to": "2020-12-31"})

        assert window.contains(date(2020, 1, 1))
        assert window.contains(date(2020, 12, 31))
        assert window.contains(date(2020, 6, 15))

    def test_dates_outside_are_excluded(self) -> None:
        window = DateRange(**{"from": "2020-01-01", "to": "2020-12-31"})

        assert not window.contains(date(2019, 12, 31))
        assert not window.contains(date(2021, 1, 1))

    def test_a_single_day_range_is_allowed(self) -> None:
        window = DateRange(**{"from": "2020-05-05", "to": "2020-05-05"})

        assert window.contains(date(2020, 5, 5))
        assert not window.contains(date(2020, 5, 6))

    def test_a_backwards_range_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="before its start"):
            DateRange(**{"from": "2020-12-31", "to": "2020-01-01"})


class TestValidation:
    def _profile(self, **overrides: object) -> dict:
        raw = {
            "profile": "unit-test",
            "price_basis": "bid",
            "instruments": {
                "XAUUSD": {"commission": {"shape": "per_lot_per_side", "value": "1.00"}}
            },
        }
        raw.update(overrides)
        return raw

    def test_an_unknown_price_basis_is_rejected(self) -> None:
        """Only bid and mid are modelled. A typo here would otherwise
        decide which side of every trade pays the spread."""
        with pytest.raises(ValidationError, match="price_basis"):
            CostProfile.model_validate(self._profile(price_basis="ask"))

    def test_an_unknown_commission_shape_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="shape"):
            CostProfile.model_validate(
                self._profile(
                    instruments={
                        "XAUUSD": {"commission": {"shape": "per_trade", "value": "1.00"}}
                    }
                )
            )

    def test_a_negative_commission_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="greater_than_equal"):
            CostProfile.model_validate(
                self._profile(
                    instruments={
                        "XAUUSD": {"commission": {"shape": "per_lot_per_side", "value": "-1"}}
                    }
                )
            )

    def test_a_negative_fallback_spread_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="greater_than_equal"):
            CostProfile.model_validate(
                self._profile(
                    instruments={
                        "XAUUSD": {
                            "commission": {"shape": "per_lot_per_side", "value": "1"},
                            "fallback_spread": "-0.01",
                        }
                    }
                )
            )

    def test_slippage_defaults_to_zero_when_omitted(self) -> None:
        profile = CostProfile.model_validate(self._profile())

        assert profile.instruments["XAUUSD"].slippage_price_units == Decimal(0)

    def test_fallback_spread_may_be_omitted(self) -> None:
        """Optional in the schema. The cost model raises if a zero spread
        then turns up and needs one, rather than treating it as free."""
        profile = CostProfile.model_validate(self._profile())

        assert profile.instruments["XAUUSD"].fallback_spread is None
