import json
from datetime import UTC, datetime

from app.schemas.meeting import ActionItemResponse, MeetingResponse
from app.schemas.task_result import ActionItemListItem
from app.services.feishu_service import (
    _build_follow_up_card_payload,
    _build_help_card_payload,
    _build_meeting_card_payload,
    _build_memory_list_payload,
    _build_memory_saved_payload,
    _build_open_tasks_payload,
    _build_project_progress_payload,
    _build_task_owner_update_confirmation_payload,
    _build_task_detail_payload,
    _post_app_bot_card,
    extract_card_callback_action,
)
from app.agent.schemas import ProjectProgressSummary
from app.schemas.memory import MemoryAliasItem


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
    assert payload["card"]["header"]["title"]["content"] == "📢 每周项目同步会"

    elements = payload["card"]["body"]["elements"]
    text_blocks = [element["content"] for element in elements if element["tag"] == "markdown"]
    combined = "\n".join(text_blocks)
    assert len(text_blocks) == 4
    assert "**当前状态**" in combined
    assert "**✅ 已确认决策**" in combined
    assert "1. Beta 版本延期到周五" in combined
    assert "**📋 待办事项**" in combined
    assert "负责人：前端同学，任务：前端更新落地页文案，截止时间：周三" in combined
    assert "当前仍有 1 个行动项待跟进" in combined


def test_build_meeting_card_payload_keeps_status_updates_in_backend() -> None:
    payload = _build_meeting_card_payload(build_meeting())
    elements = payload["card"]["body"]["elements"]
    buttons = [element for element in elements if element["tag"] == "button"]
    text_blocks = [element["content"] for element in elements if element["tag"] == "markdown"]

    assert buttons == []
    assert any("请各负责人及时同步完成状态" in content for content in text_blocks)


def test_build_follow_up_card_payload_only_contains_unfinished_items() -> None:
    payload = _build_follow_up_card_payload(build_meeting())
    elements = payload["card"]["body"]["elements"]
    text_blocks = [element["content"] for element in elements if element["tag"] == "markdown"]
    combined = "\n".join(text_blocks)

    assert payload["msg_type"] == "interactive"
    assert len(text_blocks) == 3
    assert "待跟进行动项：1 项" in combined
    assert "**📋 跟进清单**" in combined
    assert "前端更新落地页文案" in combined
    assert "测试补充回归用例" not in combined
    assert "/done 任务ID" in combined


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
    assert "已逾期：1" in combined
    assert "今日到期：1" in combined
    assert "**📋 任务清单**" in combined
    assert "🚨 #12 前端修复移动端导航栏错位问题" in combined
    assert "/done 任务ID" in combined
    assert "/task 任务ID" in combined
    assert "#14" not in combined


def test_build_open_tasks_payload_can_show_completed_query_results() -> None:
    payload = _build_open_tasks_payload([build_task_item(14, "completed", "completed", "已完成")])

    assert payload["card"]["header"]["title"]["content"] == "📋 任务查询结果"
    contents = [element["content"] for element in payload["card"]["body"]["elements"] if element["tag"] == "markdown"]
    combined = "\n".join(contents)
    assert "查询结果：1 项" in combined
    assert "#14" in combined
    assert "状态：已完成" in combined
    assert "/task 任务ID" in combined
    assert "/done 任务ID" not in combined


def test_build_task_detail_payload_contains_done_command() -> None:
    payload = _build_task_detail_payload(build_task_item(12, "in_progress", "due_today", "浠婃棩鍒版湡"))

    assert payload["msg_type"] == "interactive"
    assert payload["card"]["header"]["title"]["content"] == "📋 任务详情 #12"
    assert payload["card"]["header"]["template"] == "orange"

    contents = [element["content"] for element in payload["card"]["body"]["elements"] if element["tag"] == "markdown"]
    combined = "\n".join(contents)
    assert "任务目标" in combined
    assert "来源会议" in combined
    assert "`/done 12`" in combined
    assert "`/tasks`" in combined


def test_build_task_owner_update_confirmation_payload_uses_clean_chinese_labels() -> None:
    payload = _build_task_owner_update_confirmation_payload(
        action_item_id=2,
        title="\u5b8c\u6210\u5b98\u7f51\u6838\u5fc3\u8def\u5f84\u56de\u5f52\u6d4b\u8bd5",
        old_owner_name="\u524d\u7aef\u540c\u5b66",
        new_owner_name="\u6d4b\u8bd5\u540c\u5b66",
    )

    assert payload["card"]["header"]["title"]["content"] == "\u786e\u8ba4\u4fee\u6539\u8d1f\u8d23\u4eba #2"
    contents = [element["content"] for element in payload["card"]["body"]["elements"] if element["tag"] == "markdown"]
    combined = "\n".join(contents)
    assert "????" not in combined
    assert "**\u4efb\u52a1**" in combined
    assert "**\u539f\u8d1f\u8d23\u4eba**" in combined
    assert "**\u65b0\u8d1f\u8d23\u4eba**" in combined


def test_build_project_progress_payload_contains_summary_metrics() -> None:
    summary = ProjectProgressSummary(
        keyword="官网改版",
        total_count=2,
        completed_count=1,
        in_progress_count=0,
        pending_count=1,
        failed_count=0,
        overdue_count=1,
        due_today_count=0,
        completion_rate=50.0,
        conclusion="当前项目存在风险，建议优先处理有风险和逾期任务。",
        items=[build_task_item(12, "pending", "overdue", "已逾期")],
    )

    payload = _build_project_progress_payload(summary)

    assert payload["msg_type"] == "interactive"
    assert payload["card"]["header"]["title"]["content"] == "📊 官网改版 当前进度"
    assert payload["card"]["header"]["template"] == "red"
    contents = [element["content"] for element in payload["card"]["body"]["elements"] if element["tag"] == "markdown"]
    combined = "\n".join(contents)
    assert "完成率：50.0%" in combined
    assert "总数：2" in combined
    assert "当前项目存在风险" in combined
    assert "**📋 重点任务**" in combined
    assert "#12" in combined


def test_build_help_card_payload_lists_commands_and_examples() -> None:
    payload = _build_help_card_payload()

    assert payload["msg_type"] == "interactive"
    assert payload["card"]["header"]["title"]["content"] == "📘 ActionBridge 使用帮助"
    contents = [element["content"] for element in payload["card"]["body"]["elements"] if element["tag"] == "markdown"]
    combined = "\n".join(contents)
    assert "/meeting" in combined
    assert "/tasks" in combined
    assert "/task 12" in combined
    assert "/done 12" in combined
    assert "/remember 官网 = 官网改版" in combined
    assert "/memory" in combined
    assert "/forget 官网" in combined
    assert "官网改版进度怎么样" in combined


def test_build_memory_payloads_show_alias_mapping() -> None:
    item = MemoryAliasItem(
        id=1,
        alias="官网",
        target="官网改版",
        memory_type="project",
        created_at=datetime.now(UTC),
    )

    saved_payload = _build_memory_saved_payload(item)
    list_payload = _build_memory_list_payload([item])

    saved_contents = [
        element["content"]
        for element in saved_payload["card"]["body"]["elements"]
        if element["tag"] == "markdown"
    ]
    list_contents = [
        element["content"]
        for element in list_payload["card"]["body"]["elements"]
        if element["tag"] == "markdown"
    ]
    assert "官网" in "\n".join(saved_contents)
    assert "官网改版" in "\n".join(saved_contents)
    assert "`官网` = `官网改版`" in "\n".join(list_contents)


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
