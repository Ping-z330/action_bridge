from datetime import datetime

from pydantic import BaseModel


class MemoryAliasItem(BaseModel):
    id: int
    alias: str
    target: str
    memory_type: str
    created_at: datetime
