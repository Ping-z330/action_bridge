"""Feishu message delivery and interactive-card builders.

这个文件主要做两件事：
1. 对外提供 `send_xxx` 函数，让业务代码发送不同类型的飞书卡片。
2. 在内部把业务数据组装成飞书 interactive card payload，并选择应用机器人或 webhook 投递。

阅读顺序建议：先看顶部的 `send_xxx` 入口函数，再看 `_deliver_card_payload`，
最后按需要查看对应的 `_build_xxx_payload` 卡片构造函数。
"""

import json
from typing import Any, Iterable

import httpx

from app.agent.schemas import ProjectProgressSummary
from app.core.config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_DEFAULT_CHAT_ID, FEISHU_WEBHOOK_URL
from app.schemas.meeting import ActionItemResponse, MeetingResponse
from app.schemas.memory import MemoryAliasItem
from app.schemas.task_result import ActionItemListItem
from app.services.due_status_service import get_due_status, get_due_status_label


class FeishuDeliveryError(Exception):
    """飞书消息投递失败时抛出的统一异常。"""

    pass


# Public send functions -----------------------------------------------------
# 这些函数是本文件对外暴露的主要入口。
# 调用方通常不需要知道飞书卡片 JSON 怎么拼，只需要传入业务对象。

def send_meeting_summary(meeting: MeetingResponse, receive_id: str | None = None) -> str:
    """发送会议摘要卡片。"""

    payload = _build_meeting_card_payload(meeting)
    _deliver_card_payload(payload, receive_id=receive_id)
    return "会议摘要卡片已发送到飞书。"


def send_follow_up_summary(meeting: MeetingResponse, receive_id: str | None = None) -> str:
    """发送某个会议的待跟进任务提醒卡片。"""

    payload = _build_follow_up_card_payload(meeting)
    _deliver_card_payload(payload, receive_id=receive_id)
    return "跟进提醒卡片已发送到飞书。"


# 发送任务相关的消息函数，这些函数会构建对应的卡片内容并发送到飞书，比如任务完成通知、任务详情、任务创建确认等
def send_action_item_completed_notice(
    action_item_id: int,
    title: str,
    owner_name: str,
    receive_id: str | None = None,
) -> str:
    """发送任务已完成通知。"""

    payload = _build_action_item_completed_payload(action_item_id, title, owner_name)
    _deliver_card_payload(payload, receive_id=receive_id)
    return "行动项完成通知已发送到飞书。"


def send_open_tasks_summary(items: Iterable[ActionItemListItem], receive_id: str | None = None) -> str:
    """发送未完成任务列表，常用于 `/tasks` 查询结果。"""

    payload = _build_open_tasks_payload(items)
    _deliver_card_payload(payload, receive_id=receive_id)
    return "未完成任务列表已发送到飞书。"


def send_task_detail_summary(item: ActionItemListItem, receive_id: str | None = None) -> str:
    """发送单个任务详情，常用于 `/task 任务ID` 查询结果。"""

    payload = _build_task_detail_payload(item)
    _deliver_card_payload(payload, receive_id=receive_id)
    return "任务详情卡片已发送到飞书。"


def send_task_not_found_notice(action_item_id: int, receive_id: str | None = None) -> str:
    """任务 ID 找不到时发送提示卡片。"""

    payload = _build_task_not_found_payload(action_item_id)
    _deliver_card_payload(payload, receive_id=receive_id)
    return "任务不存在提示卡片已发送到飞书。"


def send_task_create_clarification(message: str, receive_id: str | None = None) -> str:
    """创建任务信息不完整时，请用户补充说明。"""

    payload = _build_task_create_clarification_payload(message)
    _deliver_card_payload(payload, receive_id=receive_id)
    return "任务创建补充信息提示已发送到飞书。"


def send_task_create_confirmation(
    title: str,
    owner_name: str,
    deadline: str,
    receive_id: str | None = None,
) -> str:
    """自然语言创建任务前，发送确认卡片。"""

    payload = _build_task_create_confirmation_payload(title, owner_name, deadline)
    _deliver_card_payload(payload, receive_id=receive_id)
    return "任务创建确认卡片已发送到飞书。"


