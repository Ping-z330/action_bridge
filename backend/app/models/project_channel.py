from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class ProjectChannel(Base):
    # 项目群绑定表：把项目关键词绑定到飞书群，用于跨群同步项目进展。
    __tablename__ = "project_channels"

    # 主键 ID。
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # 项目关键词，唯一；系统用它匹配会议标题或任务内容。
    project_keyword: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    # 飞书群或接收方 ID。
    receive_id: Mapped[str] = mapped_column(String(128), index=True)
    # 创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    # 更新时间；重新绑定时会更新。
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
