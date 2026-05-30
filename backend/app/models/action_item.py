from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.session import Base


class ActionItem(Base):
    __tablename__ = "action_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"))
    title: Mapped[str] = mapped_column(String(255))
    owner_name: Mapped[str] = mapped_column(String(120), default="Unassigned")
    deadline: Mapped[str] = mapped_column(String(32), default="TBD")
    deadline_date: Mapped[str] = mapped_column(String(10), default="")
    deadline_time: Mapped[str] = mapped_column(String(5), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    meeting = relationship("Meeting", back_populates="action_items")
