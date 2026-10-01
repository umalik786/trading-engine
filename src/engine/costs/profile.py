"""Cost profile configuration: what a venue charges, and on which side.

See docs/trading-engine-architecture.md §2.8 (cost model), Appendix C.1
(components) and §6.5.6 (rule provenance).

The split this file exists to enforce: the cost MECHANISM is engine code,
the VALUES and the formula SHAPES are venue configuration. FTMO and a
future retail broker are two profiles of one mechanism, exactly as the two
firms are two profiles of one account-constraints mechanism. Changing
venue must be a config edit.

`price_basis` is the setting to be most careful with. It says what the
stored bar prices represent, and it decides which side of a trade pays the
spread. Get it wrong and the engine charges the short instead of the long,
which looks plausible on every chart and is wrong on every trade. It is
not derivable from the price data, so it is configuration carrying a
source and a verification date like any other external fact.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.core.provenance import DEFAULT_STALE_AFTER_DAYS, warn_if_unverified_or_stale

CommissionShape = Literal["per_lot_per_side", "per_lot_round_turn", "pct_notional"]


class DateRange(BaseModel):
    """An inclusive range of UTC dates, compared against a bar's open date.

    `from` is a Python keyword, so the field is `from_date` with `from` as
    its config alias -- the YAML reads naturally and the Python is legal.
    """

    model_config = ConfigDict(populate_by_name=True)

    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")

    @model_validator(mode="after")
    def _ordered(self) -> DateRange:
        if self.to_date < self.from_date:
            raise ValueError(f"range end {self.to_date} is before its start {self.from_date}")
        return self

    def contains(self, day: date) -> bool:
        return self.from_date <= day <= self.to_date


class Commission(BaseModel):
    """What the venue charges per trade, beyond the spread.

    Shapes:
    - `per_lot_per_side`     -- `value` currency units per lot, on every fill.
    - `per_lot_round_turn`   -- `value` currency units per lot for the
      complete in-and-out, charged IN FULL AT ENTRY. Pessimistic, and
      common broker practice.
    - `pct_notional`         -- `value` PERCENT of notional
      (lots x contract_size x fill price). A value of "0.01" means 0.01%,
      not 1%.
    """

    shape: CommissionShape
    value: Decimal = Field(ge=0)


class InstrumentCosts(BaseModel):
    commission: Commission

    # Used when a bar's spread is zero and that zero is judged to be
    # missing data rather than a real zero. Optional only so a profile can
    # omit it where no zero is expected; if a zero then turns up and
    # resolves to missing, the cost model raises rather than treating the
    # trade as free.
    fallback_spread: Decimal | None = Field(default=None, ge=0)

    # Phase 3c owns slippage. It is zero here, and visibly so: the term is
    # wired into the executable price and exercised by a test that sets it
    # non-zero, because a zero that is never used cannot be told apart
    # from one that was never connected.
    slippage_price_units: Decimal = Field(default=Decimal(0), ge=0)

    # Date ranges in which a spread of zero is a REAL zero. Everything
    # outside them is treated as missing data. See
    # `ConfiguredCostModel.resolved_spread` for why the default is that
    # every zero is missing.
    zero_spread_genuine: list[DateRange] = Field(default_factory=list)


class CostProfile(BaseModel):
    profile: str
    rules_verified: date | None = None  # see §6.5.6; None means never verified
    rules_source: str | None = None
    price_basis: Literal["bid", "mid"]
    instruments: dict[str, InstrumentCosts]


def load_cost_profile(path: Path, stale_after_days: int = DEFAULT_STALE_AFTER_DAYS) -> CostProfile:
    """Load and validate a cost profile from YAML.

    Warns (does not raise) per §6.5.6 if the verified/source pair is
    incomplete or stale, on the same terms as account constraints: a date
    with no source is not a verification, and neither is a source with no
    date.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    profile = CostProfile.model_validate(raw["cost_profile"])
    warn_if_unverified_or_stale(
        subject=f"cost profile {profile.profile}",
        verified=profile.rules_verified,
        source=profile.rules_source,
        stale_after_days=stale_after_days,
        stacklevel=3,
    )
    return profile
