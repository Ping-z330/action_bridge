import json
from datetime import UTC, datetime

from app.schemas.meeting import ActionItemResponse, MeetingResponse
from app.schemas.task_result import ActionItemListItem
from app.services.feishu_service import (
    _build_follow_up_card_payload,
    _build_meeting_card_payload,
    _build_open_tasks_payload,
    _post_app_bot_card,
    extract_card_callback_action,
)


def build_meeting() -> MeetingResponse:
    return MeetingResponse(
        id=1,
        title="每周项目同步会",
        raw_transcript="raw",
        summary="确认了上线延期与分工安排。",
        decisions=["Beta 版本延期到周五", "周三前完成文案确认"],
        created_at=datetime.now(UTC),
        action_items=[
            ActionItemResponse(
                id=1,
                title="Action: 前端更新落地页文案",
                owner_name="前端同学",
                deadline="周三",
                status="in_progress",
            ),
            ActionItemResponse(
                id=2,
                title="测试补充回归用例",
                owner_name="测试同学",
                deadline="周四",
                status="completed",
            ),
        ],
    )


def build_task_item(
    item_id: int,
    status: str,
    due_status: str,
    due_status_label: str,
) -> ActionItemListItem:
    return ActionItemListItem(
        id=item_id,
        meeting_id=1,
        meeting_title="官网改版上线协调会",
        title="Action: 前端修复移动端导航栏错位问题",
        owner_name="前端同学",
        deadline="2026-06-01 18:00",
        deadline_date="2026-06-01",
        deadline_time="18:00",
        status=status,
        due_status=due_status,
        due_status_label=due_status_label,
        created_at=datetime.now(UTC),
    )


def test_build_meeting_card_payload_uses_interactive_card() -> None:
    payload = _build_meeting_card_payload(build_meeting())

    assert payload["msg_type"] == "interactive"
    assert payload["card"]["schema"] == "2.0"
    assert payload["card"]["header"]["title"]["content"] == "📌 会议纪要 | 每周项目同步会"

    elements = payload["card"]["body"]["elements"]
    assert elements[0]["content"].startswith("**📝 会议摘要**")
    assert elements[2]["content"] == "**📍 行动项**"
    assert elements[3]["content"] == "**前端更新落地页文案**"
    assert elements[4]["content"] == "👤 负责人：前端同学"
    assert elements[5]["content"] == "⏰ **截止日期：周三**"
    assert elements[6]["content"].startswith("📊 到期风险：")
    assert elements[7]["content"] == "📌 状态：进行中"


def test_build_meeting_card_payload_keeps_status_updates_in_backend() -> None:
    payload = _build_meeting_card_payload(build_meeting())
    elements = payload["card"]["body"]["elements"]
    buttons = [element for element in elements if element["tag"] == "button"]
    text_blocks = [element["content"] for element in elements if element["tag"] == "markdown"]

    assert buttons == []
    assert any("ActionBridge 后台任务结果页" in content for content in text_blocks)


def test_build_follow_up_card_payload_only_contains_unfinished_items() -> None:
    payload = _build_follow_up_card_payload(build_meeting())
    elements = payload["card"]["body"]["elements"]
    text_blocks = [element["content"] for element in elements if element["tag"] == "markdown"]
    combined = "\n".join(text_blocks)

    assert payload["msg_type"] == "interactive"
    assert "前端更新落地页文案" in combined
    assert "测试补充回归用例" not in combined


def test_build_open_tasks_payload_highlights_risk_and_done_command() -> None:
    payload = _build_open_tasks_payload(
        [
            build_task_item(12, "pending", "overdue", "已逾期"),
            build_task_item(13, "in_progress", "due_today", "今日到期"),
            build_task_item(14, "completed", "completed", "已完成"),
        ]
    )

    assert payload["msg_type"] == "interactive"
    assert payload["card"]["header"]["template"] == "red"

    contents = [element["content"] for element in payload["card"]["body"]["elements"] if element["tag"] == "markdown"]
    combined = "\n".join(contents)
    assert "当前未完成任务：2 项" in combined
    assert "已逾期：1 项" in combined
    assert "今日到期：1 项" in combined
    assert "🚨 #12 前端修复移动端导航栏错位问题" in combined
    assert "操作：`/done 12`" in combined
    assert "#14" not in combined


def test_post_app_bot_card_sends_interactive_message(monkeypatch) -> None:
    import app.services.feishu_service as feishu_service

    calls: list[dict] = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        if "tenant_access_token" in url:
            return FakeResponse({"code": 0, "tenant_access_token": "tenant-token"})
        return FakeResponse({"code": 0})

    monkeypatch.setattr(feishu_service, "FEISHU_APP_ID", "cli_test")
    monkeypatch.setattr(feishu_service, "FEISHU_APP_SECRET", "secret")
    monkeypatch.setattr(feishu_service, "FEISHU_DEFAULT_CHAT_ID", "oc_test")
    monkeypatch.setattr(feishu_service.httpx, "post", fake_post)

    _post_app_bot_card({"schema": "2.0", "body": {"elements": []}})

    assert calls[0]["json"] == {"app_id": "cli_test", "app_secret": "secret"}
    assert calls[1]["params"] == {"receive_id_type": "chat_id"}
    assert calls[1]["headers"] == {"Authorization": "Bearer tenant-token"}
    assert calls[1]["json"]["receive_id"] == "oc_test"
    assert calls[1]["json"]["msg_type"] == "interactive"
    assert json.loads(calls[1]["json"]["content"])["schema"] == "2.0"


def test_extract_card_callback_action_accepts_nested_payload() -> None:
    action_item_id, action = extract_card_callback_action(
        {
            "action": {
                "value": {
                    "action": "complete_action_item",
                    "action_item_id": 12,
                }
            }
        }
    )

    assert action_item_id == 12
    assert action == "complete_action_item"
