from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class AgentTraceLog(Base):
    # Agent 调试轨迹表：记录一次 Agent 处理消息时的关键过程。
    __tablename__ = "agent_trace_logs"

    # 主键 ID。
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # 飞书会话 ID 或调试会话 ID。
    chat_id: Mapped[str] = mapped_column(String(128), default="")
    # 来源，比如 agent / debug。
    source: Mapped[str] = mapped_column(String(32), default="agent")
    # 用户原始消息。
    message: Mapped[str] = mapped_column(Text, default="")
    # 经过记忆替换或清理后的消息。
    normalized_message: Mapped[str] = mapped_column(Text, default="")
    # 识别出的意图名称。
    intent_name: Mapped[str] = mapped_column(String(64), default="unhandled")
    # 意图参数，当前以 JSON 字符串保存。
    intent_filters_json: Mapped[str] = mapped_column(Text, default="{}")
    # 实际调用的工具名。
    tool_name: Mapped[str] = mapped_column(String(64), default="")
    # 工具来源，比如 local。
    tool_source: Mapped[str] = mapped_column(String(32), default="")
    # 工具分类，比如 task_query / task_write。
    tool_category: Mapped[str] = mapped_column(String(64), default="")
    # 是否真的执行了工具。
    tool_executed: Mapped[bool] = mapped_column(Boolean, default=False)
    # 工具是否属于危险写操作。
    dangerous: Mapped[bool] = mapped_column(Boolean, default=False)
    # 工具执行前是否需要用户确认。
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    # Agent 返回给用户的消息。
    response_message: Mapped[str] = mapped_column(Text, default="")
    # 轨迹创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
