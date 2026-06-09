from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AgentTraceLogItem(BaseModel):
    # Agent 调试轨迹列表里的单条记录，用于前端查看 Agent 如何识别和调用工具。
    id: int
    # 飞书会话 ID 或调试会话 ID。
    chat_id: str
    # 来源，比如 agent / debug。
    source: str
    # 用户原始输入。
    message: str
    # 经过记忆别名替换等处理后的输入。
    normalized_message: str
    # 识别出的意图名称。
    intent_name: str
    # 意图参数，已经从数据库里的 JSON 字符串转成字典。
    intent_filters: dict[str, Any]
    # 调用的工具名称。
    tool_name: str
    # 工具来源，比如 local。
    tool_source: str
    # 工具分类，比如 task_query / task_write。
    tool_category: str
    # 是否实际执行了工具。
    tool_executed: bool
    # 是否属于危险写操作。
    dangerous: bool
    # 是否需要用户确认。
    requires_confirmation: bool
    # Agent 最终回复给用户的文本。
    response_message: str
    # 轨迹创建时间。
    created_at: datetime


class AgentDebugRunRequest(BaseModel):
    # 调试运行 Agent 时前端提交的请求体。
    message: str
    # 默认使用 debug-web，方便和真实飞书会话区分。
    chat_id: str = "debug-web"


class AgentDebugRunResponse(BaseModel):
    # 调试运行 Agent 后返回给前端的结果。
    handled: bool
    # 本次识别到的意图名称。
    intent_name: str
    # Agent 回复内容。
    message: str
    # 对应的 trace 记录 ID；没有写入时可能为空。
    trace_id: int | None = None
