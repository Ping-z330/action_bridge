from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class MemoryAlias(Base):
    # 记忆别名表：保存用户定义的简称和真实项目/对象名称之间的映射。
    __tablename__ = "memory_aliases"

    # 主键 ID。
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # 用户输入的别名，比如“官网项目”。
    alias: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    # 别名指向的真实名称。
    target: Mapped[str] = mapped_column(String(255))
    # 记忆类型，当前默认 alias，后续可扩展其他记忆类型。
    memory_type: Mapped[str] = mapped_column(String(32), default="alias")
    # 创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
