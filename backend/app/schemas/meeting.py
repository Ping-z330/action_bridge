from datetime import datetime

from pydantic import BaseModel, Field


class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    transcript: str = Field(min_length=1)


class ActionItemResponse(BaseModel):
    id: int
    title: str
    owner_name: str
    deadline: str
    deadline_date: str = ""
    deadline_time: str = ""
    status: str

    model_config = {"from_attributes": True}


class MeetingResponse(BaseModel):
    id: int
    title: str
    raw_transcript: str
    summary: str
    decisions: list[str]
    created_at: datetime
    action_items: list[ActionItemResponse]

    model_config = {"from_attributes": True}


class MeetingListItem(BaseModel):
    id: int
    title: str
    summary: str
    created_at: datetime
    action_count: int = 0
    pending_count: int = 0
    completed_count: int = 0
    due_today_count: int = 0
    overdue_count: int = 0
    closure_status: str = "pending"

    model_config = {"from_attributes": True}
