from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class FollowUpLog(Base):
    # 跟进提醒日志表：记录某个行动项是否已经发送过提醒，避免重复提醒。
    __tablename__ = "follow_up_logs"

    # 主键 ID。
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # 所属会议 ID。
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), index=True)
    # 被提醒的行动项 ID。
    action_item_id: Mapped[int] = mapped_column(ForeignKey("action_items.id"), index=True)
    # 提醒类型，比如 due_today / overdue。
    reminder_type: Mapped[str] = mapped_column(String(32))
    # 发送状态，默认 sent。
    status: Mapped[str] = mapped_column(String(32), default="sent")
    # 提醒发送时间。
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
