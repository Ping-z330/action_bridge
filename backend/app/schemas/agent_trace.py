from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AgentTraceLogItem(BaseModel):
    id: int
    chat_id: str
    source: str
    message: str
    normalized_message: str
    intent_name: str
    intent_filters: dict[str, Any]
    tool_name: str
    tool_source: str
    tool_category: str
    tool_executed: bool
    dangerous: bool
    requires_confirmation: bool
    response_message: str
    created_at: datetime


class AgentDebugRunRequest(BaseModel):
    message: str
    chat_id: str = "debug-web"


class AgentDebugRunResponse(BaseModel):
    handled: bool
    intent_name: str
    message: str
    trace_id: int | None = None
