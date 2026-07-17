from dataclasses import dataclass, field

from app.schemas.task_result import ActionItemListItem


# ── Agent 基础结构 ──────────────────────────────────────────

@dataclass(frozen=True)
class ProjectProgressSummary:
    """项目进度总结，summarize_project 工具会生成它。"""
    keyword: str
    total_count: int
    completed_count: int
    in_progress_count: int
    pending_count: int
    failed_count: int
    overdue_count: int
    due_today_count: int
    completion_rate: float
    conclusion: str
    items: list[ActionItemListItem] = field(default_factory=list)


@dataclass
class AgentStep:
    """ReAct 循环中单个步骤的记录：LLM 选了哪个工具、传了什么参数、执行结果是什么。"""
    thought: str = ""
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: str = ""
    tool_error: str = ""

    def to_dict(self) -> dict:
        return {
            "thought": self.thought,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "tool_result": self.tool_result,
            "tool_error": self.tool_error,
        }


@dataclass
class AgentExecutedAction:
    """工具执行后的统一结果，写操作工具会返回它。"""
    action_type: str
    status: str
    action_item_id: int | None = None
    target_title: str | None = None
    target_status: str | None = None
    target_deadline: str | None = None
    target_owner_name: str | None = None
    action_item: ActionItemListItem | None = None


# ── mRNA 协议结构 ──────────────────────────────────────────

@dataclass
class mRNAEnvelope:
    """Agent 间通信协议：个人助手 → 中央 Agent 的结构化消息。"""
    sender_agent_id: str       # "personal:zhangsan"
    receiver_agent_id: str     # "central:project-1"
    message_type: str          # "task_update" | "status_report" | "alert_ack"
    payload: dict              # 结构化数据
    timestamp: str = ""


# ── 风险评估结构 ────────────────────────────────────────────

@dataclass
class RiskAssessment:
    """单一风险项。"""
    task_id: int
    task_title: str
    risk_type: str             # "overdue" | "no_update" | "blocked" | "dependency_chain"
    severity: str              # "critical" | "warning" | "info"
    description: str
    impacted_task_ids: list[int] = field(default_factory=list)


@dataclass
class ProjectRiskReport:
    """项目的完整风险评估报告。"""
    project_id: int
    risk_score: int            # 0–100，数字越大风险越高
    total_tasks: int
    overdue_count: int
    no_update_count: int
    blocked_count: int
    risks: list[RiskAssessment] = field(default_factory=list)
    conclusion: str = ""


# ── Agent 统一响应 ──────────────────────────────────────────

# ── 向后兼容：旧版 AgentIntent（渐进式重构用）─────────────
# Phase 1 完成后逐步移除 service.py / response_builder.py / task_reference_resolver.py 中的依赖

@dataclass(frozen=True)
class AgentIntent:
    """[已废弃] 旧版意图标签。ReAct 模式下不再使用，保留用于渐进式重构。"""
    name: str
    filters: dict[str, str] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """Agent 执行完一轮后的统一响应。

    相比旧版去掉了 AgentIntent 字段 —— ReAct 模式下不再有"意图标签"，
    取而代之的是 steps（ReAct 步骤链）和 tool_calls（LLM 自主选择的工具调用）。
    """
    handled: bool
    message: str = ""

    # ReAct 步骤链：每一步记录 LLM 的 thought、tool 选择、执行结果。
    steps: list[AgentStep] = field(default_factory=list)

    # 查询任务时返回的任务列表。
    items: list[ActionItemListItem] = field(default_factory=list)

    # 项目总结时返回的进度结构。
    progress_summary: ProjectProgressSummary | None = None

    # 写操作执行后的结果。
    executed_action: AgentExecutedAction | None = None

    # 风险评估报告。
    risk_report: ProjectRiskReport | None = None

    # 兼容旧版 orchestrator 的 intent 字段，渐进式重构用。
    intent_name: str = ""
    intent_filters: dict[str, str] = field(default_factory=dict)
