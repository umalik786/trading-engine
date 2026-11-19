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

    @pytest.mark.parametrize("path", [FTMO_PROFILE, TEST_PROFILE])
    def test_every_instrument_covered_has_a_financing_entry(self, path: Path) -> None:
        """A missing financing entry raises at the first rollover rather
        than charging zero, so a profile that covers an instrument for
        commission but forgets its swap would fail mid-run. Confirmed
        here, at load, for both shipped profiles."""
        with pytest.warns(UserWarning, match="verification is incomplete"):
            profile = load_cost_profile(path)

        covered = set(profile.instruments)
        financed = set(profile.financing.instruments)
        assert covered == financed, (
            f"{profile.profile}: instruments without a financing entry: "
            f"{covered - financed}; financing entries for instruments the profile "
            f"does not otherwise cover: {financed - covered}"
        )

    @pytest.mark.parametrize("path", [FTMO_PROFILE, TEST_PROFILE])
    def test_a_financing_profile_names_its_server_clock(self, path: Path) -> None:
        """The rollover instant is midnight on the server's clock, and
        there is no default for which clock that is."""
        with pytest.warns(UserWarning, match="verification is incomplete"):
            profile = load_cost_profile(path)

        assert profile.server_clock is not None

    def test_the_ftmo_financing_section_is_verified_unlike_the_rest(self) -> None:
        """The reason provenance is per section: these swap values were
        read from symbol_info() on a known date, while commission is still a
        placeholder. One date for the whole file would have to mislabel one
        or the other. Re-read 2026-11-17 on a fresh FTMO trial."""
        with pytest.warns(UserWarning, match="verification is incomplete"):
            profile = load_cost_profile(FTMO_PROFILE)

        assert profile.rules_verified is None  # the file as a whole
        assert profile.financing.provenance.verified == date(2026, 11, 17)
        assert profile.financing.provenance.source is not None
        assert profile.financing.provenance.stale_after_days == 30

    def test_the_ftmo_triple_weekday_is_the_2026_11_17_reading(self) -> None:
        """symbol_info().swap_rollover3days, read 2026-11-17 with
        check_chart_mode.py: Friday for the indices, Wednesday for the rest.
        Only the weekday was read. Whether "Wednesday" names the rollover
        ending that day or the one beginning it is still unverified."""
        with pytest.warns(UserWarning, match="verification is incomplete"):
            profile = load_cost_profile(FTMO_PROFILE)

        triple = {
            symbol: rates.triple_weekday
            for symbol, rates in profile.financing.instruments.items()
        }
        assert triple == {
            "NAS100": "Friday",
            "US500": "Friday",
            "EURUSD": "Wednesday",
            "XAUUSD": "Wednesday",
            "XAGUSD": "Wednesday",
        }

    def test_the_ftmo_swap_rates_are_the_2026_11_17_reading(self) -> None:
        """swap_long and swap_short from symbol_info() on FTMO-Demo,
        2026-11-17 (mt5-verification-2026-11-17.json). Two signs differ from
        the 2026-09-11 reading: the NAS100 short is now a credit and the
        XAGUSD short now a cost."""
        with pytest.warns(UserWarning, match="verification is incomplete"):
            profile = load_cost_profile(FTMO_PROFILE)

        rates = {
            symbol: (r.long_rate, r.short_rate)
            for symbol, r in profile.financing.instruments.items()
        }
        assert rates == {
            "NAS100": (Decimal("-684.39"), Decimal("20.6")),
            "US500": (Decimal("-175.75"), Decimal("-4.04")),
            "EURUSD": (Decimal("-8.8"), Decimal("0.38")),
            "XAUUSD": (Decimal("-57.69"), Decimal("-4.2")),
            "XAGUSD": (Decimal("-12.58"), Decimal("-0.93")),
        }

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
            # Every covered instrument needs a financing entry; `disabled`
            # is how "no swap" is stated, and needs no server clock.
            "financing": {"instruments": {"XAUUSD": {"shape": "disabled"}}},
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

    def test_an_instrument_without_a_financing_entry_fails_at_load(self) -> None:
        """Structural, not deferred to the first rollover. A profile that
        covers an instrument for commission while forgetting its swap is
        wrong when it is written, not when it is used."""
        with pytest.raises(ValidationError, match="no financing entry"):
            CostProfile.model_validate(self._profile(financing={"instruments": {}}))

    def test_a_financing_entry_for_an_uncovered_instrument_fails_at_load(self) -> None:
        """The other direction: a swap entry naming an instrument the
        profile does not otherwise cover is a typo or a missing commission
        entry, and either way is not what anyone meant."""
        raw = self._profile(
            financing={
                "instruments": {
                    "XAUUSD": {"shape": "disabled"},
                    "XAGUSD": {"shape": "disabled"},
                }
            }
        )
        with pytest.raises(ValidationError, match="XAGUSD"):
            CostProfile.model_validate(raw)

    def test_saying_disabled_satisfies_the_coverage_rule(self) -> None:
        """Silence is refused; an explicit zero is not. Someone has to
        type `disabled`, which is the whole distinction."""
        profile = CostProfile.model_validate(self._profile())

        assert profile.financing.instruments["XAUUSD"].shape == "disabled"

    def test_fallback_spread_may_be_omitted(self) -> None:
        """Optional in the schema. The cost model raises if a zero spread
        then turns up and needs one, rather than treating it as free."""
        profile = CostProfile.model_validate(self._profile())

        assert profile.instruments["XAUUSD"].fallback_spread is None
