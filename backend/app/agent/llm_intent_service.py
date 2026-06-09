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


# LLM 兜底允许返回的意图名称。
# 不在这个集合里的 intent 会被丢弃，避免 LLM 返回项目不支持的操作。
SUPPORTED_INTENTS = {
    "create_task",
    "clarify_task_reference",
    "update_task_deadline",
    "update_task_owner",
    "update_task_status",
    "query_tasks",
    "summarize_project",
    "help",
}

# 任务状态也必须限制在系统支持的状态值里。
SUPPORTED_STATUSES = {"pending", "in_progress", "completed", "failed"}


# 对外入口：用 LLM 尝试识别自然语言意图。
# 注意：它只是“兜底”，规则识别失败时才会调用。
def detect_llm_intent(message: str) -> AgentIntent | None:
    # 没有配置可用 API key 或 openai 包不可用时，直接跳过 LLM。
    if not _should_use_llm():
        return None

    # 调用 LLM，期望拿到 JSON dict。
    payload = _call_intent_llm(message)
    if not payload:
        return None

    # 把 LLM 返回的 JSON 严格转换成 AgentIntent。
    return _intent_from_payload(payload, source_message=message)


def _should_use_llm() -> bool:
    # 当前项目用 PARSER_PROVIDER 决定调用 DeepSeek 还是 OpenAI-compatible API。
    # key 不能是空值，也不能是 .env.example 里的 replace_with_xxx 占位符。
    return OpenAI is not None and (
        _has_real_value(DEEPSEEK_API_KEY) if PARSER_PROVIDER.lower() == "deepseek" else _has_real_value(OPENAI_API_KEY)
    )


def _has_real_value(value: str | None) -> bool:
    # 判断环境变量是否是真实配置，而不是示例占位符。
    return bool(value) and not value.startswith("replace_with_")


# 调用 LLM，把用户自然语言转换成 JSON。
# 这里只负责拿原始 JSON，不在这里直接信任或执行业务动作。
def _call_intent_llm(message: str) -> dict[str, Any] | None:
    provider = PARSER_PROVIDER.lower()
    if provider == "deepseek":
        # DeepSeek 使用 OpenAI-compatible client，但需要配置 base_url。
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        model = DEEPSEEK_MODEL
    else:
        client = OpenAI(api_key=OPENAI_API_KEY)
        model = OPENAI_MODEL

    try:
        # 要求 LLM 只返回 JSON，并明确告诉它支持哪些 intent 和字段。
        # 关键约束：不要编造 action_item_id；没有明确任务 ID 时返回 clarify_task_reference。
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are ActionBridge's intent classifier. Return JSON only. "
                        "Supported intent values: create_task, update_task_deadline, update_task_owner, "
                        "update_task_status, query_tasks, summarize_project, clarify_task_reference, help, none. "
                        "Fields: action_item_id, title, owner_name, deadline, status, keyword, due_status, "
                        "open_only, missing_fields, raw_text. "
                        "status must be one of pending, in_progress, completed, failed. "
                        "Never invent action_item_id. If the user wants to update a task but does not provide "
                        "a clear task id, return clarify_task_reference with missing_fields='任务编号'. "
                        "For task queries, extract owner, keyword, due_status, status, and open_only when possible."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Convert this user message into JSON. Example: "
                        '{"intent":"update_task_owner","filters":{"action_item_id":"12","owner_name":"测试同学"}}'
                        f"\nUser message: {message}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
    except Exception:
        # LLM 调用失败时返回 None，让上层继续走忽略/兜底帮助逻辑。
        return None

    content = response.choices[0].message.content if response.choices else None
    if not content:
        return None

    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        # LLM 没按要求返回合法 JSON，就不使用这次结果。
        return None

    return payload if isinstance(payload, dict) else None


