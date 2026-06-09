from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.session import Base


class Meeting(Base):
    # 会议表：保存一次会议的原始文本、总结、决策和关联任务。
    __tablename__ = "meetings"

    # 主键 ID。
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # 会议标题。
    title: Mapped[str] = mapped_column(String(255))
    # 用户提交的原始会议转录文本。
    raw_transcript: Mapped[str] = mapped_column(Text)
    # 解析服务生成的会议总结。
    summary: Mapped[str] = mapped_column(Text)
    # 决策列表，当前以 JSON 字符串形式保存。
    decisions: Mapped[str] = mapped_column(Text, default="[]")
    # 会议记录创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    # ORM 关系：一个会议可以有多个行动项。
    action_items = relationship("ActionItem", back_populates="meeting", cascade="all, delete-orphan")
    # ORM 关系：一个会议可以有多个后台处理任务记录。
    tasks = relationship("Task", back_populates="meeting", cascade="all, delete-orphan")
