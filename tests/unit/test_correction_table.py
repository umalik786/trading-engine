"""The fitted spread-correction table file (3c.2, approved 2026-11-20)."""

from __future__ import annotations

import json
import warnings
from datetime import UTC, datetime, timedelta
from fractions import Fraction

import pytest
from pydantic import ValidationError

from engine.costs.correction_table import (
    SpreadCorrectionTable,
    load_correction_table,
    warn_if_table_stale,
)

CUTOFF = datetime(2025, 1, 1, tzinfo=UTC)


def _raw(**instrument) -> dict:
    entry = {
        "form": "points",
        "structure": "per_hour",
        "percentile": 90,
        "weeks": 12,
        "corrections": {str(h): str(h) for h in range(24)},
    } | instrument
    return {
        "fit_until": CUTOFF.isoformat(),
        "fitted_at": CUTOFF.isoformat(),
        "source_server": "FTMO-Demo",
        "provenance": {"commit": "abc"},
        "instruments": {"XAUUSD": entry},
    }


def test_values_parse_exactly() -> None:
    table = SpreadCorrectionTable.model_validate(_raw())
    assert table.instruments["XAUUSD"].value(13) == 13
    pct = SpreadCorrectionTable.model_validate(
        _raw(form="percentage", corrections={str(h): "1/3" for h in range(24)})
    )
    assert pct.instruments["XAUUSD"].value(0) == Fraction(1, 3)


def test_every_hour_must_be_present() -> None:
    raw = _raw()
    del raw["instruments"]["XAUUSD"]["corrections"]["7"]
    with pytest.raises(ValidationError, match="all 24 server hours"):
        SpreadCorrectionTable.model_validate(raw)


def test_a_points_correction_must_be_whole_points() -> None:
    raw = _raw()
    raw["instruments"]["XAUUSD"]["corrections"]["3"] = "1/2"
    with pytest.raises(ValidationError, match="whole number of points"):
        SpreadCorrectionTable.model_validate(raw)


def test_a_value_that_is_not_a_number_is_refused() -> None:
    raw = _raw()
    raw["instruments"]["XAUUSD"]["corrections"]["3"] = "abc"
    with pytest.raises(ValidationError, match="not an exact number"):
        SpreadCorrectionTable.model_validate(raw)


def test_the_cutoff_must_be_utc() -> None:
    raw = _raw()
    raw["fit_until"] = "2025-01-01T00:00:00"
    with pytest.raises(ValidationError, match="UTC"):
        SpreadCorrectionTable.model_validate(raw)


def test_unknown_keys_are_refused() -> None:
    raw = _raw()
    raw["instruments"]["XAUUSD"]["slope"] = "1"
    with pytest.raises(ValidationError):
        SpreadCorrectionTable.model_validate(raw)


def test_load_from_file(tmp_path) -> None:
    path = tmp_path / "table.json"
    path.write_text(json.dumps(_raw()), encoding="utf-8")
    assert load_correction_table(path).instruments["XAUUSD"].value(5) == 5


def test_stale_after_60_days_of_data_age() -> None:
    table = SpreadCorrectionTable.model_validate(_raw())
    with pytest.warns(UserWarning, match="61 days"):
        warn_if_table_stale(table, now=CUTOFF + timedelta(days=61))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warn_if_table_stale(table, now=CUTOFF + timedelta(days=60))
