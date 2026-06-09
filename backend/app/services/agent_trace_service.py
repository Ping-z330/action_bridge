import json
from typing import Any

from sqlalchemy.orm import Session

from app.agent.schemas import AgentIntent, AgentResponse
from app.agent.tool_registry import (
    CREATE_TASK,
    DEFAULT_TOOL_REGISTRY,
    QUERY_TASKS,
    SUMMARIZE_PROJECT,
    UPDATE_TASK_DEADLINE,
    UPDATE_TASK_OWNER,
    UPDATE_TASK_STATUS,
)
from app.models.agent_trace_log import AgentTraceLog


# Agent 意图和工具名的映射，用来在 trace 里记录“这次应该调用哪个工具”。
INTENT_TOOL_MAP = {
    "query_tasks": QUERY_TASKS,
    "summarize_project": SUMMARIZE_PROJECT,
    "update_task_status": UPDATE_TASK_STATUS,
    "confirm_create_task": CREATE_TASK,
    "confirm_update_task_deadline": UPDATE_TASK_DEADLINE,
    "confirm_update_task_owner": UPDATE_TASK_OWNER,
}


def create_agent_trace_log(
    db: Session,
    *,
    message: str,
    chat_id: str = "",
    normalized_message: str = "",
    intent: AgentIntent | None = None,
    tool_executed: bool = False,
    response: AgentResponse | None = None,
) -> AgentTraceLog | None:
    # 创建一条 Agent 调试轨迹。
    # 这个函数尽量不影响主流程：写日志失败时会 rollback 并返回 None。
    try:
        tool_name = INTENT_TOOL_MAP.get(intent.name if intent else "")
        # 找到对应工具后，可以记录工具来源、分类、是否危险等元信息。
        tool = DEFAULT_TOOL_REGISTRY.get(tool_name) if tool_name else None

        trace = AgentTraceLog(
            chat_id=chat_id or "",
            source="debug" if chat_id.startswith("debug") else "feishu" if chat_id else "agent",
            message=message or "",
            normalized_message=normalized_message or "",
            intent_name=intent.name if intent else "unhandled",
            intent_filters_json=json.dumps(intent.filters if intent else {}, ensure_ascii=False),
            tool_name=tool.name if tool else "",
            tool_source=tool.source if tool else "",
            tool_category=tool.category if tool else "",
            tool_executed=tool_executed,
            dangerous=tool.dangerous if tool else False,
            requires_confirmation=tool.requires_confirmation if tool else False,
            response_message=response.message if response else "",
        )
        db.add(trace)
        db.commit()
        db.refresh(trace)
        return trace
    except Exception:
        # trace 是辅助日志，失败不能让用户的真实请求失败。
        db.rollback()
        return None


def list_agent_trace_logs(db: Session, limit: int = 50) -> list[AgentTraceLog]:
    # 返回最近的 Agent 轨迹，limit 做边界保护，避免一次查太多。
    safe_limit = min(max(limit, 1), 100)
    return db.query(AgentTraceLog).order_by(AgentTraceLog.id.desc()).limit(safe_limit).all()


def get_latest_agent_trace_log(db: Session, chat_id: str | None = None) -> AgentTraceLog | None:
    # 查询最新一条轨迹；传 chat_id 时只看某个会话。
    query = db.query(AgentTraceLog)
    if chat_id:
        query = query.filter(AgentTraceLog.chat_id == chat_id)
    return query.order_by(AgentTraceLog.id.desc()).first()


def parse_trace_filters(value: str) -> dict[str, Any]:
    # 把数据库里保存的 intent_filters_json 转成字典，解析失败就返回空字典。
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
