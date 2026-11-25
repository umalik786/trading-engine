"""Tests for cost profile configuration loading. See
docs/trading-engine-architecture.md §2.8 and §6.5.6.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine.costs.profile import (
    CostProfile,
    DateRange,
    SpreadCorrectionMethod,
    load_cost_profile,
)

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

    def test_only_eurusd_declares_zero_spreads_genuine_from_2022(self) -> None:
        """Decided 2026-11-20 (3c.2 wiring, point 6): EURUSD's zeros from
        2022-01-01 are verified against ticks, so they are genuine, open-ended.
        Every other zero in the stored history stays missing data."""
        with pytest.warns(UserWarning, match="verification is incomplete"):
            profile = load_cost_profile(FTMO_PROFILE)

        eurusd = profile.instruments["EURUSD"].zero_spread_genuine
        assert len(eurusd) == 1
        assert eurusd[0].from_date == date(2022, 1, 1)
        assert eurusd[0].to_date is None
        assert eurusd[0].contains(date(2099, 1, 1))
        assert not eurusd[0].contains(date(2021, 12, 31))
        others = [c for s, c in profile.instruments.items() if s != "EURUSD"]
        assert all(not costs.zero_spread_genuine for costs in others)

    def test_the_ftmo_profile_carries_the_validated_correction_methods(self) -> None:
        """As approved 2026-11-20 from the 3c.2 validation."""
        with pytest.warns(UserWarning, match="verification is incomplete"):
            profile = load_cost_profile(FTMO_PROFILE)

        expected = {
            "NAS100": ("points", "per_hour"),
            "EURUSD": ("points", "per_hour"),
            "US500": ("points", "constant"),
            "XAUUSD": ("points", "constant"),
            "XAGUSD": ("percentage", "constant"),
        }
        for symbol, (form, structure) in expected.items():
            method = profile.instruments[symbol].spread_correction
            assert method is not None, symbol
            assert (method.form, method.structure) == (form, structure), symbol
            assert method.percentile == 90
            assert method.min_fit_weeks == 12

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
        read from symbol_info() on a known date, the commission on another
        (2026-11-24, per instrument), and the fallback spreads are still
        placeholders. One date for the whole file would have to mislabel some
        of them. Swaps re-read 2026-11-17 on a fresh FTMO trial."""
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
            symbol: rates.triple_weekday for symbol, rates in profile.financing.instruments.items()
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
        assert isinstance(costs.slippage.value, Decimal)

    def test_the_test_profile_keeps_zero_slippage(self) -> None:
        """The 3a/3b golden figures were computed with no slippage; the
        migration to a slippage block must not change that."""
        with pytest.warns(UserWarning, match="verification is incomplete"):
            profile = load_cost_profile(TEST_PROFILE)

        slippage = profile.instruments["XAUUSD"].slippage
        assert (slippage.shape, slippage.value) == ("fixed", Decimal(0))

    def test_the_ftmo_profile_has_a_placeholder_spread_multiple_of_half(self) -> None:
        """Operator decision 2026-11-19: 0.5 x the charged spread, marked
        PLACEHOLDER -- slippage cannot be measured on a simulated venue
        (spec C.4), and zero would be the optimistic guess."""
        with pytest.warns(UserWarning, match="verification is incomplete"):
            profile = load_cost_profile(FTMO_PROFILE)

        assert {
            symbol: (costs.slippage.shape, costs.slippage.value)
            for symbol, costs in profile.instruments.items()
        } == {symbol: ("spread_multiple", Decimal("0.5")) for symbol in profile.instruments}


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
                    instruments={"XAUUSD": {"commission": {"shape": "per_trade", "value": "1.00"}}}
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

        slippage = profile.instruments["XAUUSD"].slippage
        assert (slippage.shape, slippage.value) == ("fixed", Decimal(0))

    def test_an_unknown_slippage_shape_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="slippage"):
            CostProfile.model_validate(
                self._profile(
                    instruments={
                        "XAUUSD": {
                            "commission": {"shape": "per_lot_per_side", "value": "1"},
                            "slippage": {"shape": "random", "value": "1"},
                        }
                    }
                )
            )

    def test_a_negative_slippage_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="greater_than_equal"):
            CostProfile.model_validate(
                self._profile(
                    instruments={
                        "XAUUSD": {
                            "commission": {"shape": "per_lot_per_side", "value": "1"},
                            "slippage": {"shape": "spread_multiple", "value": "-0.5"},
                        }
                    }
                )
            )

    def test_an_unknown_key_in_an_instruments_costs_is_rejected(self) -> None:
        """The old `slippage_price_units` key left in a profile after the
        migration must fail at load, not be silently ignored -- ignoring it
        would quietly price slippage at zero."""
        with pytest.raises(ValidationError, match="slippage_price_units"):
            CostProfile.model_validate(
                self._profile(
                    instruments={
                        "XAUUSD": {
                            "commission": {"shape": "per_lot_per_side", "value": "1"},
                            "slippage_price_units": "0.05",
                        }
                    }
                )
            )

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


