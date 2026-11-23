"""Per-instrument specifications, loaded from configuration.

`contract_size` is the multiplier that turns a price move into money
(P&L = lots x contract_size x price change). The volume minimum, step and
maximum arrived with the sizer (phase 3c.3), which rounds to them. Margin
is not here yet: checking it is the risk gate's job (phase 4).

This is a config file rather than a dict in Python because Appendix A.6
requires it: these are broker facts, read from `symbol_info()` at startup
and held in adapter configuration, never written into engine source.

The loader takes an explicit path and has no default, matching
`load_account_constraints`. A default relative path would resolve against
whatever directory the process happened to start in, which is one of the
easier ways to load the wrong file and not notice.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


class InstrumentSpec(BaseModel):
    # gt=0 because a zero multiplier reports every trade as breaking even
    # and a negative one reports every loss as a profit. Both are silent.
    contract_size: Decimal = Field(gt=0)
    # The smallest quoted price increment, 10^-digits. MT5 reports spread
    # as a count of points; the feed multiplies by this to get price units.
    # gt=0 for the same reason: a zero point size makes every spread zero.
    point: Decimal = Field(gt=0)
    # The currency the instrument is quoted in. Compared against the cost
    # profile's account currency, which raises on a mismatch rather than
    # converting at an FX rate nobody has verified.
    quote_currency: str = "USD"
    # Per timeframe, the UTC instant from which stored bars genuinely have
    # that timeframe's width. Before it, a venue may have filed bars of
    # another width under the same timeframe -- on FTMO, index "M15" before
    # September 2021 is daily then hourly bars. A timeframe absent here has
    # no restriction. See check_bar_spacing.py, which is how these are found.
    bars_genuine_from: dict[str, datetime] = Field(default_factory=dict)
    # Volume limits in lots (phase 3c.3). No defaults: a missing step would
    # leave the sizer free to order sizes the broker refuses, and there is no
    # venue-neutral guess. The minimum and maximum must be whole multiples of
    # the step, so "round down to the step" can only produce a volume the
    # broker accepts.
    volume_min: Decimal = Field(gt=0)
    volume_step: Decimal = Field(gt=0)
    volume_max: Decimal = Field(gt=0)

    @field_validator("volume_min", "volume_step", "volume_max", mode="before")
    @classmethod
    def _no_floats(cls, value: object, info: ValidationInfo) -> object:
        if isinstance(value, float):
            raise ValueError(
                f"{info.field_name} was read as a float ({value!r}); quote it so it is "
                "parsed as exact decimal text"
            )
        return value

    @model_validator(mode="after")
    def _volumes_fit_the_step(self) -> InstrumentSpec:
        if self.volume_min > self.volume_max:
            raise ValueError(
                f"volume minimum {self.volume_min} is above the maximum {self.volume_max}"
            )
        for name in ("volume_min", "volume_max"):
            value = getattr(self, name)
            if value % self.volume_step != 0:
                raise ValueError(
                    f"{name} {value} is not a whole multiple of the step {self.volume_step}"
                )
        return self

    @field_validator("bars_genuine_from")
    @classmethod
    def _must_be_utc(cls, value: dict[str, datetime]) -> dict[str, datetime]:
        for timeframe, instant in value.items():
            if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
                raise ValueError(
                    f"bars_genuine_from[{timeframe}] must be a UTC datetime "
                    f"(end it in Z), got {instant!r}"
                )
        return value


def load_instrument_specs(path: Path) -> dict[str, InstrumentSpec]:
    """Load and validate every instrument spec in a YAML config file."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        symbol: InstrumentSpec.model_validate(fields)
        for symbol, fields in raw["instruments"].items()
    }


def load_contract_sizes(path: Path) -> dict[str, Decimal]:
    """The {symbol: contract_size} mapping `Portfolio` is constructed with."""
    return {symbol: spec.contract_size for symbol, spec in load_instrument_specs(path).items()}


def load_point_sizes(path: Path) -> dict[str, Decimal]:
    """The {symbol: point} mapping a feed needs to convert MT5's spread
    from points into price units."""
    return {symbol: spec.point for symbol, spec in load_instrument_specs(path).items()}


def load_bars_genuine_from(path: Path) -> dict[str, dict[str, datetime]]:
    """The {symbol: {timeframe: instant}} mapping a feed is constructed
    with, so it refuses to read bars from before a series is genuine."""
    specs = load_instrument_specs(path)
    return {symbol: dict(spec.bars_genuine_from) for symbol, spec in specs.items()}
