from pydantic import BaseModel


class FollowUpRunItem(BaseModel):
    meeting_id: int
    meeting_title: str
    reminder_count: int
    reminder_types: list[str]
    status: str
    message: str


class FollowUpRunResponse(BaseModel):
    scanned_meetings: int
    total_candidates: int
    total_sent: int
    results: list[FollowUpRunItem]
