from pydantic import BaseModel


class FeishuSendResponse(BaseModel):
    meeting_id: int
    status: str
    message: str
