from pydantic import BaseModel


class FeishuSendResponse(BaseModel):
    # 发送飞书消息接口的响应结构。
    meeting_id: int
    # 发送状态，比如 sent / failed。
    status: str
    # 给前端或调用方看的说明文本。
    message: str