def send_task_deadline_update_confirmation(
    action_item_id: int,
    title: str,
    old_deadline: str,
    new_deadline: str,
    receive_id: str | None = None,
    reference_note: str = "",
) -> str:
    """修改任务截止时间前，发送确认卡片。"""

    payload = _build_task_deadline_update_confirmation_payload(
        action_item_id,
        title,
        old_deadline,
        new_deadline,
        reference_note,
    )
    _deliver_card_payload(payload, receive_id=receive_id)
    return "任务截止时间修改确认卡片已发送到飞书。"


def send_task_owner_update_confirmation(
    action_item_id: int,
    title: str,
    old_owner_name: str,
    new_owner_name: str,
    receive_id: str | None = None,
    reference_note: str = "",
) -> str:
    """修改任务负责人前，发送确认卡片。"""

    payload = _build_task_owner_update_confirmation_payload(
        action_item_id,
        title,
        old_owner_name,
        new_owner_name,
        reference_note,
    )
    _deliver_card_payload(payload, receive_id=receive_id)
    return "任务负责人修改确认卡片已发送到飞书。"


def send_pending_action_notice(title: str, message: str, receive_id: str | None = None) -> str:
    """发送通用的“等待确认/无法直接执行”提示。"""

    payload = _build_pending_action_notice_payload(title, message)
    _deliver_card_payload(payload, receive_id=receive_id)
    return "待确认操作提示已发送到飞书。"


def send_project_progress_summary(summary: ProjectProgressSummary, receive_id: str | None = None) -> str:
    """发送项目进度总结卡片。"""

    payload = _build_project_progress_payload(summary)
    _deliver_card_payload(payload, receive_id=receive_id)
    return "项目进度总结卡片已发送到飞书。"


def send_help_card(receive_id: str | None = None) -> str:
    """发送帮助卡片，展示飞书机器人支持的命令。"""

    payload = _build_help_card_payload()
    _deliver_card_payload(payload, receive_id=receive_id)
    return "帮助卡片已发送到飞书。"


def send_memory_saved_notice(item: MemoryAliasItem, receive_id: str | None = None) -> str:
    """Memory 别名保存成功后发送通知。"""

    payload = _build_memory_saved_payload(item)
    _deliver_card_payload(payload, receive_id=receive_id)
    return "Memory saved notice sent to Feishu."


def send_memory_deleted_notice(item: MemoryAliasItem, receive_id: str | None = None) -> str:
    """Memory 别名删除成功后发送通知。"""

    payload = _build_memory_deleted_payload(item)
    _deliver_card_payload(payload, receive_id=receive_id)
    return "Memory deleted notice sent to Feishu."


def send_memory_list_summary(items: Iterable[MemoryAliasItem], receive_id: str | None = None) -> str:
    """发送当前 Memory 别名列表。"""

    payload = _build_memory_list_payload(items)
    _deliver_card_payload(payload, receive_id=receive_id)
    return "Memory list sent to Feishu."


def extract_card_callback_action(payload: dict[str, Any]) -> tuple[int | None, str | None]:
    """从飞书卡片回调 payload 中解析任务 ID 和动作类型。"""

    # 飞书不同类型的回调结构不完全一样，这里按常见位置依次尝试取 value。
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


# Delivery helpers ----------------------------------------------------------
# 投递逻辑集中在这里：
# - 如果配置了飞书自建应用机器人，就用 app bot API 发送 interactive card。
# - 否则退回到 webhook 机器人发送。

def _deliver_card_payload(payload: dict[str, Any], receive_id: str | None = None) -> None:
    """选择可用的飞书投递方式，并发送卡片。"""

    if _is_app_bot_configured(receive_id):
        _post_app_bot_card(payload["card"], receive_id=receive_id)
        return

    _ensure_webhook_configured()
    _post_webhook_payload(payload)


def _is_app_bot_configured(receive_id: str | None = None) -> bool:
    """检查自建应用机器人所需的 app id、secret、目标会话是否都已配置。"""

    target_receive_id = receive_id or FEISHU_DEFAULT_CHAT_ID
    values = [FEISHU_APP_ID, FEISHU_APP_SECRET, target_receive_id]
    return all(value and not value.startswith("replace_with_") for value in values)


def _ensure_webhook_configured() -> None:
    """当走 webhook 发送时，提前检查 webhook URL 是否可用。"""

    if not FEISHU_WEBHOOK_URL or FEISHU_WEBHOOK_URL.startswith("replace_with_"):
        raise FeishuDeliveryError("FEISHU_WEBHOOK_URL is not configured")


