from datetime import datetime, timezone


def test_arithmetic_works():
    assert 1 + 1 == 2


def test_datetime_is_timezone_aware():
    now = datetime.now(timezone.utc)
    assert now.tzinfo is not None
