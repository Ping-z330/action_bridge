from dataclasses import dataclass, field

from app.schemas.task_result import ActionItemListItem


@dataclass(frozen=True)
class ProjectProgressSummary:
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


@dataclass(frozen=True)
class AgentIntent:
    name: str
    filters: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResponse:
    handled: bool
    intent: AgentIntent | None = None
    message: str = ""
    items: list[ActionItemListItem] = field(default_factory=list)
    progress_summary: ProjectProgressSummary | None = None