class TestSpreadCorrectionMethod:
    def _method(self, **change):
        raw = {
            "form": "points",
            "structure": "constant",
            "percentile": 90,
            "min_fit_weeks": 12,
            "source": "x",
        } | change
        return SpreadCorrectionMethod.model_validate(raw)

    @pytest.mark.parametrize("pct", [0, 101])
    def test_percentile_must_be_1_to_100(self, pct) -> None:
        with pytest.raises(ValidationError):
            self._method(percentile=pct)

    def test_min_fit_weeks_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            self._method(min_fit_weeks=0)

    def test_source_must_not_be_empty(self) -> None:
        with pytest.raises(ValidationError):
            self._method(source="")


class TestOpenEndedDateRange:
    def test_a_range_with_no_end_runs_on(self) -> None:
        r = DateRange.model_validate({"from": "2022-01-01"})
        assert r.to_date is None
        assert r.contains(date(2022, 1, 1))
        assert r.contains(date(2099, 12, 31))
        assert not r.contains(date(2021, 12, 31))


# --- commission provenance (operator decision 2026-11-23) --------------------
# Each commission entry carries its own date and source and warns when either is
# missing or the date is stale, like financing. Before this, a `provenance`
# key under commission would have been silently ignored.


def _profile_file(tmp_path: Path, commission: str) -> Path:
    path = tmp_path / "profile.yaml"
    path.write_text(
        "cost_profile:\n"
        "  profile: provenance_test\n"
        "  rules_verified: null\n"
        "  rules_source: null\n"
        "  price_basis: bid\n"
        "  financing:\n"
        "    instruments:\n"
        "      XAUUSD: {shape: disabled}\n"
        "  instruments:\n"
        "    XAUUSD:\n"
        f"      commission: {commission}\n",
        encoding="utf-8",
    )
    return path


def _commission_warnings(path: Path) -> list[str]:
    import warnings  # noqa: PLC0415

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        load_cost_profile(path)
    return [str(w.message) for w in caught if "commission" in str(w.message)]


