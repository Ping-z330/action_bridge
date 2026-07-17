"""Member model: a person assigned to a project.

Tracks when each member last updated their tasks.
Used by the central Agent to detect inactivity.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    chat_id: Mapped[str] = mapped_column(String(128), default="")     # Feishu/chat user ID for DM routing
    role: Mapped[str] = mapped_column(String(32), default="member")   # "owner" | "member"
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
