"""EquitySizer -- weight-based, and risk-based when a stop is given.

See docs/trading-engine-architecture.md §2.5. Rules approved by the operator
2026-11-23 (docs/state.md, phase 3c.3).

HOW BIG, BEFORE ROUNDING
------------------------
"close" is the DECIDING bar's close; "equity" is the portfolio's equity as
marked at that close -- balance plus open P&L at quoted prices, the figure
the firm uses.

    weight w, no stop:  |w| x equity / (contract size x close)
    a stop:             risk fraction x equity / (contract size x |close - stop|)
    quantity q:         |q|

For a stop, the weight gives only the DIRECTION and must be exactly +1 or -1;
any other weight is refused as a second answer to "how big" (operator,
2026-11-23, decision C). The
risk fraction is this sizer's configuration -- the operator's choice, not a
firm rule and not the strategy's.

THEN, IN ORDER
--------------
1. Round TOWARD ZERO to a whole number of volume steps: smaller, for a long
   and a short alike. Rounding up would exceed the size or risk asked for.
2. Below the volume minimum -> 0, no order. Rounding up to the minimum
   would breach the risk budget.
3. Above the volume maximum -> the maximum.
4. Apply the target's sign.

Arithmetic is exact (fractions), so no rounding enters before step 1's
deliberate one: a quotient that lands a hair under a step boundary in
28-digit decimal arithmetic cannot lose a whole step.

THE HOLD RULE -- weight and stop targets only (decision A)
----------------------------------------------------------
If the committed position (held plus ordered) is non-zero and in the
target's direction, it is returned unchanged: the position is sized on entry
and then held. Otherwise every bar's movement in equity would re-size it, a
little trade every bar -- rebalancing, which is a decision for the
position-conventions step. A quantity target is NOT held: it orders the
difference, exactly as before. Consequence, recorded: changing a weight in
the same direction has no effect until position conventions are built.

KNOWN UNDERSTATEMENT
--------------------
The risk distance is the raw price distance. A real stop-out also pays
spread, slippage and commission, so the loss at the stop exceeds the risk
budget by those. To be revisited when stops are executed, because the cost
depends on how a stop fills. (Stops are not executed yet; the backtest loop
stops the run if a price reaches one.)

WHAT THE SIZER CHANGED IS RECORDED
----------------------------------
A cap, a size below the minimum and a non-positive equity each add a
`SizingNote`, so an adjustment is visible rather than silent. Into the
decision log at orchestrator design.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from math import floor
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from engine.core.instruments import InstrumentSpec
from engine.core.portfolio import PortfolioView
from engine.core.types import TargetPosition
from engine.sizing.base import SizingContext


class SizingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Fraction of equity lost if a stop is hit, before costs. No default:
    # how much to risk is the operator's choice and must be written down.
    risk_fraction: Decimal = Field(gt=0, le=1)

    @field_validator("risk_fraction", mode="before")
    @classmethod
    def _no_floats(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError(
                f"risk_fraction was read as a float ({value!r}); quote it so it is "
                "parsed as exact decimal text"
            )
        return value


def load_sizing_config(path: Path) -> SizingConfig:
    """Load the `sizing:` block of a YAML file. Explicit path, no default."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SizingConfig.model_validate(raw["sizing"])


# "no_bar_yet" is written by the bar loop, not the sizer: a target for a
# symbol whose first bar has not arrived waits, because there is no close to
# size it from (operator, 2026-11-23).
NoteKind = Literal["capped_at_maximum", "below_minimum", "equity_not_positive", "no_bar_yet"]


@dataclass(frozen=True)
class SizingNote:
    """Something the sizer changed or declined. `rounded` is the size after
    rounding to the step and before the limits; `final` is what was sized."""

    ts: datetime  # the deciding bar's close
    symbol: str
    kind: NoteKind
    rounded: Decimal
    final: Decimal


def _sign(value: Decimal) -> int:
    return (value > 0) - (value < 0)


class EquitySizer:
    def __init__(self, config: SizingConfig) -> None:
        self._config = config
        self.notes: list[SizingNote] = []

    def size(
        self,
        target: TargetPosition,
        portfolio: PortfolioView,
        features: Mapping[str, Any],  # noqa: ARG002 -- not used by these rules
        context: SizingContext,
    ) -> Decimal:
        spec = context.spec
        if spec is None:
            raise ValueError(
                f"{target.symbol}: EquitySizer needs the instrument spec (volume limits, "
                "contract size); the run was given none"
            )
        stop = target.stop_price
        if stop is not None and target.quantity is not None:
            raise ValueError(
                f"{target.symbol}: a stop with a quantity gives two answers to 'how big' "
                "(the stop's risk and the quantity); give a weight for its direction"
            )

        if target.quantity is not None:
            # Ordered as the difference, as before: no hold rule.
            direction = _sign(target.quantity)
            raw = abs(Fraction(target.quantity))
        else:
            assert target.weight is not None  # TargetPosition guarantees one of the two
            direction = _sign(target.weight)
            if direction == 0:
                if stop is not None:
                    raise ValueError(f"{target.symbol}: a stop on a flat target")
                return Decimal(0)
            if stop is not None and abs(target.weight) != 1:
                raise ValueError(
                    f"{target.symbol}: a stop with weight {target.weight} gives two answers "
                    "to 'how big' (the stop's risk and the weight); a stop target's weight "
                    "must be +1 or -1, giving only the direction"
                )
            close = context.bar.close
            if stop is not None and _sign(close - stop) != direction:
                raise ValueError(
                    f"{target.symbol}: stop {stop} is on the wrong side of the close "
                    f"{close} for a {'long' if direction > 0 else 'short'}"
                )
            if context.committed != 0 and _sign(context.committed) == direction:
                return context.committed  # the hold rule
            equity = portfolio.equity
            if equity <= 0:
                self._note(context, target, "equity_not_positive", Decimal(0), Decimal(0))
                return Decimal(0)
            size = Fraction(spec.contract_size)
            if stop is None:
                raw = abs(Fraction(target.weight)) * Fraction(equity) / (size * Fraction(close))
            else:
                distance = abs(Fraction(close) - Fraction(stop))
                raw = Fraction(self._config.risk_fraction) * Fraction(equity) / (size * distance)

        return self._round_and_limit(raw, direction, spec, context, target)

    def _round_and_limit(
        self,
        raw: Fraction,
        direction: int,
        spec: InstrumentSpec,
        context: SizingContext,
        target: TargetPosition,
    ) -> Decimal:
        """Steps 1-4 of the module docstring: toward zero to the step, below
        the minimum to zero, above the maximum to it, then the sign."""
        if raw == 0:
            return Decimal(0)
        rounded = floor(raw / Fraction(spec.volume_step)) * spec.volume_step
        final = rounded
        if rounded < spec.volume_min:
            final = Decimal(0)
            self._note(context, target, "below_minimum", rounded, final)
        elif rounded > spec.volume_max:
            final = spec.volume_max
            self._note(context, target, "capped_at_maximum", rounded, final)
        return direction * final if final else Decimal(0)  # never a signed zero

    def _note(
        self,
        context: SizingContext,
        target: TargetPosition,
        kind: NoteKind,
        rounded: Decimal,
        final: Decimal,
    ) -> None:
        self.notes.append(SizingNote(context.bar.ts_close, target.symbol, kind, rounded, final))
