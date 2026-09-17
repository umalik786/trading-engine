from datetime import UTC, datetime, timedelta

import pytest

from engine.core.provenance import warn_if_unverified_or_stale


class TestWarnIfUnverifiedOrStale:
    def test_missing_verified_date_warns(self) -> None:
        with pytest.warns(UserWarning, match="verification is incomplete"):
            warn_if_unverified_or_stale("thing", verified=None, source="https://example.com")

    def test_missing_source_warns(self) -> None:
        with pytest.warns(UserWarning, match="verification is incomplete"):
            warn_if_unverified_or_stale(
                "thing", verified=datetime.now(UTC).date(), source=None
            )

    def test_missing_both_warns(self) -> None:
        with pytest.warns(UserWarning, match="verification is incomplete"):
            warn_if_unverified_or_stale("thing", verified=None, source=None)

    def test_stale_verification_warns(self) -> None:
        old_date = (datetime.now(UTC) - timedelta(days=200)).date()
        with pytest.warns(UserWarning, match="days old"):
            warn_if_unverified_or_stale(
                "thing", verified=old_date, source="https://example.com", stale_after_days=90
            )

    def test_fresh_complete_verification_does_not_warn(
        self, recwarn: pytest.WarningsRecorder
    ) -> None:
        warn_if_unverified_or_stale(
            "thing",
            verified=datetime.now(UTC).date(),
            source="https://example.com",
            stale_after_days=90,
        )
        assert len(recwarn) == 0