def _post_webhook_payload(payload: dict[str, Any]) -> None:
    """通过飞书 webhook 机器人发送完整 payload。"""

    try:
        response = httpx.post(FEISHU_WEBHOOK_URL, json=payload, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FeishuDeliveryError(f"Failed to send message to Feishu webhook: {exc}") from exc


def _post_app_bot_card(card: dict[str, Any], receive_id: str | None = None) -> None:
    """通过飞书自建应用机器人发送 interactive card。"""

    token = _get_tenant_access_token()
    target_receive_id = receive_id or FEISHU_DEFAULT_CHAT_ID
    if not target_receive_id:
        raise FeishuDeliveryError("Feishu receive_id is not configured")

    body = {
        "receive_id": target_receive_id,
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


def send_text_reply(text: str, open_id: str) -> str:
    """Send a plain text message to a specific user via Feishu Bot API."""
    if not FEISHU_APP_ID or FEISHU_APP_ID.startswith("replace_with_"):
        raise FeishuDeliveryError("FEISHU_APP_ID is not configured")
    if not FEISHU_APP_SECRET or FEISHU_APP_SECRET.startswith("replace_with_"):
        raise FeishuDeliveryError("FEISHU_APP_SECRET is not configured")

    token = _get_tenant_access_token()
    body = {
        "receive_id": open_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }
    try:
        response = httpx.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            params={"receive_id_type": "open_id"},
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FeishuDeliveryError(f"Failed to send text reply: {exc}") from exc

    data = response.json()
    if data.get("code") != 0:
        raise FeishuDeliveryError(f"Feishu text reply rejected: {data}")
    return "sent"


def _get_tenant_access_token() -> str:
    """获取调用飞书自建应用消息 API 所需的 tenant_access_token。"""

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


# Card payload builders -----------------------------------------------------
# 下面的 `_build_xxx_payload` 函数只负责拼飞书卡片 JSON，不负责发送。
# 飞书 interactive card 的基本形状通常是：
# {"msg_type": "interactive", "card": {"schema": "2.0", "header": ..., "body": ...}}

def _build_meeting_card_payload(meeting: MeetingResponse) -> dict[str, Any]:
    """构造会议摘要卡片。"""

    elements = [
        _markdown_block(_build_meeting_status_section(meeting)),
        _divider(),
        _markdown_block(_build_meeting_decision_section(meeting.decisions)),
        _divider(),
        _markdown_block(_build_meeting_action_items_section(meeting.action_items)),
    ]
    follow_up_section = _build_meeting_follow_up_section(meeting.raw_transcript)
    if follow_up_section:
        elements.extend([_divider(), _markdown_block(follow_up_section)])
    elements.extend([_divider(), _markdown_block(_build_meeting_risk_notice(meeting))])

    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📢 {meeting.title}"},
                "template": "blue",
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": elements,
            },
        },
    }


def _build_follow_up_card_payload(meeting: MeetingResponse) -> dict[str, Any]:
    """构造跟进提醒卡片，只展示 pending/in_progress 的行动项。"""

    unfinished_items = [item for item in meeting.action_items if item.status in {"pending", "in_progress"}]

    if unfinished_items:
        body_elements = [
            _markdown_block(_build_follow_up_overview(unfinished_items)),
            _divider(),
            _markdown_block(_build_follow_up_items(unfinished_items)),
            _divider(),
            _markdown_block(_build_compact_task_operations()),
        ]
        template = "orange"
    else:
        body_elements = [_markdown_block("**📍 待跟进行动项**\n· 当前所有行动项都已完成，无需继续跟进。")]
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
    """构造任务完成通知卡片。"""

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
    """构造任务列表卡片，并根据逾期/今日到期情况选择卡片颜色。"""

    raw_items = list(items)
    completed_only = bool(raw_items) and all(item.status == "completed" for item in raw_items)
    materialized = raw_items if completed_only else [item for item in raw_items if item.status != "completed"]
    visible_items = materialized[:10]
    overdue_count = len([item for item in materialized if item.due_status == "overdue"])
    due_today_count = len([item for item in materialized if item.due_status == "due_today"])
    template = "red" if overdue_count else "orange" if due_today_count else "blue"
    title = "📋 任务查询结果" if completed_only else "📋 当前未完成任务"

    if visible_items:
        elements = [
            _markdown_block(
                _build_open_tasks_overview(
                    len(materialized),
                    overdue_count,
                    due_today_count,
                    label="查询结果" if completed_only else "当前未完成任务",
                )
            ),
            _divider(),
            _markdown_block(_build_open_tasks_compact_items(visible_items)),
            _divider(),
            _markdown_block(_build_compact_task_operations(show_done=not completed_only)),
        ]
        if len(materialized) > len(visible_items):
            elements.append(_markdown_block(f"还有 {len(materialized) - len(visible_items)} 项未展示，请到 ActionBridge 任务结果页查看。"))
    else:
        elements = [_markdown_block("**当前未完成任务**\n· 当前没有未完成任务，执行闭环状态良好。")]

    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": template,
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": elements,
            },
        },
    }


