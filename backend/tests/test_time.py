from datetime import UTC, datetime

from app.core.time import ensure_utc


def test_ensure_utc_attaches_utc_to_naive_datetime() -> None:
    value = datetime(2026, 5, 30, 2, 30, 0)

    result = ensure_utc(value)

    assert result.tzinfo == UTC
    assert result.hour == 2


def test_ensure_utc_converts_aware_datetime_to_utc() -> None:
    value = datetime(2026, 5, 30, 2, 30, 0, tzinfo=UTC)

    result = ensure_utc(value)

    assert result.tzinfo == UTC
