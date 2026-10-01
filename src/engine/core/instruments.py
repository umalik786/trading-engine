"""Per-instrument specifications, loaded from configuration.

One field so far: `contract_size`, the multiplier that turns a price move
into money (P&L = lots x contract_size x price change). More of the
symbol specification -- volume step, minimum volume, digits, margin --
arrives with the sizer, which needs it.

This is a config file rather than a dict in Python because Appendix A.6
requires it: these are broker facts, read from `symbol_info()` at startup
and held in adapter configuration, never written into engine source.

The loader takes an explicit path and has no default, matching
`load_account_constraints`. A default relative path would resolve against
whatever directory the process happened to start in, which is one of the
easier ways to load the wrong file and not notice.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class InstrumentSpec(BaseModel):
    # gt=0 because a zero multiplier reports every trade as breaking even
    # and a negative one reports every loss as a profit. Both are silent.
    contract_size: Decimal = Field(gt=0)
    # The smallest quoted price increment, 10^-digits. MT5 reports spread
    # as a count of points; the feed multiplies by this to get price units.
    # gt=0 for the same reason: a zero point size makes every spread zero.
    point: Decimal = Field(gt=0)


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
