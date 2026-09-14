from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from engine.core.decisions import DecisionRecord, RiskDecision
from engine.core.types import Bar, Order, TargetPosition


def _bar(**overrides: object) -> Bar:
    defaults = {
        "symbol": "EURUSD",
        "ts_open": datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        "ts_close": datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
        "open": Decimal("1.1000"),
        "high": Decimal("1.1010"),
        "low": Decimal("1.0990"),
        "close": Decimal("1.1005"),
        "volume": Decimal("100"),
        "is_final": True,
    }
    defaults.update(overrides)
    return Bar(**defaults)


def _target_position(**overrides: object) -> TargetPosition:
    defaults = {
        "symbol": "EURUSD",
        "quantity": Decimal("1000"),
        "weight": None,
        "stop_price": Decimal("1.0950"),
        "take_profit": Decimal("1.1100"),
        "reason": "breakout above prior session high",
        "confidence": Decimal("0.65"),
    }
    defaults.update(overrides)
    return TargetPosition(**defaults)


def _order(**overrides: object) -> Order:
    defaults = {
        "client_order_id": "deadbeef",
        "symbol": "EURUSD",
        "side": "buy",
        "quantity": Decimal("1000"),
        "order_type": "market",
        "limit_price": None,
        "stop_price": Decimal("1.0950"),
        "intent_id": "intent-1",
    }
    defaults.update(overrides)
    return Order(**defaults)


def _decision_record(**overrides: object) -> DecisionRecord:
    defaults = {
        "ts": datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
        "symbol": "EURUSD",
        "bar": _bar(),
        "features": {"sma_20": Decimal("1.0998"), "atr_14": Decimal("0.0012")},
        "strategy_output": _target_position(),
        "strategy_reason": "breakout above prior session high",
        "sized_quantity": Decimal("1000"),
        "risk_decision": RiskDecision.APPROVE,
        "risk_reason": "within per-trade risk cap",
        "order": _order(),
        "expected_fill": Decimal("1.1006"),
        "realised_fill": None,
        "account_snapshot": {"equity": Decimal("100000.00"), "open_positions": 1},
    }
    defaults.update(overrides)
    return DecisionRecord(**defaults)


class TestConstruction:
    def test_valid_record_constructs(self) -> None:
        record = _decision_record()
        assert record.symbol == "EURUSD"
        assert record.risk_decision is RiskDecision.APPROVE

    def test_immutable(self) -> None:
        record = _decision_record()
        with pytest.raises(FrozenInstanceError):
            record.risk_reason = "changed"

    def test_naive_ts_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _decision_record(ts=datetime(2026, 1, 1, 0, 15))  # noqa: DTZ001 -- naivety is what's under test

    def test_float_sized_quantity_rejected(self) -> None:
        with pytest.raises(TypeError, match="Decimal"):
            _decision_record(sized_quantity=1000.0)


class TestRejectionsLoggedFully:
    """§2.9: a REJECT record must carry the same context an APPROVE does."""

    def test_reject_record_carries_full_context(self) -> None:
        record = _decision_record(
            risk_decision=RiskDecision.REJECT,
            risk_reason="daily loss internal limit reached",
        )
        assert record.risk_decision is RiskDecision.REJECT
        assert record.features
        assert record.strategy_output is not None
        assert record.strategy_reason
        assert record.account_snapshot

    def test_empty_features_rejected_regardless_of_risk_decision(self) -> None:
        # The guard is unconditional -- REJECT gets no special pass to omit
        # context that APPROVE would also be required to carry.
        with pytest.raises(ValueError, match="features"):
            _decision_record(risk_decision=RiskDecision.REJECT, features={})
        with pytest.raises(ValueError, match="features"):
            _decision_record(risk_decision=RiskDecision.APPROVE, features={})

    def test_empty_account_snapshot_rejected(self) -> None:
        with pytest.raises(ValueError, match="account_snapshot"):
            _decision_record(risk_decision=RiskDecision.REJECT, account_snapshot={})

    def test_empty_risk_reason_rejected(self) -> None:
        with pytest.raises(ValueError, match="risk_reason"):
            _decision_record(risk_decision=RiskDecision.APPROVE, risk_reason="")


class TestRealisedFillBackfill:
    def test_replace_backfills_realised_fill_leaving_rest_unchanged(self) -> None:
        original = _decision_record(realised_fill=None)
        backfilled = replace(original, realised_fill=Decimal("1.10065"))

        assert original.realised_fill is None
        assert backfilled.realised_fill == Decimal("1.10065")
        assert backfilled is not original
        assert backfilled.ts == original.ts
        assert backfilled.symbol == original.symbol
        assert backfilled.bar == original.bar
        assert backfilled.features == original.features
        assert backfilled.strategy_output == original.strategy_output
        assert backfilled.strategy_reason == original.strategy_reason
        assert backfilled.sized_quantity == original.sized_quantity
        assert backfilled.risk_decision == original.risk_decision
        assert backfilled.risk_reason == original.risk_reason
        assert backfilled.order == original.order
        assert backfilled.expected_fill == original.expected_fill
        assert backfilled.account_snapshot == original.account_snapshot