def _build_task_detail_payload(item: ActionItemListItem) -> dict[str, Any]:
    """构造单个任务详情卡片。"""

    title = _normalize_action_title(item.title, item.owner_name)
    due_status = item.due_status or get_due_status(item.deadline)
    due_label = item.due_status_label or get_due_status_label(due_status)
    template = (
        "green"
        if item.status == "completed"
        else "red"
        if due_status == "overdue" or item.status == "failed"
        else "orange"
        if due_status == "due_today"
        else "blue"
    )
    operation = "已完成，无需重复操作。" if item.status == "completed" else f"`/done {item.id}`"

    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📋 任务详情 #{item.id}"},
                "template": template,
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": [
                    _markdown_block(f"**任务目标**\n{title}"),
                    _markdown_block(f"**来源会议**\n{item.meeting_title}"),
                    _markdown_block(f"**负责人**\n{item.owner_name}"),
                    _markdown_block(f"**截止时间**\n{item.deadline or '待确认'}"),
                    _markdown_block(f"**状态 / 风险**\n{_get_status_label(item.status)} / {due_label}"),
                    _markdown_block(f"**操作指令**\n完成该任务：{operation}\n查看未完成列表：`/tasks`"),
                ],
            },
        },
    }


def _build_task_not_found_payload(action_item_id: int) -> dict[str, Any]:
    """构造任务不存在提示卡片。"""

    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"🔎 没有找到任务 #{action_item_id}"},
                "template": "orange",
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": [
                    _markdown_block("没有找到这个任务，可能是任务 ID 输入错误，或者任务已被删除。"),
                    _markdown_block(
                        "\n".join(
                            [
                                "**你可以这样检查：**",
                                "`/tasks` 查看当前未完成任务",
                                "`/task 任务ID` 查看任务详情",
                                "确认任务 ID 后再尝试更新。",
                            ]
                        )
                    ),
                ],
            },
        },
    }


def _build_task_create_clarification_payload(message: str) -> dict[str, Any]:
    """构造任务创建信息待补充卡片。"""

    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": "📝 任务信息待补充"},
                "template": "orange",
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": [
                    _markdown_block(message),
                    _markdown_block(
                        "\n".join(
                            [
                                "**可按这个格式发送：**",
                                "`帮我加一个任务，前端同学周五前完成登录页联调`",
                                "`创建任务：设计同学 明天下午 产出首页 banner 图`",
                            ]
                        )
                    ),
                ],
            },
        },
    }


def _build_task_create_confirmation_payload(title: str, owner_name: str, deadline: str) -> dict[str, Any]:
    """构造任务创建确认卡片。"""

    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": "📝 请确认创建任务"},
                "template": "blue",
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": [
                    _markdown_block(f"**任务目标**\n{title}"),
                    _markdown_block(f"**负责人**\n{owner_name}"),
                    _markdown_block(f"**截止时间**\n{deadline}"),
                    _divider(),
                    _markdown_block("回复 `确认` 创建任务，回复 `取消` 放弃。本次确认 30 分钟内有效。"),
                ],
            },
        },
    }


