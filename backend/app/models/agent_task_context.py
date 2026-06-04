from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class AgentTaskContext(Base):
    __tablename__ = "agent_task_contexts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    chat_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    item_ids_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
