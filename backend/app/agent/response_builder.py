from app.agent.schemas import AgentExecutedAction, AgentIntent, AgentResponse, ProjectProgressSummary
from app.agent.tools import filter_tasks, summarize_project_progress
from app.schemas.task_result import ActionItemListItem


def build_agent_response_from_intent(
    intent: AgentIntent | None,
    action_items: list[ActionItemListItem],
    tool_items: list[ActionItemListItem] | None = None,
    progress_summary: ProjectProgressSummary | None = None,
    executed_action: AgentExecutedAction | None = None,
) -> AgentResponse:
    if not intent:
        return AgentResponse(handled=False, message="No supported agent intent found.")

    if intent.name == "help":
        return AgentResponse(
            handled=True,
            intent=intent,
            message="ActionBridge help is ready.",
        )

    if intent.name == "create_task":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"Ready to create task: {intent.filters['title']}.",
        )

    if intent.name == "create_task_missing_info":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"Task information is incomplete: {intent.filters['missing_fields']}.",
        )

    if intent.name == "clarify_task_reference":
        return AgentResponse(
            handled=True,
            intent=intent,
            message="我理解你想修改任务，但还缺少任务编号。请告诉我任务编号，例如：把 12 号任务负责人改成测试同学。",
        )

    if intent.name == "update_task_deadline":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"Ready to update task {intent.filters['action_item_id']} deadline.",
        )

    if intent.name == "update_task_owner":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"Ready to update task {intent.filters['action_item_id']} owner.",
        )

    if intent.name == "update_task_status":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=_build_update_message(intent.filters),
            executed_action=executed_action,
        )

    if intent.name == "confirm_create_task":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"Task created: {intent.filters['title']}.",
            executed_action=executed_action,
        )

    if intent.name == "confirm_update_task_deadline":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"Task {intent.filters['action_item_id']} deadline updated.",
            executed_action=executed_action,
        )

    if intent.name == "confirm_update_task_owner":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"Task {intent.filters['action_item_id']} owner updated.",
            executed_action=executed_action,
        )

    if intent.name == "summarize_project":
        keyword = intent.filters["keyword"]
        summary = progress_summary or summarize_project_progress(action_items, keyword)
        return AgentResponse(
            handled=True,
            intent=intent,
            items=summary.items,
            progress_summary=summary,
            message=_build_progress_message(summary.total_count, keyword),
        )

    if intent.name == "query_tasks":
        items = tool_items if tool_items is not None else filter_tasks(action_items, intent.filters)
        return AgentResponse(
            handled=True,
            intent=intent,
            items=items,
            message=_build_query_message(items, intent.filters),
        )

    return AgentResponse(handled=False, message="Unsupported agent intent.")


def _build_query_message(items: list[ActionItemListItem], filters: dict[str, str]) -> str:
    if not items:
        return "No matching tasks found."

    if filters.get("due_status") == "due_today":
        return f"Found {len(items)} tasks due today."
    if filters.get("due_status") == "overdue":
        return f"Found {len(items)} overdue tasks."
    if filters.get("owner"):
        return f"Found {len(items)} tasks owned by {filters['owner']}."
    if filters.get("keyword"):
        return f"Found {len(items)} tasks related to {filters['keyword']}."
    return f"Found {len(items)} matching tasks."


def _build_update_message(filters: dict[str, str]) -> str:
    status_label = {
        "pending": "pending",
        "in_progress": "in progress",
        "completed": "completed",
        "failed": "at risk",
    }.get(filters.get("status", ""), filters.get("status", ""))
    return f"Ready to update task {filters.get('action_item_id')} to {status_label}."


def _build_progress_message(total_count: int, keyword: str) -> str:
    if total_count == 0:
        return f"No tasks found for {keyword}."
    return f"Generated project progress summary for {keyword}."