def _build_task_deadline_update_confirmation_payload(
    action_item_id: int,
    title: str,
    old_deadline: str,
    new_deadline: str,
    reference_note: str = "",
) -> dict[str, Any]:
    """构造修改截止时间确认卡片。"""

    elements = [
        _markdown_block(f"**任务**\n{title}"),
        _markdown_block(f"**原截止时间**\n{old_deadline or '未设置'}"),
        _markdown_block(f"**新截止时间**\n{new_deadline}"),
    ]
    if reference_note:
        elements.append(_markdown_block(f"**解析依据**\n{reference_note}"))
    elements.extend(
        [
            _divider(),
            _markdown_block("回复 `确认` 应用修改，回复 `取消` 放弃。本次确认 30 分钟内有效。"),
        ]
    )
    return _build_task_update_confirmation_payload(
        header_title=f"确认修改截止时间 #{action_item_id}",
        elements=elements,
    )


def _build_task_owner_update_confirmation_payload(
    action_item_id: int,
    title: str,
    old_owner_name: str,
    new_owner_name: str,
    reference_note: str = "",
) -> dict[str, Any]:
    """构造修改负责人确认卡片。"""

    elements = [
        _markdown_block(f"**任务**\n{title}"),
        _markdown_block(f"**原负责人**\n{old_owner_name or '未设置'}"),
        _markdown_block(f"**新负责人**\n{new_owner_name}"),
    ]
    if reference_note:
        elements.append(_markdown_block(f"**解析依据**\n{reference_note}"))
    elements.extend(
        [
            _divider(),
            _markdown_block("回复 `确认` 应用修改，回复 `取消` 放弃。本次确认 30 分钟内有效。"),
        ]
    )
    return _build_task_update_confirmation_payload(
        header_title=f"确认修改负责人 #{action_item_id}",
        elements=elements,
    )


def _build_pending_action_notice_payload(title: str, message: str) -> dict[str, Any]:
    """构造通用待确认提示卡片。"""

    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "orange",
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": [_markdown_block(message)],
            },
        },
    }


def _build_task_update_confirmation_payload(header_title: str, elements: list[dict[str, Any]]) -> dict[str, Any]:
    """任务修改确认卡片的公共外壳。"""

    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": header_title},
                "template": "blue",
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": elements,
            },
        },
    }


def _build_project_progress_payload(summary: ProjectProgressSummary) -> dict[str, Any]:
    """构造项目进度卡片，并根据风险选择红/橙/绿/蓝模板。"""

    template = (
        "red"
        if summary.failed_count or summary.overdue_count
        else "orange"
        if summary.due_today_count
        else "green"
        if summary.total_count and summary.completed_count == summary.total_count
        else "blue"
    )

    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📊 {summary.keyword} 当前进度"},
                "template": template,
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": [
                    _markdown_block(_build_project_progress_overview(summary)),
                    _divider(),
                    _markdown_block(f"**⚠️ 进度判断**\n{summary.conclusion}"),
                    _divider(),
                    _markdown_block(_build_project_progress_items(summary.items[:5])),
                ],
            },
        },
    }


def _build_help_card_payload() -> dict[str, Any]:
    """构造帮助卡片。"""

    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": "📘 ActionBridge 使用帮助"},
                "template": "blue",
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": [
                    _markdown_block("**我可以帮你把会议纪要转成行动项，并持续跟进执行进度。**"),
                    _divider(),
                    _markdown_block(
                        "\n".join(
                            [
                                "**会议处理**",
                                "`/meeting 会议标题`",
                                "下一行开始粘贴会议正文，我会生成摘要、决策和行动项。",
                            ]
                        )
                    ),
                    _markdown_block(
                        "\n".join(
                            [
                                "**任务查询**",
                                "`/tasks` 查看未完成任务",
                                "`/task 12` 查看 12 号任务详情",
                                "也可以说：`帮我看看今天到期的任务`、`官网改版相关任务`",
                            ]
                        )
                    ),
                    _markdown_block(
                        "\n".join(
                            [
                                "**任务更新**",
                                "`/done 12` 标记 12 号任务完成",
                                "也可以说：`把 12 号任务标记完成`、`把 8 号任务改成进行中`、`9 号任务有风险`",
                                "修改截止时间：`把 12 号任务延期到周五`，我会先让你确认。",
                                "修改负责人：`把 12 号任务负责人改成测试同学`，我也会先让你确认。",
                            ]
                        )
                    ),
                    _markdown_block(
                        "\n".join(
                            [
                                "**任务创建**",
                                "可以说：`帮我加一个任务，前端同学周五前完成登录页联调`",
                                "我会先让你确认，确认后创建行动项并挂到“飞书临时任务”中。",
                            ]
                        )
                    ),
                    _markdown_block(
                        "\n".join(
                            [
                                "**项目总结**",
                                "可以说：`官网改版进度怎么样`、`官网改版有哪些风险`、`总结一下官网改版项目`",
                            ]
                        )
                    ),
                    _markdown_block(
                        "\n".join(
                            [
                                "**记忆库**",
                                "`/remember 官网 = 官网改版` 记住项目/成员别名",
                                "`/memory` 查看当前记忆",
                                "`/forget 官网` 删除一条记忆",
                            ]
                        )
                    ),
                    _divider(),
                    _markdown_block("**回复范围**\n私聊触发会回复私聊；群里触发会回复原群；后台发送和自动提醒会发到默认群。"),
                ],
            },
        },
    }


