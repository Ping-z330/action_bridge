from datetime import UTC, datetime

from app.schemas.meeting import ActionItemResponse, MeetingResponse
from app.services.feishu_service import (
    _build_follow_up_card_payload,
    _build_meeting_card_payload,
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


def test_build_meeting_card_payload_uses_interactive_card() -> None:
    payload = _build_meeting_card_payload(build_meeting())

    assert payload["msg_type"] == "interactive"
    assert payload["card"]["schema"] == "2.0"
    assert payload["card"]["header"]["title"]["content"] == "📑 会议纪要 | 每周项目同步会"

    elements = payload["card"]["body"]["elements"]
    assert elements[0]["content"].startswith("**🧾 会议摘要**")
    assert elements[2]["content"] == "**📌 行动项**"
    assert elements[3]["content"] == "**前端更新落地页文案**"
    assert elements[4]["content"] == "👤 负责人：前端同学"
    assert elements[5]["content"] == "⏰ **截止日期：周三**"
    assert elements[6]["content"].startswith("🚦 到期风险：")
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
