"""Shared provenance-verification warning. See spec §6.5.6.

A claim about external, changeable reality -- a firm's rulebook figures, a
broker's server timezone convention -- is only as good as knowing when it
was last checked and against what. Account-constraints config loading and
extraction-data manifests both need the identical check: is there a
verification date, is there a source behind it, and is it stale. This
lives in one place so the two never drift into two different definitions
of "verified."
"""

from __future__ import annotations

import warnings
from datetime import UTC, date, datetime

DEFAULT_STALE_AFTER_DAYS = 90


def warn_if_unverified_or_stale(
    subject: str,
    verified: date | None,
    source: str | None,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
    stacklevel: int = 2,
) -> None:
    """Warn (never raise) if a provenance claim is incomplete or stale.

    A verification date with no source, or a source with no date, is not a
    verification -- both are required together, per §6.5.6. If both are
    present, warn when `verified` is older than `stale_after_days`: firm
    rules and broker configuration change without notice, so any claim
    needs an expiry, not just an origin.
    """
    if verified is None or source is None:
        warnings.warn(
            f"{subject}: verification is incomplete (verified={verified}, "
            f"source={source!r}) -- a date with no source, or a source with "
            "no date, is not a verification (spec section 6.5.6)",
            stacklevel=stacklevel,
        )
        return
    age_days = (datetime.now(UTC).date() - verified).days
    if age_days > stale_after_days:
        warnings.warn(
            f"{subject}: verified {verified} is {age_days} days old, older "
            f"than the {stale_after_days}-day threshold -- re-verify against "
            f"{source} (spec section 6.5.6)",
            stacklevel=stacklevel,
        )
