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

PROVENANCE IS PER SECTION, not per file. The swap rates were read from
`symbol_info()` on a known date and are verified facts; the commission
figures and `price_basis` are placeholders nobody has confirmed. A single
`rules_verified` for the whole profile would force one of those to be
mislabelled. The precedent is `ftmo_2step.yaml`, which already keeps
`accounting_day_verified` apart from `rules_source`. Each section also
sets its own staleness threshold, because swap rates are revised far more
often than a firm's rulebook.
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
SwapShape = Literal["points", "currency_per_lot", "disabled"]
Weekday = Literal[
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
]

# Swap rates are revised by brokers far more often than rulebooks change.
FINANCING_STALE_AFTER_DAYS = 30

WEEKDAY_NUMBERS = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}


class Provenance(BaseModel):
    """Where one section's numbers came from, and when they were checked."""

    verified: date | None = None
    source: str | None = None
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS

    def warn_if_stale(self, subject: str) -> None:
        warn_if_unverified_or_stale(
            subject=subject,
            verified=self.verified,
            source=self.source,
            stale_after_days=self.stale_after_days,
            stacklevel=4,
        )


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


class ServerClockConfig(BaseModel):
    """Which clock the trade server runs. See `engine.core.clock`.

    Two shapes, because this is venue configuration:

    - `iana` -- a real, nameable timezone. Needs `zone`.
    - `dst_switched_offsets` -- fixed winter and summer offsets switching
      on another region's DST calendar. Needs all three of
      `winter_offset_hours`, `summer_offset_hours` and `dst_calendar`.
      FTMO is +2/+3 on America/New_York, a combination no IANA zone
      describes.

    NOT the §6.5 accounting-day clock, which is a separate setting in a
    separate file. The two differ by two hours for a few weeks each spring
    and autumn.
    """

    shape: Literal["iana", "dst_switched_offsets"]
    zone: str | None = None
    winter_offset_hours: int | None = None
    summer_offset_hours: int | None = None
    dst_calendar: str | None = None
    provenance: Provenance = Field(default_factory=Provenance)

    @model_validator(mode="after")
    def _fields_match_shape(self) -> ServerClockConfig:
        if self.shape == "iana":
            if self.zone is None:
                raise ValueError("server_clock shape 'iana' requires a zone")
        elif (
            self.winter_offset_hours is None
            or self.summer_offset_hours is None
            or self.dst_calendar is None
        ):
            raise ValueError(
                "server_clock shape 'dst_switched_offsets' requires "
                "winter_offset_hours, summer_offset_hours and dst_calendar"
            )
        return self


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


class SwapRates(BaseModel):
    """Overnight financing for one instrument.

    RATES ARE SIGNED, and the sign is load-bearing: negative is charged to
    the account, positive is paid to it. Two of the five instruments on
    this venue currently credit a short, so a mechanism that assumed
    financing is always a cost would be wrong today, not hypothetically.

    Shapes mirror MT5's ENUM_SYMBOL_SWAP_MODE:
    - `points` (mode 1) -- rate in points; money is
      `rate x point x contract_size` per lot per night. What FTMO uses on
      every instrument.
    - `currency_per_lot` (mode 4) -- rate already in account currency per
      lot per night. The common retail shape.
    - `disabled` (mode 0) -- no financing.

    Modes 2, 3, 5, 6, 7 and 8 are deliberately unimplemented: the interest
    modes need a day-count convention that is another unverified external
    fact, and the reopen modes alter the position's open price rather than
    charging money. The cost model raises on them by name rather than
    approximating.

    `triple_weekday` is the day charged three times, to collect the
    weekend's value dates. Per instrument, because it need not be the same
    everywhere. `null` means no triple day.
    """

    shape: SwapShape
    long_rate: Decimal = Decimal(0)
    short_rate: Decimal = Decimal(0)
    triple_weekday: Weekday | None = None


class FinancingConfig(BaseModel):
    provenance: Provenance = Field(
        default_factory=lambda: Provenance(stale_after_days=FINANCING_STALE_AFTER_DAYS)
    )
    instruments: dict[str, SwapRates] = Field(default_factory=dict)


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
    # Every money figure the cost model produces is in this currency. An
    # instrument quoted in anything else would need an FX rate nobody has
    # verified, so the cost model raises rather than converting silently.
    account_currency: str = "USD"
    server_clock: ServerClockConfig | None = None
    financing: FinancingConfig = Field(default_factory=FinancingConfig)
    instruments: dict[str, InstrumentCosts]

    @model_validator(mode="after")
    def _financing_covers_every_instrument(self) -> CostProfile:
        """Every instrument the profile covers must have a financing entry,
        and vice versa.

        Enforced at load rather than at the first rollover. A missing entry
        already raises when financing is asked for, but that happens part
        way through a run, on whichever instrument happened to be held
        overnight first -- and a profile that covers an instrument for
        commission while forgetting its swap is wrong the moment it is
        written, not the moment it is used.

        "This instrument has no swap" remains sayable: write
        `shape: disabled`. What is refused is silence.
        """
        covered = set(self.instruments)
        financed = set(self.financing.instruments)
        if covered == financed:
            return self
        missing = covered - financed
        orphaned = financed - covered
        problems = []
        if missing:
            problems.append(
                f"no financing entry for {sorted(missing)} -- an omission would price "
                "overnight holding as free; use shape: disabled to say there is none"
            )
        if orphaned:
            problems.append(
                f"financing entries for {sorted(orphaned)}, which the profile does not "
                "otherwise cover -- either the name is wrong or the instrument is "
                "missing its commission entry"
            )
        raise ValueError(f"cost profile {self.profile!r}: " + "; ".join(problems))

    @model_validator(mode="after")
    def _financing_needs_a_clock(self) -> CostProfile:
        charges = any(rates.shape != "disabled" for rates in self.financing.instruments.values())
        if charges and self.server_clock is None:
            raise ValueError(
                "financing is configured but server_clock is not -- the rollover "
                "instant is midnight on the server's clock, and there is no "
                "default for which clock that is"
            )
        return self


def load_cost_profile(path: Path, stale_after_days: int = DEFAULT_STALE_AFTER_DAYS) -> CostProfile:
    """Load and validate a cost profile from YAML.

    Warns (does not raise) per §6.5.6 for the profile as a whole and for
    each section that carries its own provenance. A date with no source is
    not a verification, and neither is a source with no date.
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
    if profile.financing.instruments:
        profile.financing.provenance.warn_if_stale(f"{profile.profile} financing")
    if profile.server_clock is not None:
        profile.server_clock.provenance.warn_if_stale(f"{profile.profile} server clock")
    return profile
