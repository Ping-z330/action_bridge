from datetime import datetime

from pydantic import BaseModel, Field


class MeetingCreate(BaseModel):
    # 创建会议接口的请求体：用户提交标题和会议转录文本。
    title: str = Field(min_length=1, max_length=255)
    transcript: str = Field(min_length=1)


class ActionItemResponse(BaseModel):
    # 会议详情里返回的行动项结构。
    id: int
    title: str
    owner_name: str
    # 原始截止时间文本。
    deadline: str
    # 规范化日期/时间，方便前端展示和筛选。
    deadline_date: str = ""
    deadline_time: str = ""
    status: str

    # 允许 Pydantic 从 SQLAlchemy ORM 对象直接读取字段。
    model_config = {"from_attributes": True}


class MeetingResponse(BaseModel):
    # 会议详情接口返回结构。
    id: int
    title: str
    raw_transcript: str
    summary: str
    # decisions 在数据库里是 JSON 字符串，返回时转成 list[str]。
    decisions: list[str]
    created_at: datetime
    action_items: list[ActionItemResponse]

    # 允许从 ORM 对象构造响应。
    model_config = {"from_attributes": True}


class MeetingListItem(BaseModel):
    # 会议列表里的单条记录，比详情更轻量，但带一些统计字段。
    id: int
    title: str
    summary: str
    created_at: datetime
    # 该会议下行动项总数。
    action_count: int = 0
    # 未开始/待处理数量。
    pending_count: int = 0
    # 已完成数量。
    completed_count: int = 0
    # 今天到期数量。
    due_today_count: int = 0
    # 已逾期数量。
    overdue_count: int = 0
    # 会议闭环状态，比如 pending / completed / at_risk。
    closure_status: str = "pending"

    # 允许从 ORM 对象构造响应。
    model_config = {"from_attributes": True}