def _build_memory_saved_payload(item: MemoryAliasItem) -> dict[str, Any]:
    """构造 Memory 保存成功卡片。"""

    return _build_simple_memory_payload(
        title="🧠 已记住",
        template="green",
        lines=[
            f"类型：{item.memory_type}",
            f"别名：{item.alias}",
            f"标准说法：{item.target}",
            "之后我会先用这条记忆归一化你的自然语言查询。",
        ],
    )


def _build_memory_deleted_payload(item: MemoryAliasItem) -> dict[str, Any]:
    """构造 Memory 删除成功卡片。"""

    return _build_simple_memory_payload(
        title="🧹 已忘记",
        template="orange",
        lines=[
            f"别名：{item.alias}",
            f"原标准说法：{item.target}",
        ],
    )


def _build_memory_list_payload(items: Iterable[MemoryAliasItem]) -> dict[str, Any]:
    """构造 Memory 列表卡片。"""

    materialized = list(items)
    if materialized:
        lines = [
            f"- `{item.alias}` = `{item.target}` ({item.memory_type})"
            for item in materialized[:20]
        ]
        if len(materialized) > 20:
            lines.append(f"- 还有 {len(materialized) - 20} 条未展示")
    else:
        lines = ["当前还没有记忆。可以发送：`/remember 官网 = 官网改版`"]

    return _build_simple_memory_payload(
        title="🧠 当前记忆",
        template="blue",
        lines=lines,
    )


def _build_simple_memory_payload(title: str, template: str, lines: list[str]) -> dict[str, Any]:
    """构造只有一个 markdown 区块的 Memory 卡片。"""

    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": template,
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": [_markdown_block("\n".join(lines))],
            },
        },
    }


def _build_open_task_elements(items: Iterable[ActionItemListItem]) -> list[dict[str, Any]]:
    """构造较详细的任务元素列表，保留给需要逐字段展示的卡片布局。"""

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
    """构造会议行动项元素列表，保留给较详细的会议卡片布局。"""

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


# Text section builders -----------------------------------------------------
# 这些函数把会议、任务、进度等业务对象转换成 markdown 字符串，
# 再交给 `_markdown_block` 包装成飞书卡片元素。

def _build_meeting_status_section(meeting: MeetingResponse) -> str:
    """从原始会议记录中提取“当前状态”段落；没有就用摘要兜底。"""

    status_lines = _extract_section_lines(meeting.raw_transcript, ("当前状态",), ("已确认决策", "待办事项", "后续跟进"))
    if not status_lines:
        status_lines = [meeting.summary] if meeting.summary else []
    return "\n".join(["**当前状态**", *_format_dot_lines(status_lines)])


def _build_meeting_decision_section(decisions: Iterable[str]) -> str:
    """把关键决策列表格式化成飞书 markdown。"""

    materialized = [decision.strip() for decision in decisions if decision.strip()]
    if not materialized:
        return "**✅ 已确认决策**\n· 暂无明确决策"
    lines = [f"{index}. {decision}" for index, decision in enumerate(materialized, start=1)]
    return "\n".join(["**✅ 已确认决策**", *lines])


def _build_meeting_action_items_section(items: Iterable[ActionItemResponse]) -> str:
    """把行动项列表格式化成飞书 markdown。"""

    materialized = list(items)
    if not materialized:
        return "**📋 待办事项**\n· 暂无待办事项"

    lines = [
        "· "
        + f"负责人：{item.owner_name or '待确认'}，"
        + f"任务：{_normalize_action_title(item.title, item.owner_name)}，"
        + f"截止时间：{item.deadline or '待确认'}"
        for item in materialized
    ]
    return "\n".join(["**📋 待办事项**", *lines])


