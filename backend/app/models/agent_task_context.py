from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class AgentTaskContext(Base):
    # Agent 任务上下文表：保存某个会话最近展示过的任务列表。
    __tablename__ = "agent_task_contexts"

    # 主键 ID。
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # 会话 ID，每个会话只保留一份最近任务上下文。
    chat_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    # 最近任务 ID 列表，当前以 JSON 字符串保存。
    item_ids_json: Mapped[str] = mapped_column(Text)
    # 创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    # 更新时间；上下文刷新时会更新它。
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
