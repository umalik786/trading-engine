"""Account-constraints configuration schema and loader.

See docs/trading-engine-architecture.md §6.5.3 (schema), §6.5.4 (internal
margin) and §6.5.6 (rule provenance). Schema only -- nothing here acts on
these limits; that is phase 4.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, field_validator, model_validator

from engine.core.provenance import DEFAULT_STALE_AFTER_DAYS, warn_if_unverified_or_stale

_RESET_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class AccountingDay(BaseModel):
    reset_time: str  # "HH:MM", the firm's local reset time
    timezone: str  # IANA name; DST handled by the library, never by arithmetic

    @field_validator("reset_time")
    @classmethod
    def _validate_reset_time(cls, v: str) -> str:
        if not _RESET_TIME_PATTERN.fullmatch(v):
            raise ValueError(f"reset_time must be HH:MM (00-23:00-59), got {v!r}")
        return v

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"timezone must be a real IANA name, got {v!r}") from exc
        return v


class DailyLoss(BaseModel):
    external_pct: Decimal | None = None  # the firm's limit; omitted on a personal account
    internal_pct: Decimal  # ours, fires first -- see §6.5.4
    measured_on: Literal["equity", "closed_balance"]
    anchor: Literal["initial_balance", "day_open_balance"]

    @model_validator(mode="after")
    def _internal_below_external(self) -> DailyLoss:
        if self.external_pct is not None and self.internal_pct >= self.external_pct:
            raise ValueError(
                f"daily_loss.internal_pct ({self.internal_pct}) must be < "
                f"external_pct ({self.external_pct}) -- an internal limit at or "
                "above the external one is not a limit, see §6.5.4"
            )
        return self


class MaxLoss(BaseModel):
    external_pct: Decimal | None = None  # the firm's limit; omitted on a personal account
    internal_pct: Decimal  # ours, fires first -- see §6.5.4
    mode: Literal["static", "trailing_eod"]

    @model_validator(mode="after")
    def _internal_below_external(self) -> MaxLoss:
        if self.external_pct is not None and self.internal_pct >= self.external_pct:
            raise ValueError(
                f"max_loss.internal_pct ({self.internal_pct}) must be < "
                f"external_pct ({self.external_pct}) -- an internal limit at or "
                "above the external one is not a limit, see §6.5.4"
            )
        return self


class AccountConstraints(BaseModel):
    profile: str
    rules_verified: date | None = None  # see §6.5.6; None means never verified
    rules_source: str | None = None  # URL for the loss-limit figures; not a comparison site
    automation_policy_source: str | None = None  # URL for the firm's automation/EA policy
    accounting_day: AccountingDay
    daily_loss: DailyLoss
    max_loss: MaxLoss


def load_account_constraints(
    path: Path, stale_after_days: int = DEFAULT_STALE_AFTER_DAYS
) -> AccountConstraints:
    """Load and validate an account_constraints profile from YAML.

    Warns (does not raise) per §6.5.6 if the profile's rules_verified/
    rules_source pair is incomplete (either missing) or stale -- see
    `warn_if_unverified_or_stale`. A verified date with no source is not a
    verification, and neither is a source with no date.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    constraints = AccountConstraints.model_validate(raw["account_constraints"])
    warn_if_unverified_or_stale(
        subject=constraints.profile,
        verified=constraints.rules_verified,
        source=constraints.rules_source,
        stale_after_days=stale_after_days,
        stacklevel=3,
    )
    return constraints
