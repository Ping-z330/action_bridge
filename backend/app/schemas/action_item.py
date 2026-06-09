from pydantic import BaseModel, Field


class ActionItemUpdate(BaseModel):
    # 更新行动项接口的请求体：前端 PATCH 行动项时会提交这些字段。
    # Field 里的长度和 pattern 是输入校验，避免写入明显异常的数据。
    owner_name: str = Field(min_length=1, max_length=120)
    deadline: str = Field(min_length=1, max_length=32)
    # 规范化日期，通常是 YYYY-MM-DD；为空表示未解析出明确日期。
    deadline_date: str = Field(default="", max_length=10)
    # 规范化时间，通常是 HH:mm；为空表示未解析出明确时间。
    deadline_time: str = Field(default="", max_length=5)
    # 只允许这四种任务状态。
    status: str = Field(pattern="^(pending|in_progress|completed|failed)$")


class FeishuCardCallbackResponse(BaseModel):
    # 飞书卡片按钮回调后的统一响应。
    status: str
    message: str
    # 被操作的行动项 ID；有些失败场景可能没有。
    action_item_id: int | None = None
