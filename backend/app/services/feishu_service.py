import json
from typing import Any, Iterable

import httpx

from app.core.config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_DEFAULT_CHAT_ID, FEISHU_WEBHOOK_URL
from app.schemas.meeting import ActionItemResponse, MeetingResponse
from app.schemas.task_result import ActionItemListItem
from app.services.due_status_service import get_due_status, get_due_status_label


class FeishuDeliveryError(Exception):
    pass


def send_meeting_summary(meeting: MeetingResponse) -> str:
    payload = _build_meeting_card_payload(meeting)
    _deliver_card_payload(payload)
    return "会议摘要卡片已发送到飞书。"


def send_follow_up_summary(meeting: MeetingResponse) -> str:
    payload = _build_follow_up_card_payload(meeting)
    _deliver_card_payload(payload)
    return "跟进提醒卡片已发送到飞书。"


def send_action_item_completed_notice(action_item_id: int, title: str, owner_name: str) -> str:
    payload = _build_action_item_completed_payload(action_item_id, title, owner_name)
    _deliver_card_payload(payload)
    return "行动项完成通知已发送到飞书。"


def send_open_tasks_summary(items: Iterable[ActionItemListItem]) -> str:
    payload = _build_open_tasks_payload(items)
    _deliver_card_payload(payload)
    return "未完成任务列表已发送到飞书。"


def extract_card_callback_action(payload: dict[str, Any]) -> tuple[int | None, str | None]:
    value = (
        payload.get("action", {}).get("value")
        or payload.get("event", {}).get("action", {}).get("value")
        or payload.get("value")
        or {}
    )

    action_item_id = value.get("action_item_id") or value.get("id")
    action = value.get("action") or value.get("type")

    try:
        parsed_id = int(action_item_id)
    except (TypeError, ValueError):
        parsed_id = None

    return parsed_id, action


def _deliver_card_payload(payload: dict[str, Any]) -> None:
    if _is_app_bot_configured():
        _post_app_bot_card(payload["card"])
        return

    _ensure_webhook_configured()
    _post_webhook_payload(payload)


def _is_app_bot_configured() -> bool:
    values = [FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_DEFAULT_CHAT_ID]
    return all(value and not value.startswith("replace_with_") for value in values)


def _ensure_webhook_configured() -> None:
    if not FEISHU_WEBHOOK_URL or FEISHU_WEBHOOK_URL.startswith("replace_with_"):
        raise FeishuDeliveryError("FEISHU_WEBHOOK_URL is not configured")


def _post_webhook_payload(payload: dict[str, Any]) -> None:
    try:
        response = httpx.post(FEISHU_WEBHOOK_URL, json=payload, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FeishuDeliveryError(f"Failed to send message to Feishu webhook: {exc}") from exc


def _post_app_bot_card(card: dict[str, Any]) -> None:
    token = _get_tenant_access_token()
    body = {
        "receive_id": FEISHU_DEFAULT_CHAT_ID,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }

    try:
        response = httpx.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FeishuDeliveryError(f"Failed to send app bot card to Feishu: {exc}") from exc

    data = response.json()
    if data.get("code") != 0:
        raise FeishuDeliveryError(f"Feishu message API rejected request: {data}")


def _get_tenant_access_token() -> str:
    try:
        response = httpx.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FeishuDeliveryError(f"Failed to fetch Feishu tenant access token: {exc}") from exc

    data = response.json()
    token = data.get("tenant_access_token")
    if data.get("code") != 0 or not token:
        raise FeishuDeliveryError(f"Feishu token API rejected request: {data}")

    return token


def _build_meeting_card_payload(meeting: MeetingResponse) -> dict[str, Any]:
    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📌 会议纪要 | {meeting.title}"},
                "template": "blue",
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": [
                    _markdown_block(f"**📝 会议摘要**\n{meeting.summary}"),
                    _markdown_block(f"**✅ 会议结论**\n{_format_bullets(meeting.decisions)}"),
                    _markdown_block("**📍 行动项**"),
                    *_build_action_item_elements(meeting.action_items),
                    _markdown_block("**💡 状态更新**\n请在 ActionBridge 后台任务结果页确认完成状态，机器人会持续跟进未完成任务。"),
                ],
            },
        },
    }


