"""Tests for the venue configuration (spec v3.12, §2.10; decision 1 of the
position conventions, 2026-11-25)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine.core.venue import load_venue_config

REPO_ROOT = Path(__file__).resolve().parents[2]
FTMO = REPO_ROOT / "config" / "venue_ftmo_demo.yaml"


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "venue.yaml"
    path.write_text(body, encoding="utf-8")
    return path


class TestFtmoVenue:
    def test_ftmo_is_hedging(self) -> None:
        assert load_venue_config(FTMO).position_mode == "hedging"

    def test_the_mode_carries_its_provenance(self) -> None:
        venue = load_venue_config(FTMO)
        assert venue.position_mode_verified == date(2026, 9, 29)
        assert "margin_mode = 2" in (venue.position_mode_source or "")


class TestValidation:
    def test_an_unknown_mode_is_refused(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "venue:\n  venue: x\n  position_mode: fifo\n")
        with pytest.raises(ValidationError, match="position_mode"):
            load_venue_config(path)

    def test_the_mode_has_no_default(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "venue:\n  venue: x\n")
        with pytest.raises(ValidationError, match="position_mode"):
            load_venue_config(path)

    def test_a_mode_without_a_source_warns(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "venue:\n  venue: x\n  position_mode: netting\n"
            '  position_mode_verified: "2026-11-01"\n',
        )
        with pytest.warns(UserWarning, match="incomplete"):
            assert load_venue_config(path).position_mode == "netting"
