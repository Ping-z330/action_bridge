from datetime import datetime

from pydantic import BaseModel


class ActionItemListItem(BaseModel):
    id: int
    meeting_id: int
    meeting_title: str
    title: str
    owner_name: str
    deadline: str
    deadline_date: str
    deadline_time: str
    status: str
    due_status: str
    due_status_label: str
    created_at: datetime
