"""The fitted spread-correction table (phase 3c.2).

The cost profile says HOW each instrument's spread is corrected (form,
structure, percentile). This file holds the fitted VALUES, produced by
fit_spread_correction.py for a stated cutoff, `fit_until`: every tick it was
fitted on came from a sampled week ending at or before that instant.

The cost model refuses to cost any bar opening before `fit_until`, so a
table can never be applied to the period it was fitted on -- the correction
is fitted only on data before the backtest starts (decided 2026-11-19).

Values are exact: whole points as "14", percentages as fractions like
"2/3". Nothing is floating point, so a table reproduces to the last digit.
"""

from __future__ import annotations

import json
import warnings
from datetime import datetime, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# The live table warns when its data is older than this (operator decision
# 2026-11-20, mirroring the swap-rate staleness check). Backtests use older
# tables on purpose and do not call the check.
STALE_AFTER_DAYS = 60
_HOURS = frozenset(range(24))


def _exact(text: str) -> Fraction:
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        raise ValueError(f"{text!r} is not an exact number") from None


class InstrumentCorrection(BaseModel):
    """One instrument's fitted corrections, one per server hour 0-23."""

    model_config = ConfigDict(extra="forbid")

    form: Literal["points", "percentage"]
    structure: Literal["per_hour", "constant"]
    percentile: int = Field(ge=1, le=100)
    weeks: int = Field(ge=0)  # sampled weeks the values were fitted on
    corrections: dict[int, str]

    @model_validator(mode="after")
    def _complete_and_exact(self) -> InstrumentCorrection:
        if set(self.corrections) != _HOURS:
            raise ValueError("corrections must give all 24 server hours, 0-23")
        for hour, text in self.corrections.items():
            value = _exact(text)
            if self.form == "points" and value.denominator != 1:
                raise ValueError(
                    f"hour {hour}: a points correction must be a whole number of points, "
                    f"got {text!r}"
                )
        return self

    def value(self, hour: int) -> int | Fraction:
        value = _exact(self.corrections[hour])
        return value.numerator if value.denominator == 1 else value


class SpreadCorrectionTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fit_until: datetime
    fitted_at: datetime
    source_server: str
    provenance: dict[str, str]
    instruments: dict[str, InstrumentCorrection]

    @field_validator("fit_until", "fitted_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError(f"must be a UTC datetime, got {value!r}")
        return value


def load_correction_table(path: Path) -> SpreadCorrectionTable:
    return SpreadCorrectionTable.model_validate(json.loads(path.read_text(encoding="utf-8")))


def warn_if_table_stale(
    table: SpreadCorrectionTable, now: datetime, stale_after_days: int = STALE_AFTER_DAYS
) -> None:
    """Warn (never raise) when the table's data is older than the threshold.
    Age is measured from `fit_until`, the newest data it saw, because that is
    what goes stale -- not the day the file was written. For live trading."""
    age_days = (now - table.fit_until).days
    if age_days > stale_after_days:
        warnings.warn(
            f"spread-correction table fitted until {table.fit_until:%Y-%m-%d} is "
            f"{age_days} days old, older than the {stale_after_days}-day threshold -- "
            "refit it on the latest sampled weeks",
            stacklevel=2,
        )