class TestCommissionProvenance:
    def test_a_commission_without_provenance_warns_naming_its_instrument(self, tmp_path) -> None:
        path = _profile_file(tmp_path, '{shape: per_lot_per_side, value: "1"}')
        (message,) = _commission_warnings(path)
        assert message.startswith("provenance_test XAUUSD commission: verification")

    def test_a_recently_verified_commission_does_not_warn(self, tmp_path) -> None:
        from datetime import UTC, datetime, timedelta  # noqa: PLC0415

        recent = (datetime.now(UTC).date() - timedelta(days=10)).isoformat()
        path = _profile_file(
            tmp_path,
            '{shape: per_lot_per_side, value: "1", '
            f'provenance: {{verified: "{recent}", source: "deal history"}}}}',
        )
        assert _commission_warnings(path) == []

    def test_a_stale_commission_warns(self, tmp_path) -> None:
        path = _profile_file(
            tmp_path,
            '{shape: per_lot_per_side, value: "1", '
            'provenance: {verified: "2020-01-01", source: "deal history"}}',
        )
        (message,) = _commission_warnings(path)
        assert "XAUUSD commission: verified 2020-01-01" in message

    def test_commission_staleness_defaults_to_90_days(self) -> None:
        from engine.costs.profile import Commission  # noqa: PLC0415

        commission = Commission.model_validate({"shape": "per_lot_per_side", "value": "1"})
        assert commission.provenance.stale_after_days == 90

    def test_a_misspelt_key_under_commission_is_refused(self) -> None:
        from engine.costs.profile import Commission  # noqa: PLC0415

        with pytest.raises(ValidationError):
            Commission.model_validate(
                {"shape": "per_lot_per_side", "value": "1", "provenence": {"source": "x"}}
            )


# --- the FTMO commission, verified 2026-11-24 ---------------------------------
# Venue: FTMO's symbols page (Forex $5.000; XAUUSD, XAGUSD 0.0014%; indices
# 0.000%), confirmed by trial-account deal history to be charged HALF PER SIDE.


def _ftmo() -> CostProfile:
    import warnings  # noqa: PLC0415

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return load_cost_profile(FTMO_PROFILE)


@pytest.mark.parametrize(
    ("symbol", "shape", "value"),
    [
        ("EURUSD", "per_lot_per_side", Decimal("2.50")),
        ("XAUUSD", "pct_notional", Decimal("0.0007")),
        ("XAGUSD", "pct_notional", Decimal("0.0007")),
        ("NAS100", "per_lot_per_side", Decimal(0)),
        ("US500", "per_lot_per_side", Decimal(0)),
    ],
)
def test_the_ftmo_commission_is_the_verified_venue_rate(symbol, shape, value) -> None:
    commission = _ftmo().instruments[symbol].commission
    assert (commission.shape, commission.value) == (shape, value)
    assert commission.provenance.verified == date(2026, 11, 24)
    assert "ftmo.com/en/symbols" in commission.provenance.source


@pytest.mark.parametrize(
    ("symbol", "price", "expected"),
    [
        # The 2026-11-24 1.00-lot deals, at their own prices. EXACT, not rounded
        # to the cent as MT5 rounds them (operator decision 2026-11-23): MT5
        # showed -2.50, -1.43, -2.50.
        ("EURUSD", "1.09699", Decimal("2.50")),
        ("XAUUSD", "3567.85", Decimal("2.497495")),  # 1 x 100 x 3567.85 x 0.0007%
        ("XAGUSD", "40.985", Decimal("1.434475")),  # 1 x 5000 x 40.985 x 0.0007%
        ("NAS100", "25973.68", Decimal(0)),
    ],
)
def test_ftmo_commission_on_one_lot_matches_the_deal_history_exactly(
    symbol, price, expected
) -> None:
    from engine.core.instruments import load_instrument_specs  # noqa: PLC0415
    from engine.core.types import Order  # noqa: PLC0415
    from engine.costs.configured import ConfiguredCostModel  # noqa: PLC0415

    profile = _ftmo()
    # The fee arithmetic needs no spread-correction table; drop the methods.
    no_correction = {
        s: c.model_copy(update={"spread_correction": None}) for s, c in profile.instruments.items()
    }
    model = ConfiguredCostModel(
        profile.model_copy(update={"instruments": no_correction}),
        load_instrument_specs(REPO_ROOT / "config" / "instruments.yaml"),
    )
    order = Order(
        client_order_id="c",
        symbol=symbol,
        side="buy",
        quantity=Decimal(1),
        order_type="market",
        limit_price=None,
        stop_price=None,
        intent_id="i",
    )
    assert model.fees(order, Decimal(price), Decimal(1)) == expected
