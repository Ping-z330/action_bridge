from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class FeishuEventLog(Base):
    __tablename__ = "feishu_event_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    event_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    command_type: Mapped[str] = mapped_column(String(32), default="unknown")
    status: Mapped[str] = mapped_column(String(32), default="processing")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
