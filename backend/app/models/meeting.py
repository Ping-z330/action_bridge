from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.session import Base

# Meeting 模型定义了会议的数据库表结构，包括会议的标题、原始转录文本、总结、决策、创建时间等字段，以及与行动项和任务的关系；这个模型用于在数据库中存储和管理会议相关的数据。
class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    raw_transcript: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    decisions: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    action_items = relationship("ActionItem", back_populates="meeting", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="meeting", cascade="all, delete-orphan")
