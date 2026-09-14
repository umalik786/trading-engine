from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.core.types import Bar, Fill, Order, TargetPosition

UTC_PLUS_4 = timezone(timedelta(hours=4))


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


def _fill(**overrides: object) -> Fill:
    defaults = {
        "order_id": "o1",
        "client_order_id": "c1",
        "symbol": "EURUSD",
        "quantity": Decimal("1000"),
        "price": Decimal("1.1005"),
        "fees": Decimal("0.50"),
        "ts": datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
    }
    defaults.update(overrides)
    return Fill(**defaults)


class TestBarConstruction:
    def test_valid_bar_constructs(self) -> None:
        bar = _bar()
        assert bar.symbol == "EURUSD"
        assert bar.is_final is True

    def test_bar_is_immutable(self) -> None:
        bar = _bar()
        with pytest.raises(FrozenInstanceError):
            bar.close = Decimal("2.0")


class TestBarTimeValidation:
    def test_naive_ts_open_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _bar(ts_open=datetime(2026, 1, 1, 0, 0))  # noqa: DTZ001 -- naivety is what's under test

    def test_naive_ts_close_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _bar(ts_close=datetime(2026, 1, 1, 0, 15))  # noqa: DTZ001 -- naivety is what's under test

    def test_non_utc_ts_open_rejected(self) -> None:
        with pytest.raises(ValueError, match="UTC"):
            _bar(ts_open=datetime(2026, 1, 1, 4, 0, tzinfo=UTC_PLUS_4))

    def test_ts_close_before_ts_open_rejected(self) -> None:
        with pytest.raises(ValueError, match="after"):
            _bar(
                ts_open=datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
                ts_close=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            )

    def test_ts_close_equal_ts_open_rejected(self) -> None:
        same = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        with pytest.raises(ValueError, match="after"):
            _bar(ts_open=same, ts_close=same)


class TestBarOhlcValidation:
    def test_inverted_high_low_rejected_by_ohlc_checks_collectively(self) -> None:
        # Cannot isolate the `high >= low` guard alone: if high < low, the
        # [low, high] interval is empty, so any open/close value trips one of
        # the other four checks (high>=open, high>=close, low<=open,
        # low<=close) first. Verified by temporarily disabling that guard and
        # confirming this test still passed — see task 2 session notes.
        with pytest.raises(ValueError, match="high"):
            _bar(
                high=Decimal("1.0"), low=Decimal("1.1"), open=Decimal("1.05"), close=Decimal("1.05")
            )

    def test_high_below_open_rejected(self) -> None:
        with pytest.raises(ValueError, match="high"):
            _bar(
                open=Decimal("1.2"), high=Decimal("1.1"), low=Decimal("1.0"), close=Decimal("1.05")
            )

    def test_high_below_close_rejected(self) -> None:
        with pytest.raises(ValueError, match="high"):
            _bar(
                high=Decimal("1.0"), close=Decimal("1.2"), low=Decimal("0.9"), open=Decimal("0.95")
            )

    def test_low_above_open_rejected(self) -> None:
        with pytest.raises(ValueError, match="low"):
            _bar(
                low=Decimal("1.2"), open=Decimal("1.1"), high=Decimal("1.3"), close=Decimal("1.25")
            )

    def test_low_above_close_rejected(self) -> None:
        with pytest.raises(ValueError, match="low"):
            _bar(
                low=Decimal("1.2"), close=Decimal("1.1"), high=Decimal("1.3"), open=Decimal("1.25")
            )


class TestBarDecimalValidation:
    def test_float_volume_rejected(self) -> None:
        with pytest.raises(TypeError, match="Decimal"):
            _bar(volume=100.0)


class TestTargetPosition:
    def test_valid_construction(self) -> None:
        tp = TargetPosition(
            symbol="EURUSD",
            quantity=Decimal("1000"),
            weight=None,
            stop_price=Decimal("1.09"),
            take_profit=Decimal("1.12"),
            reason="breakout",
            confidence=Decimal("0.7"),
        )
        assert tp.reason == "breakout"

    def test_float_quantity_rejected(self) -> None:
        with pytest.raises(TypeError, match="Decimal"):
            TargetPosition(
                symbol="EURUSD",
                quantity=1000.0,
                weight=None,
                stop_price=None,
                take_profit=None,
                reason="x",
                confidence=None,
            )

    def test_immutable(self) -> None:
        tp = TargetPosition(
            symbol="EURUSD",
            quantity=Decimal("1"),
            weight=None,
            stop_price=None,
            take_profit=None,
            reason="x",
            confidence=None,
        )
        with pytest.raises(FrozenInstanceError):
            tp.quantity = Decimal("2")


class TestOrder:
    def test_valid_construction(self) -> None:
        order = Order(
            client_order_id="abc123",
            symbol="EURUSD",
            side="buy",
            quantity=Decimal("1000"),
            order_type="market",
            limit_price=None,
            stop_price=None,
            intent_id="intent-1",
        )
        assert order.side == "buy"

    def test_immutable(self) -> None:
        order = Order(
            client_order_id="abc123",
            symbol="EURUSD",
            side="buy",
            quantity=Decimal("1000"),
            order_type="market",
            limit_price=None,
            stop_price=None,
            intent_id="intent-1",
        )
        with pytest.raises(FrozenInstanceError):
            order.quantity = Decimal("2000")


class TestFill:
    def test_valid_construction(self) -> None:
        fill = _fill()
        assert fill.price == Decimal("1.1005")

    def test_naive_ts_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _fill(ts=datetime(2026, 1, 1, 0, 15))  # noqa: DTZ001 -- naivety is what's under test

    def test_immutable(self) -> None:
        fill = _fill()
        with pytest.raises(FrozenInstanceError):
            fill.price = Decimal("2")
