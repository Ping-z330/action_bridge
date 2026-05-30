from datetime import UTC, date, datetime

from app.services.due_status_service import get_due_status, get_due_status_label


def test_due_status_handles_relative_days() -> None:
    today = date(2026, 5, 30)

    assert get_due_status("今天下午", today=today) == "due_today"
    assert get_due_status("明天上午", today=today) == "upcoming"
    assert get_due_status("昨天", today=today) == "overdue"


def test_due_status_handles_weekday_from_created_week() -> None:
    created_at = datetime(2026, 5, 26, tzinfo=UTC)
    today = date(2026, 5, 30)

    assert get_due_status("周三下班前", created_at=created_at, today=today) == "overdue"
    assert get_due_status("下周一", created_at=created_at, today=today) == "upcoming"


def test_due_status_handles_unknown_and_labels() -> None:
    assert get_due_status("Pending confirmation") == "unknown"
    assert get_due_status_label("overdue") == "已逾期"
