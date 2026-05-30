from pydantic import BaseModel, Field


class ActionItemUpdate(BaseModel):
    owner_name: str = Field(min_length=1, max_length=120)
    deadline: str = Field(min_length=1, max_length=32)
    status: str = Field(pattern="^(pending|in_progress|completed|failed)$")


class FeishuCardCallbackResponse(BaseModel):
    status: str
    message: str
    action_item_id: int | None = None