def _build_follow_up_card_payload(meeting: MeetingResponse) -> dict[str, Any]:
    unfinished_items = [item for item in meeting.action_items if item.status in {"pending", "in_progress"}]

    if unfinished_items:
        body_elements = [
            _markdown_block("**📍 待跟进行动项**\n请优先关注以下尚未完成的任务。"),
            *_build_action_item_elements(unfinished_items),
            _markdown_block("**💡 状态更新**\n请在 ActionBridge 后台任务结果页更新任务状态。"),
        ]
        template = "orange"
    else:
        body_elements = [_markdown_block("**📍 待跟进行动项**\n当前所有行动项都已完成，无需继续跟进。")]
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


def _build_action_item_completed_payload(action_item_id: int, title: str, owner_name: str) -> dict[str, Any]:
    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": "✅ 行动项已完成"},
                "template": "green",
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": [
                    _markdown_block(f"**任务 ID：{action_item_id}**"),
                    _markdown_block(f"**任务目标：{_normalize_action_title(title, owner_name)}**"),
                    _markdown_block(f"负责人：{owner_name}"),
                    _markdown_block("状态已更新为：已完成"),
                ],
            },
        },
    }


def _build_open_tasks_payload(items: Iterable[ActionItemListItem]) -> dict[str, Any]:
    materialized = [item for item in items if item.status != "completed"]
    visible_items = materialized[:10]
    overdue_count = len([item for item in materialized if item.due_status == "overdue"])
    due_today_count = len([item for item in materialized if item.due_status == "due_today"])
    template = "red" if overdue_count else "orange" if due_today_count else "blue"

    if visible_items:
        elements = [
            _markdown_block(
                "\n".join(
                    [
                        f"**当前未完成任务：{len(materialized)} 项**",
                        f"已逾期：{overdue_count} 项",
                        f"今日到期：{due_today_count} 项",
                        "完成任务可直接发送：`/done 任务ID`",
                    ]
                )
            ),
            _divider(),
            *_build_open_task_elements(visible_items),
        ]
        if len(materialized) > len(visible_items):
            elements.append(_divider())
            elements.append(_markdown_block(f"还有 {len(materialized) - len(visible_items)} 项未展示，请到 ActionBridge 任务结果页查看。"))
    else:
        elements = [_markdown_block("当前没有未完成任务，执行闭环状态良好。")]

    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": "📋 当前未完成任务"},
                "template": template,
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": elements,
            },
        },
    }


def _build_open_task_elements(items: Iterable[ActionItemListItem]) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []

    for item in items:
        title = _normalize_action_title(item.title, item.owner_name)
        risk_prefix = "🚨" if item.due_status == "overdue" else "⏰" if item.due_status == "due_today" else "📌"
        elements.extend(
            [
                _markdown_block(f"**{risk_prefix} #{item.id} {title}**"),
                _markdown_block(f"来源会议：{item.meeting_title}"),
                _markdown_block(f"负责人：{item.owner_name}"),
                _markdown_block(f"截止时间：**{item.deadline or '待确认'}**"),
                _markdown_block(f"状态：{_get_status_label(item.status)} · 风险：{item.due_status_label}"),
                _markdown_block(f"操作：`/done {item.id}`"),
            ]
        )
        elements.append(_divider())

    if elements:
        elements.pop()

    return elements


def _build_action_item_elements(items: Iterable[ActionItemResponse]) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []

    for item in items:
        elements.extend(
            [
                _markdown_block(f"**{_normalize_action_title(item.title, item.owner_name)}**"),
                _markdown_block(f"👤 负责人：{item.owner_name}"),
                _markdown_block(f"⏰ **截止日期：{item.deadline}**"),
                _markdown_block(f"📊 到期风险：{get_due_status_label(get_due_status(item.deadline))}"),
                _markdown_block(f"📌 状态：{_get_status_label(item.status)}"),
            ]
        )
        elements.append(_divider())

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
        "failed": "有风险",
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
