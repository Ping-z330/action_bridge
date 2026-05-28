from typing import Any, Iterable

import httpx

from app.core.config import FEISHU_WEBHOOK_URL
from app.schemas.meeting import ActionItemResponse, MeetingResponse


class FeishuDeliveryError(Exception):
    pass


def send_meeting_summary(meeting: MeetingResponse) -> str:
    _ensure_webhook_configured()
    payload = _build_meeting_card_payload(meeting)
    _post_payload(payload)
    return "会议摘要卡片已发送到飞书。"


def send_follow_up_summary(meeting: MeetingResponse) -> str:
    _ensure_webhook_configured()
    payload = _build_follow_up_card_payload(meeting)
    _post_payload(payload)
    return "跟进提醒卡片已发送到飞书。"


def _ensure_webhook_configured() -> None:
    if not FEISHU_WEBHOOK_URL or FEISHU_WEBHOOK_URL.startswith("replace_with_"):
        raise FeishuDeliveryError("FEISHU_WEBHOOK_URL is not configured")


def _post_payload(payload: dict[str, Any]) -> None:
    try:
        response = httpx.post(FEISHU_WEBHOOK_URL, json=payload, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FeishuDeliveryError(f"Failed to send message to Feishu: {exc}") from exc


def _build_meeting_card_payload(meeting: MeetingResponse) -> dict[str, Any]:
    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📝 会议纪要 | {meeting.title}"},
                "template": "blue",
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": [
                    _markdown_block(f"**🧾 会议摘要**\n{meeting.summary}"),
                    _markdown_block(f"**✅ 会议结论**\n{_format_bullets(meeting.decisions)}"),
                    _markdown_block("**📌 行动项**"),
                    *_build_action_item_elements(meeting.action_items),
                ],
            },
        },
    }


def _build_follow_up_card_payload(meeting: MeetingResponse) -> dict[str, Any]:
    unfinished_items = [item for item in meeting.action_items if item.status in {"pending", "in_progress"}]

    if unfinished_items:
        body_elements = [
            _markdown_block("**📌 待跟进行动项**\n请优先关注以下尚未完成的任务。"),
            *_build_action_item_elements(unfinished_items),
        ]
        template = "orange"
    else:
        body_elements = [
            _markdown_block("**📌 待跟进行动项**\n当前所有行动项都已完成，无需继续跟进。"),
        ]
        template = "green"

    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📣 跟进提醒 | {meeting.title}"},
                "template": template,
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": body_elements,
            },
        },
    }


def _build_action_item_elements(items: Iterable[ActionItemResponse]) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []

    for item in items:
        elements.extend(
            [
                _markdown_block(f"**{_normalize_action_title(item.title, item.owner_name)}**"),
                _markdown_block(f"👤 负责人：{item.owner_name}"),
                _markdown_block(f"⏰ **截止日期：{item.deadline}**"),
                _markdown_block(f"📌 状态：{_get_status_label(item.status)}"),
                _divider(),
            ]
        )

    if elements:
        elements.pop()

    return elements


def _markdown_block(content: str) -> dict[str, Any]:
    return {
        "tag": "markdown",
        "content": content,
        "text_align": "left",
        "text_size": "normal_v2",
        "margin": "0px 0px 8px 0px",
    }


def _divider() -> dict[str, Any]:
    return {
        "tag": "hr",
        "margin": "8px 0px 8px 0px",
    }


def _format_bullets(items: Iterable[str]) -> str:
    materialized = [item.strip() for item in items if item.strip()]
    if not materialized:
        return "- 暂无明确结论"
    return "\n".join(f"- {item}" for item in materialized)


def _get_status_label(status: str) -> str:
    return {
        "pending": "待处理",
        "in_progress": "进行中",
        "completed": "已完成",
        "failed": "失败",
    }.get(status, status)


def _normalize_action_title(title: str, owner_name: str) -> str:
    normalized = title.strip()
    prefixes = ("Action:", "Next step:", "Todo:", "Follow up:", "Follow-up:")
    for prefix in prefixes:
        if normalized.lower().startswith(prefix.lower()):
            normalized = normalized[len(prefix) :].strip()
            break

    if owner_name and normalized.startswith(owner_name):
        normalized = normalized[len(owner_name) :].strip()

    return normalized or title.strip()
