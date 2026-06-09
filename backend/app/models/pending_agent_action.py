from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class PendingAgentAction(Base):
    # 待确认 Agent 动作表：保存用户确认前暂存的写操作。
    __tablename__ = "pending_agent_actions"

    # 主键 ID。
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # 飞书会话 ID，用来知道这条待确认动作属于哪个聊天。
    chat_id: Mapped[str] = mapped_column(String(128), index=True)
    # 动作类型，比如 create_task / update_task_deadline / update_task_owner。
    action_type: Mapped[str] = mapped_column(String(64))
    # 动作参数，当前以 JSON 字符串保存。
    payload_json: Mapped[str] = mapped_column(Text)
    # 当前状态，比如 pending / confirmed / cancelled / expired。
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # 创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    # 过期时间，超过后不应再执行。
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
