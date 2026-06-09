import re
from dataclasses import dataclass
from typing import Any

from app.core.config import FEISHU_BOT_NAME


# 飞书群聊类型。群聊中默认不处理自然语言，避免机器人误响应所有聊天。
GROUP_CHAT_TYPES = {"group", "chat", "supergroup"}

# 飞书私聊类型。私聊通常可以直接交给 Agent 处理。
PRIVATE_CHAT_TYPES = {"p2p", "private", "single"}


@dataclass(frozen=True)
class FeishuAgentGate:
    # Agent 消息入口的门禁结果：是否处理、清理后的文本、原因。
    should_process: bool
    message_text: str
    reason: str = ""


def gate_agent_message(
    payload: dict[str, Any],
    message_text: str,
    *,
    has_fixed_command: bool,
    has_active_pending_action: bool,
    is_confirmation_message: bool,
) -> FeishuAgentGate:
    # 判断一条飞书消息是否应该进入 Agent 自然语言流程。
    stripped = message_text.strip()
    if not stripped:
        return FeishuAgentGate(False, "", "empty_message")

    # 先识别聊天类型、是否 @ 机器人，并移除 @ 文本。
    chat_type = extract_chat_type(payload)
    mentioned = is_bot_mentioned(payload, stripped)
    cleaned_text = strip_bot_mentions(payload, stripped)

    if has_fixed_command:
        # 固定命令如 /tasks、/done 不受群聊 @ 限制。
        return FeishuAgentGate(True, cleaned_text, "fixed_command")

    if chat_type in PRIVATE_CHAT_TYPES or not chat_type:
        # 私聊或未知聊天类型默认放行，提升可用性。
        return FeishuAgentGate(True, cleaned_text, "private_or_unknown_chat")

    if chat_type in GROUP_CHAT_TYPES:
        if mentioned:
            # 群聊里明确 @ 机器人时，才进入自然语言 Agent。
            return FeishuAgentGate(True, cleaned_text, "bot_mentioned")
        if has_active_pending_action and is_confirmation_message:
            # 如果正在等待确认，用户在群里回复“确认/取消”也允许处理。
            return FeishuAgentGate(True, cleaned_text, "pending_confirmation")
        return FeishuAgentGate(False, cleaned_text, "group_message_without_bot_mention")

    return FeishuAgentGate(True, cleaned_text, "unsupported_chat_type_fallback")


def extract_chat_type(payload: dict[str, Any]) -> str | None:
    # 从飞书 payload 的不同层级里尽量提取 chat_type。
    message = _message(payload)
    candidates = [
        message.get("chat_type"),
        payload.get("chat_type"),
        payload.get("message", {}).get("chat_type") if isinstance(payload.get("message"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip().lower()
    return None


def is_bot_mentioned(payload: dict[str, Any], message_text: str) -> bool:
    # 判断消息是否 @ 了当前机器人，支持飞书 mentions 数组和纯文本 @ 名称。
    bot_name = FEISHU_BOT_NAME.strip().lower()
    for mention in _mentions(payload):
        name = str(mention.get("name") or "").strip().lower()
        key = str(mention.get("key") or "").strip()
        if bot_name and name == bot_name:
            return True
        if key and key in message_text:
            return True

    return bool(bot_name and re.search(rf"@{re.escape(bot_name)}\b", message_text, re.IGNORECASE))


def strip_bot_mentions(payload: dict[str, Any], message_text: str) -> str:
    # 移除 @ 机器人的文本，留下真正要给 Agent 理解的用户指令。
    cleaned = message_text
    bot_name = FEISHU_BOT_NAME.strip()
    for mention in _mentions(payload):
        key = str(mention.get("key") or "").strip()
        name = str(mention.get("name") or "").strip()
        if key:
            cleaned = cleaned.replace(key, " ")
        if name:
            cleaned = re.sub(rf"@\s*{re.escape(name)}", " ", cleaned, flags=re.IGNORECASE)

    if bot_name:
        cleaned = re.sub(rf"@\s*{re.escape(bot_name)}", " ", cleaned, flags=re.IGNORECASE)

    return re.sub(r"\s+", " ", cleaned).strip()


def _message(payload: dict[str, Any]) -> dict[str, Any]:
    # 兼容飞书事件 payload 的不同结构，统一取 message 对象。
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    if message:
        return message
    return payload.get("message") if isinstance(payload.get("message"), dict) else {}


def _mentions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    # 统一提取 mentions 列表，并过滤掉非 dict 的异常项。
    message = _message(payload)
    mentions = message.get("mentions") or payload.get("mentions") or []
    return [mention for mention in mentions if isinstance(mention, dict)]
