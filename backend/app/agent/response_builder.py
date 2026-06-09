from app.agent.schemas import AgentExecutedAction, AgentIntent, AgentResponse, ProjectProgressSummary
from app.agent.tools import filter_tasks, summarize_project_progress
from app.schemas.task_result import ActionItemListItem


# 把 AgentIntent 和工具执行结果组装成统一的 AgentResponse。
# graph.py 的最后一个节点会调用这里，orchestrator.py 再根据 AgentResponse 决定发什么飞书卡片。
def build_agent_response_from_intent(
    intent: AgentIntent | None,
    action_items: list[ActionItemListItem],
    tool_items: list[ActionItemListItem] | None = None,
    progress_summary: ProjectProgressSummary | None = None,
    executed_action: AgentExecutedAction | None = None,
) -> AgentResponse:
    # 没有识别出意图，表示 Agent 不处理这句话。
    if not intent:
        return AgentResponse(handled=False, message="No supported agent intent found.")

    # 帮助意图：只告诉上层“帮助准备好了”，真正发帮助卡片在 orchestrator.py。
    if intent.name == "help":
        return AgentResponse(
            handled=True,
            intent=intent,
            message="ActionBridge help is ready.",
        )

    # 创建任务属于危险写操作。
    # 这里不会真的创建，只返回“准备创建”，后续 orchestrator 会请求用户确认。
    if intent.name == "create_task":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"Ready to create task: {intent.filters['title']}.",
        )

    # 创建任务信息不完整，例如缺负责人或截止时间。
    # 上层会据此发送补充信息提示。
    if intent.name == "create_task_missing_info":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"Task information is incomplete: {intent.filters['missing_fields']}.",
        )

    # 用户想修改任务，但任务引用不清楚。
    # 比如“把那个任务改成测试同学”，系统不知道“那个任务”是哪一个。
    if intent.name == "clarify_task_reference":
        return AgentResponse(
            handled=True,
            intent=intent,
            message="我理解你想修改任务，但还缺少任务编号。请告诉我任务编号，例如：把 12 号任务负责人改成测试同学。",
        )

    # 修改截止时间属于危险写操作。
    # 这里仅返回准备修改，真正修改需要用户确认后走 confirm_update_task_deadline。
    if intent.name == "update_task_deadline":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"Ready to update task {intent.filters['action_item_id']} deadline.",
        )

    # 修改负责人也属于危险写操作，需要确认。
    if intent.name == "update_task_owner":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"Ready to update task {intent.filters['action_item_id']} owner.",
        )

    # 修改任务状态通常可以直接执行。
    # executed_action 里可能带有已经更新后的行动项。
    if intent.name == "update_task_status":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=_build_update_message(intent.filters),
            executed_action=executed_action,
        )

    # 用户确认后创建任务，工具已经执行，executed_action 保存执行结果。
    if intent.name == "confirm_create_task":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"Task created: {intent.filters['title']}.",
            executed_action=executed_action,
        )

    # 用户确认后修改截止时间。
    if intent.name == "confirm_update_task_deadline":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"Task {intent.filters['action_item_id']} deadline updated.",
            executed_action=executed_action,
        )

    # 用户确认后修改负责人。
    if intent.name == "confirm_update_task_owner":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"Task {intent.filters['action_item_id']} owner updated.",
            executed_action=executed_action,
        )

    # 项目进度总结。
    # 如果工具节点已经生成 progress_summary 就直接用；否则这里兜底计算一次。
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

    # 查询任务。
    # 如果工具节点已经过滤出 tool_items 就直接用；否则这里兜底过滤一次。
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
    # 根据查询结果和过滤条件生成简短文本。
    # 飞书卡片正文主要由 feishu_service.py 构造，这里的 message 更多用于 trace/API 返回。
    if not items:
        return "No matching tasks found."

    # 根据不同过滤条件生成更具体的提示。
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
    # 构造任务状态更新的简短描述。
    # 把系统内部状态值转成更适合英文 message 的短语。
    status_label = {
        "pending": "pending",
        "in_progress": "in progress",
        "completed": "completed",
        "failed": "at risk",
    }.get(filters.get("status", ""), filters.get("status", ""))
    return f"Ready to update task {filters.get('action_item_id')} to {status_label}."


def _build_progress_message(total_count: int, keyword: str) -> str:
    # 构造项目进度总结的简短描述。
    if total_count == 0:
        return f"No tasks found for {keyword}."
    return f"Generated project progress summary for {keyword}."
