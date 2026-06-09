from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.session import Base


class Task(Base):
    # 后台任务表：记录一次会议解析、发送等后台处理任务的输入输出和状态。
    __tablename__ = "tasks"

    # 主键 ID。
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # 所属会议 ID，关联 meetings 表。
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"))
    # 任务类型，比如解析会议、发送飞书等。
    task_type: Mapped[str] = mapped_column(String(64))
    # 处理状态，比如 pending / completed / failed。
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # 任务输入参数，当前用 JSON 字符串保存。
    input_json: Mapped[str] = mapped_column(Text)
    # 任务输出结果，当前用 JSON 字符串保存。
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    # 任务创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    # ORM 关系：一个后台任务属于一个会议。
    meeting = relationship("Meeting", back_populates="tasks")
