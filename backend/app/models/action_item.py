from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.session import Base


class ActionItem(Base):
    # 行动项表：保存从会议纪要中提取出来、需要跟进的具体任务。
    __tablename__ = "action_items"

    # 主键 ID，也是飞书命令里常用的任务编号。
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # 所属会议 ID，关联 meetings 表。
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"))
    # 行动项标题，也就是具体要做什么。
    title: Mapped[str] = mapped_column(String(255))
    # 负责人姓名，未识别到时默认为 Unassigned。
    owner_name: Mapped[str] = mapped_column(String(120), default="Unassigned")
    # 原始截止时间文本，比如“明天下午”或“TBD”。
    deadline: Mapped[str] = mapped_column(String(32), default="TBD")
    # 规范化后的日期，格式通常是 YYYY-MM-DD，方便判断今天到期/逾期。
    deadline_date: Mapped[str] = mapped_column(String(10), default="")
    # 规范化后的时间，格式通常是 HH:mm。
    deadline_time: Mapped[str] = mapped_column(String(5), default="")
    # 任务状态：pending / in_progress / completed / failed 等。
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # 记录创建时间，使用项目统一的 UTC 时间函数。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    # ORM 关系：一个行动项属于一个会议。
    meeting = relationship("Meeting", back_populates="action_items")
