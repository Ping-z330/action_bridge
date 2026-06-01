from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class MemoryAlias(Base):
    __tablename__ = "memory_aliases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    alias: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    target: Mapped[str] = mapped_column(String(255))
    memory_type: Mapped[str] = mapped_column(String(32), default="alias")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
