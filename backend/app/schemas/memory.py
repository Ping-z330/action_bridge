from datetime import datetime

from pydantic import BaseModel


class MemoryAliasItem(BaseModel):
    # 记忆别名接口返回的单条记录。
    id: int
    # 用户定义的简称。
    alias: str
    # 简称对应的真实项目名或对象名。
    target: str
    # 记忆类型，当前主要是 alias。
    memory_type: str
    # 创建时间。
    created_at: datetime
