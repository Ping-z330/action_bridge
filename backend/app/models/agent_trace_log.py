from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class AgentTraceLog(Base):
    __tablename__ = "agent_trace_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    chat_id: Mapped[str] = mapped_column(String(128), default="")
    source: Mapped[str] = mapped_column(String(32), default="agent")
    message: Mapped[str] = mapped_column(Text, default="")
    normalized_message: Mapped[str] = mapped_column(Text, default="")
    intent_name: Mapped[str] = mapped_column(String(64), default="unhandled")
    intent_filters_json: Mapped[str] = mapped_column(Text, default="{}")
    tool_name: Mapped[str] = mapped_column(String(64), default="")
    tool_source: Mapped[str] = mapped_column(String(32), default="")
    tool_category: Mapped[str] = mapped_column(String(64), default="")
    tool_executed: Mapped[bool] = mapped_column(Boolean, default=False)
    dangerous: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    response_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
