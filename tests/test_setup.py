from datetime import UTC, datetime


def test_arithmetic_works():
    assert 1 + 1 == 2


def test_datetime_is_timezone_aware():
    now = datetime.now(UTC)
    assert now.tzinfo is not None
