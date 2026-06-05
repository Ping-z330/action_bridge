from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class ProjectChannel(Base):
    __tablename__ = "project_channels"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_keyword: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    receive_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
