import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from engine.core.decisions import DecisionRecord, RiskDecision
from engine.core.types import Bar, Order, TargetPosition
from engine.observability.decision_log import DEFAULT_LOG_PATH, DecisionLogWriter


def _decision_record(**overrides: object) -> DecisionRecord:
    defaults = {
        "ts": datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
        "symbol": "EURUSD",
        "bar": Bar(
            symbol="EURUSD",
            ts_open=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            ts_close=datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
            open=Decimal("1.1000"),
            high=Decimal("1.1010"),
            low=Decimal("1.0990"),
            close=Decimal("1.1005"),
            volume=Decimal("100"),
            is_final=True,
        ),
        "features": {"sma_20": Decimal("1.09987654321"), "atr_14": Decimal("0.0012")},
        "strategy_output": TargetPosition(
            symbol="EURUSD",
            quantity=Decimal("1000"),
            weight=None,
            stop_price=Decimal("1.0950"),
            take_profit=Decimal("1.1100"),
            reason="breakout above prior session high",
            confidence=Decimal("0.654321"),
        ),
        "strategy_reason": "breakout above prior session high",
        "sized_quantity": Decimal("1000"),
        "risk_decision": RiskDecision.APPROVE,
        "risk_reason": "within per-trade risk cap",
        "order": Order(
            client_order_id="deadbeef",
            symbol="EURUSD",
            side="buy",
            quantity=Decimal("1000"),
            order_type="market",
            limit_price=None,
            stop_price=Decimal("1.0950"),
            intent_id="intent-1",
        ),
        # deliberately precision-sensitive -- would lose digits through float
        "expected_fill": Decimal("1.100649999999"),
        "realised_fill": None,
        "account_snapshot": {"equity": Decimal("100000.005"), "open_positions": 1},
    }
    defaults.update(overrides)
    return DecisionRecord(**defaults)


def _decision_record_from_json(raw: dict) -> DecisionRecord:
    return DecisionRecord(
        ts=datetime.fromisoformat(raw["ts"]),
        symbol=raw["symbol"],
        bar=Bar(
            symbol=raw["bar"]["symbol"],
            ts_open=datetime.fromisoformat(raw["bar"]["ts_open"]),
            ts_close=datetime.fromisoformat(raw["bar"]["ts_close"]),
            open=Decimal(raw["bar"]["open"]),
            high=Decimal(raw["bar"]["high"]),
            low=Decimal(raw["bar"]["low"]),
            close=Decimal(raw["bar"]["close"]),
            volume=Decimal(raw["bar"]["volume"]),
            is_final=raw["bar"]["is_final"],
        ),
        features={k: Decimal(v) for k, v in raw["features"].items()},
        strategy_output=TargetPosition(
            symbol=raw["strategy_output"]["symbol"],
            quantity=Decimal(raw["strategy_output"]["quantity"]),
            weight=raw["strategy_output"]["weight"],
            stop_price=Decimal(raw["strategy_output"]["stop_price"]),
            take_profit=Decimal(raw["strategy_output"]["take_profit"]),
            reason=raw["strategy_output"]["reason"],
            confidence=Decimal(raw["strategy_output"]["confidence"]),
        ),
        strategy_reason=raw["strategy_reason"],
        sized_quantity=Decimal(raw["sized_quantity"]),
        risk_decision=RiskDecision(raw["risk_decision"]),
        risk_reason=raw["risk_reason"],
        order=Order(
            client_order_id=raw["order"]["client_order_id"],
            symbol=raw["order"]["symbol"],
            side=raw["order"]["side"],
            quantity=Decimal(raw["order"]["quantity"]),
            order_type=raw["order"]["order_type"],
            limit_price=raw["order"]["limit_price"],
            stop_price=Decimal(raw["order"]["stop_price"]),
            intent_id=raw["order"]["intent_id"],
        ),
        expected_fill=Decimal(raw["expected_fill"]),
        realised_fill=raw["realised_fill"],
        account_snapshot={
            k: (Decimal(v) if isinstance(v, str) else v) for k, v in raw["account_snapshot"].items()
        },
    )


class TestDefaultPath:
    def test_default_log_path_is_outside_repo_runtime_logs(self) -> None:
        # Equality check only -- never instantiate a writer with the default
        # path in a test, or it would write into the real runtime directory.
        assert Path("C:/trading/runtime/logs/decisions.jsonl") == DEFAULT_LOG_PATH


class TestWriteAndRoundTrip:
    def test_writes_one_json_object_per_line(self, tmp_path: Path) -> None:
        log_path = tmp_path / "decisions.jsonl"
        record_a = _decision_record()
        record_b = _decision_record(ts=datetime(2026, 1, 1, 0, 30, tzinfo=UTC))

        with DecisionLogWriter(log_path) as writer:
            writer.write(record_a)
            writer.write(record_b)

        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        for line in lines:
            json.loads(line)  # each line is valid, self-contained JSON

    def test_decimal_serialises_as_string_not_float(self, tmp_path: Path) -> None:
        log_path = tmp_path / "decisions.jsonl"
        with DecisionLogWriter(log_path) as writer:
            writer.write(_decision_record())

        raw = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert raw["expected_fill"] == "1.100649999999"
        assert isinstance(raw["expected_fill"], str)
        assert raw["sized_quantity"] == "1000"
        assert raw["bar"]["open"] == "1.1000"
        assert raw["account_snapshot"]["equity"] == "100000.005"

    def test_datetime_serialises_as_iso8601_with_offset(self, tmp_path: Path) -> None:
        log_path = tmp_path / "decisions.jsonl"
        record = _decision_record()
        with DecisionLogWriter(log_path) as writer:
            writer.write(record)

        raw = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert raw["ts"] == record.ts.isoformat()
        assert raw["ts"].endswith("+00:00")
        assert raw["bar"]["ts_open"] == record.bar.ts_open.isoformat()

    def test_risk_decision_serialises_as_its_value(self, tmp_path: Path) -> None:
        log_path = tmp_path / "decisions.jsonl"
        record = _decision_record(risk_decision=RiskDecision.REJECT, risk_reason="rejected")
        with DecisionLogWriter(log_path) as writer:
            writer.write(record)

        raw = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert raw["risk_decision"] == "REJECT"

    def test_full_round_trip_preserves_decimal_precision(self, tmp_path: Path) -> None:
        log_path = tmp_path / "decisions.jsonl"
        original = _decision_record()
        with DecisionLogWriter(log_path) as writer:
            writer.write(original)

        raw = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        rebuilt = _decision_record_from_json(raw)

        assert rebuilt == original
        assert rebuilt.expected_fill == original.expected_fill
        assert str(rebuilt.expected_fill) == "1.100649999999"
