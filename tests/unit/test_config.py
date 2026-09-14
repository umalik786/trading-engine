from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pydantic
import pytest
import yaml

from engine.core.config import AccountConstraints, load_account_constraints

FUNDEDNEXT_YAML = Path("config/fundednext_stellar_2step.yaml")
FTMO_YAML = Path("config/ftmo_2step.yaml")


def _valid_raw() -> dict:
    return {
        "profile": "fundednext_stellar_2step",
        "rules_verified": "2026-09-10",
        "rules_source": "https://help.fundednext.com/en/articles/8020763",
        "accounting_day": {"reset_time": "00:00", "timezone": "Europe/Prague"},
        "daily_loss": {
            "external_pct": 5.0,
            "internal_pct": 3.0,
            "measured_on": "equity",
            "anchor": "initial_balance",
        },
        "max_loss": {"external_pct": 10.0, "internal_pct": 6.0, "mode": "static"},
    }


class TestValidLoad:
    def test_fundednext_config_loads(self) -> None:
        constraints = load_account_constraints(FUNDEDNEXT_YAML)
        assert constraints.profile == "fundednext_stellar_2step"
        assert constraints.daily_loss.external_pct == Decimal("5.0")
        assert constraints.max_loss.mode == "static"

    def test_ftmo_config_loads(self) -> None:
        constraints = load_account_constraints(FTMO_YAML)
        assert constraints.profile == "ftmo_2step"
        assert constraints.rules_verified is None

    def test_percentages_are_decimal_not_float(self) -> None:
        constraints = AccountConstraints.model_validate(_valid_raw())
        assert isinstance(constraints.daily_loss.external_pct, Decimal)
        assert isinstance(constraints.daily_loss.internal_pct, Decimal)
        assert isinstance(constraints.max_loss.external_pct, Decimal)
        assert isinstance(constraints.max_loss.internal_pct, Decimal)


class TestTimezoneValidation:
    def test_invalid_iana_timezone_rejected(self) -> None:
        raw = _valid_raw()
        raw["accounting_day"]["timezone"] = "Not/A_Real_Zone"
        with pytest.raises(pydantic.ValidationError, match="real IANA name"):
            AccountConstraints.model_validate(raw)

    def test_valid_iana_timezone_accepted(self) -> None:
        raw = _valid_raw()
        raw["accounting_day"]["timezone"] = "America/New_York"
        constraints = AccountConstraints.model_validate(raw)
        assert constraints.accounting_day.timezone == "America/New_York"


class TestInternalExternalOrdering:
    def test_daily_loss_internal_at_external_rejected(self) -> None:
        raw = _valid_raw()
        raw["daily_loss"]["internal_pct"] = 5.0  # equal to external_pct
        with pytest.raises(pydantic.ValidationError, match="must be <"):
            AccountConstraints.model_validate(raw)

    def test_daily_loss_internal_above_external_rejected(self) -> None:
        raw = _valid_raw()
        raw["daily_loss"]["internal_pct"] = 6.0  # above external_pct
        with pytest.raises(pydantic.ValidationError, match="must be <"):
            AccountConstraints.model_validate(raw)

    def test_max_loss_internal_at_external_rejected(self) -> None:
        raw = _valid_raw()
        raw["max_loss"]["internal_pct"] = 10.0  # equal to external_pct
        with pytest.raises(pydantic.ValidationError, match="must be <"):
            AccountConstraints.model_validate(raw)


class TestPersonalAccount:
    def test_config_with_no_external_pct_loads_fine(self) -> None:
        raw = _valid_raw()
        del raw["daily_loss"]["external_pct"]
        del raw["max_loss"]["external_pct"]
        constraints = AccountConstraints.model_validate(raw)
        assert constraints.daily_loss.external_pct is None
        assert constraints.max_loss.external_pct is None
        # internal limits still apply and are still enforced as the only limits
        assert constraints.daily_loss.internal_pct == Decimal("3.0")
        assert constraints.max_loss.internal_pct == Decimal("6.0")


class TestRoundTrip:
    @pytest.mark.parametrize("yaml_path", [FUNDEDNEXT_YAML, FTMO_YAML])
    def test_load_dump_reload_matches_original(self, yaml_path: Path) -> None:
        original = load_account_constraints(yaml_path)
        dumped = original.model_dump(mode="json")
        reloaded = AccountConstraints.model_validate(dumped)
        assert reloaded == original

    def test_round_trip_preserves_yaml_values(self) -> None:
        raw = yaml.safe_load(FUNDEDNEXT_YAML.read_text(encoding="utf-8"))["account_constraints"]
        original = AccountConstraints.model_validate(raw)
        dumped = original.model_dump(mode="json")
        reloaded = AccountConstraints.model_validate(dumped)

        assert reloaded.profile == raw["profile"]
        assert str(reloaded.rules_verified) == raw["rules_verified"]
        assert reloaded.rules_source == raw["rules_source"]
        assert reloaded.accounting_day.reset_time == raw["accounting_day"]["reset_time"]
        assert reloaded.accounting_day.timezone == raw["accounting_day"]["timezone"]
        assert reloaded.daily_loss.external_pct == Decimal(str(raw["daily_loss"]["external_pct"]))
        assert reloaded.daily_loss.internal_pct == Decimal(str(raw["daily_loss"]["internal_pct"]))
        assert reloaded.max_loss.external_pct == Decimal(str(raw["max_loss"]["external_pct"]))
        assert reloaded.max_loss.internal_pct == Decimal(str(raw["max_loss"]["internal_pct"]))


class TestRuleProvenanceWarning:
    def test_never_verified_profile_warns_at_load(self) -> None:
        with pytest.warns(UserWarning, match="never been checked"):
            load_account_constraints(FTMO_YAML)

    def test_stale_rules_verified_warns_at_load(self, tmp_path: Path) -> None:
        raw = _valid_raw()
        stale_date = (datetime.now(UTC).date() - timedelta(days=200)).isoformat()
        raw["rules_verified"] = stale_date
        config_path = tmp_path / "stale.yaml"
        config_path.write_text(
            yaml.safe_dump({"account_constraints": raw}), encoding="utf-8"
        )
        with pytest.warns(UserWarning, match="days old"):
            load_account_constraints(config_path)

    def test_recently_verified_profile_does_not_warn(
        self, tmp_path: Path, recwarn: pytest.WarningsRecorder
    ) -> None:
        raw = _valid_raw()
        raw["rules_verified"] = datetime.now(UTC).date().isoformat()
        config_path = tmp_path / "fresh.yaml"
        config_path.write_text(yaml.safe_dump({"account_constraints": raw}), encoding="utf-8")
        load_account_constraints(config_path)
        assert len(recwarn) == 0
