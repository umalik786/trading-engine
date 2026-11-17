"""The extractor's timeframes: M1 included, and every timeframe it extracts
is one ReplayFeed can read.

A timeframe extracted but missing from ReplayFeed's TIMEFRAME_DURATIONS
would be stored and then unreadable, and the forming-bar cutoff -- which
takes its bar widths from the same table -- would raise mid-extraction.

Marked requires_mt5 because extract_mt5_data imports MetaTrader5. Needs the
package, not a terminal. Run with:  uv run --extra mt5 pytest -m requires_mt5
"""

from __future__ import annotations

from pathlib import Path

import pytest

mt5 = pytest.importorskip("MetaTrader5")

from engine.feeds.replay import TIMEFRAME_DURATIONS  # noqa: E402

pytestmark = pytest.mark.requires_mt5

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def extractor(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO))
    import extract_mt5_data  # noqa: PLC0415 -- needs REPO on sys.path first

    return extract_mt5_data


def test_m1_is_extracted(extractor):
    assert extractor.TIMEFRAMES.get("M1") == mt5.TIMEFRAME_M1


def test_every_extracted_timeframe_is_readable(extractor):
    missing = set(extractor.TIMEFRAMES) - set(TIMEFRAME_DURATIONS)
    assert not missing, f"extracted but unreadable by ReplayFeed: {sorted(missing)}"
