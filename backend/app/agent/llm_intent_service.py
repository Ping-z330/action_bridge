import json
from typing import Any

from app.agent.schemas import AgentIntent
from app.core.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    PARSER_PROVIDER,
)

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


SUPPORTED_INTENTS = {
    "create_task",
    "update_task_deadline",
    "update_task_owner",
    "update_task_status",
    "query_tasks",
    "summarize_project",
    "help",
}
SUPPORTED_STATUSES = {"pending", "in_progress", "completed", "failed"}


def detect_llm_intent(message: str) -> AgentIntent | None:
    if not _should_use_llm():
        return None

    payload = _call_intent_llm(message)
    if not payload:
        return None

    return _intent_from_payload(payload)


def _should_use_llm() -> bool:
    return OpenAI is not None and (
        _has_real_value(DEEPSEEK_API_KEY) if PARSER_PROVIDER.lower() == "deepseek" else _has_real_value(OPENAI_API_KEY)
    )


def _has_real_value(value: str | None) -> bool:
    return bool(value) and not value.startswith("replace_with_")


def _call_intent_llm(message: str) -> dict[str, Any] | None:
    provider = PARSER_PROVIDER.lower()
    if provider == "deepseek":
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        model = DEEPSEEK_MODEL
    else:
        client = OpenAI(api_key=OPENAI_API_KEY)
        model = OPENAI_MODEL

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 ActionBridge 的意图识别器，只返回 JSON，不要解释。"
                        "支持的 intent：create_task, update_task_deadline, update_task_owner, "
                        "update_task_status, query_tasks, summarize_project, help, none。"
                        "如果用户想修改数据库，必须抽取明确字段，不能猜。"
                        "字段命名：action_item_id, title, owner_name, deadline, status, keyword, due_status, open_only。"
                        "status 只能是 pending, in_progress, completed, failed。"
                        "如果没有明确任务 ID，不要输出 update_task_*。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请把用户消息转成 JSON，格式示例："
                        '{"intent":"update_task_owner","filters":{"action_item_id":"12","owner_name":"测试同学"}}'
                        f"\n用户消息：{message}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
    except Exception:
        return None

    content = response.choices[0].message.content if response.choices else None
    if not content:
        return None

    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None

    return payload if isinstance(payload, dict) else None


def _intent_from_payload(payload: dict[str, Any]) -> AgentIntent | None:
    intent_name = str(payload.get("intent", "")).strip()
    if intent_name == "none" or intent_name not in SUPPORTED_INTENTS:
        return None

    raw_filters = payload.get("filters")
    filters = {str(key): str(value).strip() for key, value in raw_filters.items()} if isinstance(raw_filters, dict) else {}

    if intent_name == "create_task":
        if not all(filters.get(key) for key in ("title", "owner_name", "deadline")):
            return None
        return AgentIntent(name=intent_name, filters=_pick(filters, "title", "owner_name", "deadline"))

    if intent_name == "update_task_deadline":
        if not filters.get("action_item_id") or not filters.get("deadline"):
            return None
        return AgentIntent(name=intent_name, filters=_pick(filters, "action_item_id", "deadline"))

    if intent_name == "update_task_owner":
        if not filters.get("action_item_id") or not filters.get("owner_name"):
            return None
        return AgentIntent(name=intent_name, filters=_pick(filters, "action_item_id", "owner_name"))

    if intent_name == "update_task_status":
        if not filters.get("action_item_id") or filters.get("status") not in SUPPORTED_STATUSES:
            return None
        return AgentIntent(name=intent_name, filters=_pick(filters, "action_item_id", "status"))

    if intent_name == "query_tasks":
        allowed = _pick(filters, "owner", "keyword", "due_status", "status", "open_only")
        return AgentIntent(name=intent_name, filters=allowed or {"open_only": "true"})

    if intent_name == "summarize_project":
        if not filters.get("keyword"):
            return None
        return AgentIntent(name=intent_name, filters=_pick(filters, "keyword"))

    if intent_name == "help":
        return AgentIntent(name="help")

    return None


def _pick(source: dict[str, str], *keys: str) -> dict[str, str]:
    return {key: source[key] for key in keys if source.get(key)}
