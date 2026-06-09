from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class FeishuEventLog(Base):
    # 飞书事件日志表：用于事件去重和处理状态记录。
    __tablename__ = "feishu_event_logs"

    # 主键 ID。
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # 飞书事件唯一标识；唯一索引用来防止重复处理同一个事件。
    event_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    # 命令类型，比如 meeting / done / tasks / agent 等。
    command_type: Mapped[str] = mapped_column(String(32), default="unknown")
    # 处理状态，比如 processing / finished / failed。
    status: Mapped[str] = mapped_column(String(32), default="processing")
    # 事件日志创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
