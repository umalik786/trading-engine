"""Venue configuration: facts about the account the engine's behaviour
depends on. See docs/trading-engine-architecture.md §2.10 (spec v3.12).

Today that is one fact, the position mode. It is configuration, never an
engine assumption, because it is a property of the account: both candidate
venues are hedging (margin_mode 2, verified 2026-09-29), and a different
venue could be netting. Changing venue must be a config edit.

It carries its provenance like every other external fact (§6.5.6): a date
and a source, both required, and a warning when either is missing or the
date is stale. A live adapter checks the account's actual mode against
this at startup and halts on a mismatch (§2.7, phase 7).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel

from engine.core.provenance import DEFAULT_STALE_AFTER_DAYS, warn_if_unverified_or_stale
from engine.core.types import PositionMode


class VenueConfig(BaseModel):
    venue: str
    position_mode: PositionMode
    position_mode_verified: date | None = None
    position_mode_source: str | None = None


def load_venue_config(path: Path, stale_after_days: int = DEFAULT_STALE_AFTER_DAYS) -> VenueConfig:
    """Load and validate a venue file. Warns (never raises) if the position
    mode's verification date or source is missing, or the date is stale."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    venue = VenueConfig.model_validate(raw["venue"])
    warn_if_unverified_or_stale(
        subject=f"{venue.venue} position_mode",
        verified=venue.position_mode_verified,
        source=venue.position_mode_source,
        stale_after_days=stale_after_days,
        stacklevel=3,
    )
    return venue