# 把 LLM 返回的 JSON 转成系统内部 AgentIntent。
# 这是安全校验层：字段不完整、不合法、疑似编造任务 ID 的结果都会被拒绝或改成澄清意图。
def _intent_from_payload(payload: dict[str, Any], source_message: str | None = None) -> AgentIntent | None:
    intent_name = str(payload.get("intent", "")).strip()
    if intent_name == "none" or intent_name not in SUPPORTED_INTENTS:
        # 不支持的 intent 直接丢弃。
        return None

    raw_filters = payload.get("filters")
    # filters 统一转成 str -> str，方便后续和规则识别结果保持一致。
    filters = {str(key): str(value).strip() for key, value in raw_filters.items()} if isinstance(raw_filters, dict) else {}

    if intent_name == "create_task":
        # 创建任务必须同时有标题、负责人、截止时间。
        if not all(filters.get(key) for key in ("title", "owner_name", "deadline")):
            return None
        return AgentIntent(name=intent_name, filters=_pick(filters, "title", "owner_name", "deadline"))

    if intent_name == "clarify_task_reference":
        # 任务引用不清楚时，返回澄清意图，让机器人提示用户补充任务编号。
        return AgentIntent(
            name=intent_name,
            filters=filters or {"missing_fields": "任务编号", "raw_text": source_message or ""},
        )

    if intent_name == "update_task_deadline":
        # 修改截止时间必须至少知道新的 deadline。
        if not filters.get("deadline"):
            return None
        if not filters.get("action_item_id"):
            # 没有任务 ID 时，不允许直接修改，转成澄清意图。
            return _build_task_reference_clarification(
                source_message or "",
                {
                    "target_intent": "update_task_deadline",
                    "deadline": filters["deadline"],
                },
            )
        if source_message and not _message_has_explicit_task_id(source_message, filters["action_item_id"]):
            # 如果 LLM 给了任务 ID，但用户原话里并没有这个 ID，也视为可能是编造，要求澄清。
            return _build_task_reference_clarification(
                source_message,
                {
                    "target_intent": "update_task_deadline",
                    "deadline": filters["deadline"],
                },
            )
        return AgentIntent(name=intent_name, filters=_pick(filters, "action_item_id", "deadline"))

    if intent_name == "update_task_owner":
        # 修改负责人必须知道新的 owner_name。
        if not filters.get("owner_name"):
            return None
        if not filters.get("action_item_id"):
            # 没有任务 ID 时，不允许直接修改，转成澄清意图。
            return _build_task_reference_clarification(
                source_message or "",
                {
                    "target_intent": "update_task_owner",
                    "owner_name": filters["owner_name"],
                },
            )
        if source_message and not _message_has_explicit_task_id(source_message, filters["action_item_id"]):
            # 防止 LLM 编造任务 ID。
            return _build_task_reference_clarification(
                source_message,
                {
                    "target_intent": "update_task_owner",
                    "owner_name": filters["owner_name"],
                },
            )
        return AgentIntent(name=intent_name, filters=_pick(filters, "action_item_id", "owner_name"))

    if intent_name == "update_task_status":
        # 修改状态时，status 必须是系统支持的值。
        if filters.get("status") not in SUPPORTED_STATUSES:
            return None
        if not filters.get("action_item_id"):
            # 没有任务 ID 时，不允许直接修改，转成澄清意图。
            return _build_task_reference_clarification(
                source_message or "",
                {
                    "target_intent": "update_task_status",
                    "status": filters["status"],
                },
            )
        if source_message and not _message_has_explicit_task_id(source_message, filters["action_item_id"]):
            # 防止 LLM 编造任务 ID。
            return _build_task_reference_clarification(
                source_message,
                {
                    "target_intent": "update_task_status",
                    "status": filters["status"],
                },
            )
        return AgentIntent(name=intent_name, filters=_pick(filters, "action_item_id", "status"))

    if intent_name == "query_tasks":
        # 查询任务是读操作，允许字段不完整；没有条件时默认查未完成任务。
        allowed = _pick(filters, "owner", "keyword", "due_status", "status", "open_only")
        return AgentIntent(name=intent_name, filters=allowed or {"open_only": "true"})

    if intent_name == "summarize_project":
        # 总结项目必须知道项目关键词。
        if not filters.get("keyword"):
            return None
        return AgentIntent(name=intent_name, filters=_pick(filters, "keyword"))

    if intent_name == "help":
        # 帮助意图不需要 filters。
        return AgentIntent(name="help")

    return None


def _pick(source: dict[str, str], *keys: str) -> dict[str, str]:
    # 从 filters 里挑出允许透传的字段，避免多余字段污染后续流程。
    return {key: source[key] for key in keys if source.get(key)}


def _message_has_explicit_task_id(message: str, action_item_id: str) -> bool:
    # 判断用户原文里是否真的出现了这个任务 ID。
    # 允许 "12" 或 "#12" 两种形式。
    normalized_id = action_item_id.strip()
    if not normalized_id:
        return False
    return normalized_id in message or f"#{normalized_id}" in message


# 构造“任务引用不清楚”的澄清意图。
# 上层 orchestrator 会据此发送补充提示，而不是直接执行危险写操作。
def _build_task_reference_clarification(message: str, extra_filters: dict[str, str] | None = None) -> AgentIntent:
    filters = {
        "missing_fields": "任务编号",
        "raw_text": message,
    }
    if extra_filters:
        filters.update(extra_filters)

    return AgentIntent(
        name="clarify_task_reference",
        filters=filters,
    )
