import re
from dataclasses import dataclass
from typing import Any

from app.core.config import FEISHU_BOT_NAME


GROUP_CHAT_TYPES = {"group", "chat", "supergroup"}
PRIVATE_CHAT_TYPES = {"p2p", "private", "single"}


@dataclass(frozen=True)
class FeishuAgentGate:
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
    stripped = message_text.strip()
    if not stripped:
        return FeishuAgentGate(False, "", "empty_message")

    chat_type = extract_chat_type(payload)
    mentioned = is_bot_mentioned(payload, stripped)
    cleaned_text = strip_bot_mentions(payload, stripped)

    if has_fixed_command:
        return FeishuAgentGate(True, cleaned_text, "fixed_command")

    if chat_type in PRIVATE_CHAT_TYPES or not chat_type:
        return FeishuAgentGate(True, cleaned_text, "private_or_unknown_chat")

    if chat_type in GROUP_CHAT_TYPES:
        if mentioned:
            return FeishuAgentGate(True, cleaned_text, "bot_mentioned")
        if has_active_pending_action and is_confirmation_message:
            return FeishuAgentGate(True, cleaned_text, "pending_confirmation")
        return FeishuAgentGate(False, cleaned_text, "group_message_without_bot_mention")

    return FeishuAgentGate(True, cleaned_text, "unsupported_chat_type_fallback")


def extract_chat_type(payload: dict[str, Any]) -> str | None:
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
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    if message:
        return message
    return payload.get("message") if isinstance(payload.get("message"), dict) else {}


def _mentions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    message = _message(payload)
    mentions = message.get("mentions") or payload.get("mentions") or []
    return [mention for mention in mentions if isinstance(mention, dict)]