def _build_meeting_follow_up_section(transcript: str) -> str:
    """从会议原文中提取“后续跟进”段落。"""

    follow_up_lines = _extract_section_lines(transcript, ("后续跟进",), ("风险", "提醒", "⚠", "待办事项"))
    if not follow_up_lines:
        return ""
    return "\n".join(["**🔜 后续跟进**", *_format_dot_lines(follow_up_lines)])


def _build_meeting_risk_notice(meeting: MeetingResponse) -> str:
    """构造会议卡片底部的风险提醒。"""

    warning_lines = _extract_warning_lines(meeting.raw_transcript)
    if warning_lines:
        return "\n".join([f"> ⚠️ {line}" for line in warning_lines])

    unfinished_count = len([item for item in meeting.action_items if item.status in {"pending", "in_progress", "failed"}])
    if unfinished_count:
        return f"> ⚠️ 当前仍有 {unfinished_count} 个行动项待跟进，请各负责人及时同步完成状态。"
    return "> ✅ 当前行动项均已完成，暂无待跟进事项。"


def _build_project_progress_overview(summary: ProjectProgressSummary) -> str:
    """构造项目进度指标总览。"""

    return "\n".join(
        [
            f"**完成率：{summary.completion_rate}%**",
            (
                f"· 总数：{summary.total_count} ｜ 已完成：{summary.completed_count} ｜ "
                f"进行中：{summary.in_progress_count} ｜ 待处理：{summary.pending_count}"
            ),
            f"· 逾期：{summary.overdue_count} ｜ 今日到期：{summary.due_today_count} ｜ 有风险：{summary.failed_count}",
        ]
    )


def _build_project_progress_items(items: Iterable[ActionItemListItem]) -> str:
    """构造项目进度卡片里的重点任务列表。"""

    materialized = list(items)
    if not materialized:
        return "**📋 重点任务**\n· 暂无相关任务"

    lines = []
    for item in materialized:
        risk_prefix = "🚨" if item.due_status == "overdue" else "⏰" if item.due_status == "due_today" else "📌"
        title = _normalize_action_title(item.title, item.owner_name)
        lines.append(
            f"· {risk_prefix} #{item.id} {title}，负责人：{item.owner_name}，"
            f"截止：{item.deadline or '待确认'}，状态：{_get_status_label(item.status)}"
        )
    return "\n".join(["**📋 重点任务**", *lines])


def _build_open_tasks_overview(
    total_count: int,
    overdue_count: int,
    due_today_count: int,
    *,
    label: str = "当前未完成任务",
) -> str:
    """构造任务列表卡片的统计总览。"""

    return "\n".join(
        [
            f"**{label}：{total_count} 项**",
            f"· 已逾期：{overdue_count} ｜ 今日到期：{due_today_count}",
        ]
    )


def _build_open_tasks_compact_items(items: Iterable[ActionItemListItem]) -> str:
    """构造任务列表卡片中的紧凑任务行。"""

    materialized = list(items)
    if not materialized:
        return "**📋 任务清单**\n· 暂无未完成任务"
    return "\n".join(["**📋 任务清单**", *[_format_compact_task_item(item) for item in materialized]])


def _build_follow_up_overview(items: Iterable[ActionItemResponse]) -> str:
    """构造跟进提醒卡片的任务数量说明。"""

    materialized = list(items)
    return "\n".join(
        [
            f"**待跟进行动项：{len(materialized)} 项**",
            "· 请优先确认以下任务完成状态，有问题及时同步。",
        ]
    )


def _build_follow_up_items(items: Iterable[ActionItemResponse]) -> str:
    """构造跟进提醒卡片中的任务清单。"""

    materialized = list(items)
    if not materialized:
        return "**📋 跟进清单**\n· 暂无待跟进行动项"
    lines = [
        f"· 📌 #{item.id} {_normalize_action_title(item.title, item.owner_name)}，"
        f"负责人：{item.owner_name}，截止：{item.deadline or '待确认'}，状态：{_get_status_label(item.status)}"
        for item in materialized
    ]
    return "\n".join(["**📋 跟进清单**", *lines])


