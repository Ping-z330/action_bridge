from datetime import datetime

from pydantic import BaseModel


class ActionItemListItem(BaseModel):
    # 任务列表接口的单条行动项结构，包含会议上下文和到期状态。
    id: int
    # 所属会议 ID。
    meeting_id: int
    # 所属会议标题，前端列表展示时不用再额外查会议。
    meeting_title: str
    title: str
    owner_name: str
    # 原始截止时间文本。
    deadline: str
    # 规范化日期/时间。
    deadline_date: str
    deadline_time: str
    status: str
    # 系统计算出的到期状态，比如 due_today / overdue / upcoming / unknown。
    due_status: str
    # 给用户看的中文到期状态文案。
    due_status_label: str
    created_at: datetime
