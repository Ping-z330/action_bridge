import json
from typing import Any

from sqlalchemy.orm import Session

from app.agent.schemas import AgentResponse
from app.agent.tool_registry import DEFAULT_TOOL_REGISTRY
from app.models.agent_trace_log import AgentTraceLog


def create_agent_trace_log(
    db: Session,
    *,
    message: str,
    chat_id: str = "",
    normalized_message: str = "",
    intent_name: str = "",
    intent_filters_json: str = "{}",
    tool_name: str = "",
    tool_executed: bool = False,
    response: AgentResponse | None = None,
) -> AgentTraceLog | None:
    """Create an Agent trace log entry.

    The new signature accepts intent_name and intent_filters_json directly
    instead of an AgentIntent object. Trace is auxiliary logging; failure
    must not break the main request flow.
    """
    try:
        tool = DEFAULT_TOOL_REGISTRY.get(tool_name) if tool_name else None

        trace = AgentTraceLog(
            chat_id=chat_id or "",
            source="debug" if chat_id.startswith("debug") else "feishu" if chat_id else "agent",
            message=message or "",
            normalized_message=normalized_message or "",
            intent_name=intent_name or "unhandled",
            intent_filters_json=intent_filters_json,
            tool_name=tool.name if tool else tool_name,
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
        db.rollback()
        return None


def list_agent_trace_logs(db: Session, limit: int = 50) -> list[AgentTraceLog]:
    safe_limit = min(max(limit, 1), 100)
    return db.query(AgentTraceLog).order_by(AgentTraceLog.id.desc()).limit(safe_limit).all()


def get_latest_agent_trace_log(db: Session, chat_id: str | None = None) -> AgentTraceLog | None:
    query = db.query(AgentTraceLog)
    if chat_id:
        query = query.filter(AgentTraceLog.chat_id == chat_id)
    return query.order_by(AgentTraceLog.id.desc()).first()


def parse_trace_filters(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
