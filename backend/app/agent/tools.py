from sqlalchemy.orm import Session

from app.agent.schemas import AgentExecutedAction, ProjectProgressSummary
from app.schemas.task_result import ActionItemListItem
from app.services.meeting_service import (
    create_action_item_from_agent,
    update_action_item_deadline,
    update_action_item_owner,
    update_action_item_status,
)


# 这些状态代表任务还没有结束，查询“未完成/待办”时会保留它们。
OPEN_STATUSES = {"pending", "in_progress", "failed"}


def filter_tasks(items: list[ActionItemListItem], filters: dict[str, str]) -> list[ActionItemListItem]:
    # 根据 filters 逐层过滤任务列表：是否未完成、到期状态、任务状态、负责人、关键词。
    results = items

    if filters.get("open_only") == "true":
        # open_only 表示只看还需要继续跟进的任务。
        results = [item for item in results if item.status in OPEN_STATUSES]

    due_status = filters.get("due_status")
    if due_status:
        # due_status 通常是 due_today / overdue 等截止时间分类。
        results = [item for item in results if item.due_status == due_status]

    status = filters.get("status")
    if status:
        # status 是任务本身状态，比如 pending / completed / failed。
        results = [item for item in results if item.status == status]

    owner = filters.get("owner")
    if owner:
        # 负责人使用包含匹配，方便用户只输入姓名的一部分。
        results = [item for item in results if owner.lower() in item.owner_name.lower()]

    keyword = filters.get("keyword")
    if keyword:
        # 项目关键词会同时匹配会议标题和任务标题。
        normalized_keyword = keyword.lower()
        results = [
            item
            for item in results
            if normalized_keyword in item.meeting_title.lower()
            or normalized_keyword in item.title.lower()
        ]

    return results


def summarize_project_progress(items: list[ActionItemListItem], keyword: str) -> ProjectProgressSummary:
    # 先按关键词找出相关任务，再统计完成率、风险数、逾期数等进度指标。
    matched_items = filter_tasks(items, {"keyword": keyword})
    total_count = len(matched_items)
    completed_count = len([item for item in matched_items if item.status == "completed"])
    in_progress_count = len([item for item in matched_items if item.status == "in_progress"])
    pending_count = len([item for item in matched_items if item.status == "pending"])
    failed_count = len([item for item in matched_items if item.status == "failed"])
    overdue_count = len([item for item in matched_items if item.due_status == "overdue"])
    due_today_count = len([item for item in matched_items if item.due_status == "due_today"])
    completion_rate = round(completed_count / total_count * 100, 1) if total_count else 0.0

    # ProjectProgressSummary 是 Agent 回复项目进度卡片时使用的结构化结果。
    return ProjectProgressSummary(
        keyword=keyword,
        total_count=total_count,
        completed_count=completed_count,
        in_progress_count=in_progress_count,
        pending_count=pending_count,
        failed_count=failed_count,
        overdue_count=overdue_count,
        due_today_count=due_today_count,
        completion_rate=completion_rate,
        conclusion=_build_progress_conclusion(
            total_count=total_count,
            completion_rate=completion_rate,
            failed_count=failed_count,
            overdue_count=overdue_count,
            due_today_count=due_today_count,
        ),
        items=matched_items,
    )


def execute_status_update_tool(
    db: Session,
    action_item_id: int,
    target_status: str,
) -> AgentExecutedAction:
    # 执行状态更新：真正写数据库，并把执行结果包装成 AgentExecutedAction。
    action_item = update_action_item_status(db, action_item_id, target_status)
    return AgentExecutedAction(
        action_type="update_task_status",
        status="updated" if action_item else "not_found",
        action_item_id=action_item_id,
        target_status=target_status,
        action_item=action_item,
    )


def execute_create_task_tool(
    db: Session,
    title: str,
    owner_name: str,
    deadline: str,
) -> AgentExecutedAction:
    # 执行新建任务：通常来自用户确认后的 Agent 操作。
    action_item = create_action_item_from_agent(
        db,
        title=title,
        owner_name=owner_name,
        deadline=deadline,
    )
    return AgentExecutedAction(
        action_type="create_task",
        status="created",
        action_item_id=action_item.id,
        target_title=title,
        target_deadline=deadline,
        target_owner_name=owner_name,
        action_item=action_item,
    )


def execute_deadline_update_tool(
    db: Session,
    action_item_id: int,
    target_deadline: str,
) -> AgentExecutedAction:
    # 执行截止时间更新；如果任务不存在，status 会返回 not_found。
    action_item = update_action_item_deadline(db, action_item_id, target_deadline)
    return AgentExecutedAction(
        action_type="update_task_deadline",
        status="updated" if action_item else "not_found",
        action_item_id=action_item_id,
        target_deadline=target_deadline,
        action_item=action_item,
    )


def execute_owner_update_tool(
    db: Session,
    action_item_id: int,
    target_owner_name: str,
) -> AgentExecutedAction:
    # 执行负责人更新；如果任务不存在，status 会返回 not_found。
    action_item = update_action_item_owner(db, action_item_id, target_owner_name)
    return AgentExecutedAction(
        action_type="update_task_owner",
        status="updated" if action_item else "not_found",
        action_item_id=action_item_id,
        target_owner_name=target_owner_name,
        action_item=action_item,
    )


def _build_progress_conclusion(
    total_count: int,
    completion_rate: float,
    failed_count: int,
    overdue_count: int,
    due_today_count: int,
) -> str:
    # 根据统计指标生成一句项目进度结论，优先提示风险和逾期问题。
    if total_count == 0:
        return "没有找到相关任务，建议确认项目关键词是否准确。"
    if failed_count or overdue_count:
        return "当前项目存在风险，建议优先处理有风险和逾期任务。"
    if due_today_count:
        return "当前项目有任务今日到期，建议当天完成确认。"
    if completion_rate == 100:
        return "当前项目任务已全部完成，可以进入归档或复盘。"
    return "当前项目整体推进中，建议持续跟进未完成任务。"
