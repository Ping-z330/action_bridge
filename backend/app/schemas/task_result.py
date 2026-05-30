from datetime import datetime

from pydantic import BaseModel


class ActionItemListItem(BaseModel):
    id: int
    meeting_id: int
    meeting_title: str
    title: str
    owner_name: str
    deadline: str
    status: str
    created_at: datetime
