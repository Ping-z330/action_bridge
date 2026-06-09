from dataclasses import dataclass, field

from app.schemas.task_result import ActionItemListItem


# 项目进度总结结构。
# summarize_project 工具会生成它，feishu_service.py 会用它构造项目进度卡片。
@dataclass(frozen=True)
class ProjectProgressSummary:
    # 项目关键词，例如“官网改版”。
    keyword: str

    # 任务总数和各种状态数量。
    total_count: int
    completed_count: int
    in_progress_count: int
    pending_count: int
    failed_count: int

    # 到期风险统计。
    overdue_count: int
    due_today_count: int

    # 完成率，通常是 completed_count / total_count * 100。
    completion_rate: float

    # 面向用户的进度判断文案。
    conclusion: str

    # 参与本次项目总结的重点任务列表。
    items: list[ActionItemListItem] = field(default_factory=list)


# Agent 识别出来的“意图”。
# 例如 query_tasks、create_task、update_task_owner、summarize_project。
@dataclass(frozen=True)
class AgentIntent:
    # 意图名称。
    name: str

    # 意图参数，例如 action_item_id、owner_name、deadline、keyword。
    filters: dict[str, str] = field(default_factory=dict)


# Agent 工具实际执行后的结果。
# 写操作工具会返回它，例如创建任务、更新状态、修改负责人。
@dataclass(frozen=True)
class AgentExecutedAction:
    # 执行动作类型，例如 create_task、update_task_status。
    action_type: str

    # 执行状态，例如 completed、failed。
    status: str

    # 被操作的行动项 ID，创建失败或无目标时可能为空。
    action_item_id: int | None = None

    # 下面这些 target_* 字段记录本次动作想改成什么。
    target_title: str | None = None
    target_status: str | None = None
    target_deadline: str | None = None
    target_owner_name: str | None = None

    # 执行后返回的最新行动项详情。
    action_item: ActionItemListItem | None = None


# Agent 执行完一轮后的统一响应。
# graph.py 返回它，orchestrator.py 根据它决定怎么回复飞书。
@dataclass(frozen=True)
class AgentResponse:
    # handled=False 表示 Agent 不处理这条消息。
    handled: bool

    # 本次识别到的意图。
    intent: AgentIntent | None = None

    # 简短响应文案，主要用于 trace、debug 和部分提示。
    message: str = ""

    # 查询任务时返回的任务列表。
    items: list[ActionItemListItem] = field(default_factory=list)

    # 项目总结时返回的进度结构。
    progress_summary: ProjectProgressSummary | None = None

    # 写操作执行后的结果。
    executed_action: AgentExecutedAction | None = None