def _format_compact_task_item(item: ActionItemListItem) -> str:
    """把一个任务格式化成单行文本，并加上风险前缀。"""

    risk_prefix = "🚨" if item.due_status == "overdue" else "⏰" if item.due_status == "due_today" else "📌"
    title = _normalize_action_title(item.title, item.owner_name)
    return (
        f"· {risk_prefix} #{item.id} {title}，负责人：{item.owner_name}，"
        f"截止：{item.deadline or '待确认'}，状态：{_get_status_label(item.status)}"
    )


def _build_compact_task_operations(*, show_done: bool = True) -> str:
    """构造任务卡片底部的操作提示。"""

    operation_line = (
        "· 完成任务：`/done 任务ID` ｜ 查看详情：`/task 任务ID`"
        if show_done
        else "· 查看详情：`/task 任务ID`"
    )
    extra_line = (
        "· 也可以直接回复：`#任务ID 有风险`、`#任务ID 还在进行中`"
        if show_done
        else "· 如需重新跟进，可在后台把状态改回待处理或进行中。"
    )
    return "\n".join(
        [
            "**操作**",
            operation_line,
            extra_line,
        ]
    )


# Low-level formatting helpers ---------------------------------------------
# 最底部是字符串清洗、markdown block、状态文案等小工具。

def _extract_section_lines(transcript: str, starts: tuple[str, ...], stops: tuple[str, ...]) -> list[str]:
    """从会议原文中截取某个标题开始、下一个标题结束之间的行。"""

    lines = [_clean_meeting_line(line) for line in transcript.splitlines()]
    lines = [line for line in lines if line]
    collecting = False
    result: list[str] = []
    for line in lines:
        if _line_contains_any(line, starts):
            collecting = True
            continue
        if collecting and _line_contains_any(line, stops):
            break
        if collecting:
            result.append(line)
    return result


def _extract_warning_lines(transcript: str) -> list[str]:
    """从会议原文中提取看起来像风险/提醒的行。"""

    return [
        _clean_meeting_line(line)
        for line in transcript.splitlines()
        if "⚠" in line or "风险" in line or "及时同步" in line
        if _clean_meeting_line(line)
    ]


def _format_dot_lines(lines: Iterable[str]) -> list[str]:
    """把普通文本行转成飞书卡片里的点状列表。"""

    return [f"· {line.strip()}" for line in lines if line.strip()]


def _clean_meeting_line(line: str) -> str:
    """清理会议原文行首的符号、emoji 和多余空白。"""

    cleaned = line.strip().strip("-").strip()
    for prefix in ("📢", "✅", "📋", "🔜", "⚠️", "⚠"):
        cleaned = cleaned.removeprefix(prefix).strip()
    return cleaned


def _line_contains_any(line: str, keywords: tuple[str, ...]) -> bool:
    """判断一行文本是否包含任意关键词。"""

    return any(keyword in line for keyword in keywords)


def _markdown_block(content: str) -> dict[str, Any]:
    """把 markdown 字符串包装成飞书卡片元素。"""

    return {
        "tag": "markdown",
        "content": content,
        "text_align": "left",
        "text_size": "normal_v2",
        "margin": "0px 0px 8px 0px",
    }


def _divider() -> dict[str, Any]:
    """构造飞书卡片里的分割线元素。"""

    return {
        "tag": "hr",
        "margin": "8px 0px 8px 0px",
    }


def _format_bullets(items: Iterable[str]) -> str:
    """把字符串列表格式化成普通 markdown bullet 列表。"""

    materialized = [item.strip() for item in items if item.strip()]
    if not materialized:
        return "- 暂无明确结论"
    return "\n".join(f"- {item}" for item in materialized)


def _get_status_label(status: str) -> str:
    """把内部任务状态转换成中文展示文案。"""

    return {
        "pending": "待处理",
        "in_progress": "进行中",
        "completed": "已完成",
        "failed": "有风险",
    }.get(status, status)


def _normalize_action_title(title: str, owner_name: str) -> str:
    """去掉任务标题里的英文前缀和重复负责人。"""

    normalized = title.strip()
    prefixes = ("Action:", "Next step:", "Todo:", "Follow up:", "Follow-up:")
    for prefix in prefixes:
        if normalized.lower().startswith(prefix.lower()):
            normalized = normalized[len(prefix) :].strip()
            break

    if owner_name and normalized.startswith(owner_name):
        normalized = normalized[len(owner_name) :].strip()

    return normalized or title.strip()
