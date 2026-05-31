from datetime import UTC, datetime

from app.agent.service import detect_intent, handle_agent_message
from app.schemas.task_result import ActionItemListItem


def _task(
    item_id: int,
    title: str,
    owner: str,
    meeting_title: str,
    status: str,
    due_status: str,
) -> ActionItemListItem:
    return ActionItemListItem(
        id=item_id,
        meeting_id=1,
        meeting_title=meeting_title,
        title=title,
        owner_name=owner,
        deadline="2026-05-31 18:00",
        deadline_date="2026-05-31",
        deadline_time="18:00",
        status=status,
        due_status=due_status,
        due_status_label=due_status,
        created_at=datetime.now(UTC),
    )


def test_detect_intent_for_due_today_tasks() -> None:
    intent = detect_intent("帮我看看今天到期的任务")

    assert intent is not None
    assert intent.name == "query_tasks"
    assert intent.filters["due_status"] == "due_today"
    assert intent.filters["open_only"] == "true"


def test_detect_intent_for_completed_task_update() -> None:
    intent = detect_intent("把 12 号任务标记完成")

    assert intent is not None
    assert intent.name == "update_task_status"
    assert intent.filters["action_item_id"] == "12"
    assert intent.filters["status"] == "completed"


def test_detect_intent_for_in_progress_task_update() -> None:
    intent = detect_intent("把 8 号任务改成进行中")

    assert intent is not None
    assert intent.name == "update_task_status"
    assert intent.filters["action_item_id"] == "8"
    assert intent.filters["status"] == "in_progress"


def test_detect_intent_for_failed_task_update() -> None:
    intent = detect_intent("9 号任务有风险")

    assert intent is not None
    assert intent.name == "update_task_status"
    assert intent.filters["action_item_id"] == "9"
    assert intent.filters["status"] == "failed"


def test_detect_intent_for_pending_task_update() -> None:
    intent = detect_intent("把 6 号任务改回待处理")

    assert intent is not None
    assert intent.name == "update_task_status"
    assert intent.filters["action_item_id"] == "6"
    assert intent.filters["status"] == "pending"


def test_detect_intent_for_project_progress_summary() -> None:
    intent = detect_intent("官网改版进度怎么样")

    assert intent is not None
    assert intent.name == "summarize_project"
    assert intent.filters["keyword"] == "官网改版"


def test_handle_agent_message_filters_by_owner() -> None:
    items = [
        _task(1, "修复移动端问题", "前端同学", "官网改版", "pending", "upcoming"),
        _task(2, "补充测试用例", "测试同学", "官网改版", "pending", "upcoming"),
    ]

    response = handle_agent_message("前端同学负责的任务", items)

    assert response.handled is True
    assert [item.id for item in response.items] == [1]


def test_handle_agent_message_filters_by_project_keyword() -> None:
    items = [
        _task(1, "修复移动端问题", "前端同学", "官网改版上线会", "pending", "upcoming"),
        _task(2, "整理复盘文档", "运营同学", "活动复盘会", "pending", "upcoming"),
    ]

    response = handle_agent_message("官网改版相关任务", items)

    assert response.handled is True
    assert [item.id for item in response.items] == [1]


def test_handle_agent_message_summarizes_project_progress() -> None:
    items = [
        _task(1, "修复移动端问题", "前端同学", "官网改版上线会", "completed", "completed"),
        _task(2, "补充测试用例", "测试同学", "官网改版上线会", "pending", "overdue"),
        _task(3, "整理复盘文档", "运营同学", "活动复盘会", "pending", "upcoming"),
    ]

    response = handle_agent_message("官网改版进度怎么样", items)

    assert response.handled is True
    assert response.intent is not None
    assert response.intent.name == "summarize_project"
    assert response.progress_summary is not None
    assert response.progress_summary.total_count == 2
    assert response.progress_summary.completed_count == 1
    assert response.progress_summary.overdue_count == 1
    assert response.progress_summary.completion_rate == 50.0


def test_handle_agent_message_ignores_unrelated_chat() -> None:
    response = handle_agent_message("大家下午好", [])

    assert response.handled is False
