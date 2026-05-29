from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class FollowUpLog(Base):
    __tablename__ = "follow_up_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), index=True)
    action_item_id: Mapped[int] = mapped_column(ForeignKey("action_items.id"), index=True)
    reminder_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="sent")
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
