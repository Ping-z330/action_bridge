from pydantic import BaseModel


class FollowUpRunItem(BaseModel):
    # 单个会议的跟进提醒执行结果。
    meeting_id: int
    meeting_title: str
    # 本次为该会议发送了多少条提醒。
    reminder_count: int
    # 提醒类型列表，比如 due_today / overdue。
    reminder_types: list[str]
    # 该会议提醒执行状态。
    status: str
    # 给调用方看的说明。
    message: str


class FollowUpRunResponse(BaseModel):
    # 批量执行跟进提醒后的汇总响应。
    # 扫描过的会议数量。
    scanned_meetings: int
    # 符合提醒条件的候选行动项数量。
    total_candidates: int
    # 实际发送成功的提醒数量。
    total_sent: int
    # 每个会议的提醒执行结果。
    results: list[FollowUpRunItem]
