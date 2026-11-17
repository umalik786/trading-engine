"""Tests for instrument configuration loading. See
docs/trading-engine-architecture.md Appendix A.6.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine.core.instruments import (
    load_bars_genuine_from,
    load_contract_sizes,
    load_instrument_specs,
)

INSTRUMENTS_CONFIG = Path(__file__).resolve().parents[2] / "config" / "instruments.yaml"


class TestShippedConfig:
    def test_every_traded_instrument_has_a_contract_size(self) -> None:
        """§10 names these five instruments; a symbol missing here raises
        at the first fill rather than defaulting to a guessed multiplier."""
        sizes = load_contract_sizes(INSTRUMENTS_CONFIG)
        assert set(sizes) == {"NAS100", "US500", "EURUSD", "XAUUSD", "XAGUSD"}

    @pytest.mark.parametrize(
        ("symbol", "expected"),
        [
            ("NAS100", Decimal(1)),
            ("US500", Decimal(1)),
            ("EURUSD", Decimal(100000)),
            ("XAUUSD", Decimal(100)),
            ("XAGUSD", Decimal(5000)),
        ],
    )
    def test_contract_sizes_are_the_expected_venue_values(
        self, symbol: str, expected: Decimal
    ) -> None:
        assert load_contract_sizes(INSTRUMENTS_CONFIG)[symbol] == expected

    def test_contract_sizes_load_as_decimal_not_float(self) -> None:
        sizes = load_contract_sizes(INSTRUMENTS_CONFIG)
        assert all(isinstance(size, Decimal) for size in sizes.values())

    def test_specs_and_sizes_agree(self) -> None:
        specs = load_instrument_specs(INSTRUMENTS_CONFIG)
        sizes = load_contract_sizes(INSTRUMENTS_CONFIG)
        assert {symbol: spec.contract_size for symbol, spec in specs.items()} == sizes


class TestBarsGenuineFrom:
    """Index history on this venue is daily, then hourly, bars filed under
    M15 until September 2021, and daily bars filed under H1/H4 until
    January 2021 (docs/state.md, trial session 2026-11-17, proposal b).
    The dates past which each series is genuinely what its folder says are
    venue facts, so they live in config."""

    def test_the_index_series_carry_their_genuine_from_dates(self) -> None:
        genuine = load_bars_genuine_from(INSTRUMENTS_CONFIG)
        for symbol in ("NAS100", "US500"):
            assert genuine[symbol] == {
                "M15": datetime(2021, 9, 15, tzinfo=UTC),
                "H1": datetime(2021, 1, 22, tzinfo=UTC),
                "H4": datetime(2021, 1, 22, tzinfo=UTC),
            }

    def test_the_clean_instruments_carry_no_restriction(self) -> None:
        genuine = load_bars_genuine_from(INSTRUMENTS_CONFIG)
        for symbol in ("EURUSD", "XAUUSD", "XAGUSD"):
            assert genuine[symbol] == {}

    def test_a_date_without_a_timezone_is_rejected(self, tmp_path: Path) -> None:
        config = tmp_path / "instruments.yaml"
        config.write_text(
            'instruments:\n  NAS100:\n    contract_size: 1\n    point: "0.01"\n'
            '    bars_genuine_from:\n      M15: "2021-09-15T00:00:00"\n'
        )
        with pytest.raises(ValidationError, match="UTC"):
            load_instrument_specs(config)

    def test_a_non_utc_date_is_rejected(self, tmp_path: Path) -> None:
        config = tmp_path / "instruments.yaml"
        config.write_text(
            'instruments:\n  NAS100:\n    contract_size: 1\n    point: "0.01"\n'
            '    bars_genuine_from:\n      M15: "2021-09-15T00:00:00+02:00"\n'
        )
        with pytest.raises(ValidationError, match="UTC"):
            load_instrument_specs(config)


class TestValidation:
    @pytest.mark.parametrize("bad_value", ["0", "-100"])
    def test_a_non_positive_contract_size_is_rejected(
        self, tmp_path: Path, bad_value: str
    ) -> None:
        """Zero reports every trade as breaking even and a negative one
        reports every loss as a profit. Both are silent."""
        config = tmp_path / "instruments.yaml"
        config.write_text(f"instruments:\n  XAUUSD:\n    contract_size: {bad_value}\n")

        with pytest.raises(ValidationError, match="greater_than"):
            load_instrument_specs(config)

    def test_a_missing_contract_size_is_rejected(self, tmp_path: Path) -> None:
        config = tmp_path / "instruments.yaml"
        config.write_text("instruments:\n  XAUUSD:\n    digits: 2\n")

        with pytest.raises(ValidationError, match="contract_size"):
            load_instrument_specs(config)
