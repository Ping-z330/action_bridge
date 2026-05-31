from app.agent.schemas import ProjectProgressSummary
from app.schemas.task_result import ActionItemListItem


OPEN_STATUSES = {"pending", "in_progress", "failed"}


def filter_tasks(items: list[ActionItemListItem], filters: dict[str, str]) -> list[ActionItemListItem]:
    results = items

    if filters.get("open_only") == "true":
        results = [item for item in results if item.status in OPEN_STATUSES]

    due_status = filters.get("due_status")
    if due_status:
        results = [item for item in results if item.due_status == due_status]

    status = filters.get("status")
    if status:
        results = [item for item in results if item.status == status]

    owner = filters.get("owner")
    if owner:
        results = [item for item in results if owner.lower() in item.owner_name.lower()]

    keyword = filters.get("keyword")
    if keyword:
        normalized_keyword = keyword.lower()
        results = [
            item
            for item in results
            if normalized_keyword in item.meeting_title.lower()
            or normalized_keyword in item.title.lower()
        ]

    return results


def summarize_project_progress(items: list[ActionItemListItem], keyword: str) -> ProjectProgressSummary:
    matched_items = filter_tasks(items, {"keyword": keyword})
    total_count = len(matched_items)
    completed_count = len([item for item in matched_items if item.status == "completed"])
    in_progress_count = len([item for item in matched_items if item.status == "in_progress"])
    pending_count = len([item for item in matched_items if item.status == "pending"])
    failed_count = len([item for item in matched_items if item.status == "failed"])
    overdue_count = len([item for item in matched_items if item.due_status == "overdue"])
    due_today_count = len([item for item in matched_items if item.due_status == "due_today"])
    completion_rate = round(completed_count / total_count * 100, 1) if total_count else 0.0

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


def _build_progress_conclusion(
    total_count: int,
    completion_rate: float,
    failed_count: int,
    overdue_count: int,
    due_today_count: int,
) -> str:
    if total_count == 0:
        return "没有找到相关任务，建议确认项目关键词是否准确。"
    if failed_count or overdue_count:
        return "当前项目存在风险，建议优先处理有风险和逾期任务。"
    if due_today_count:
        return "当前项目有任务今日到期，建议当天完成确认。"
    if completion_rate == 100:
        return "当前项目任务已全部完成，可以进入归档或复盘。"
    return "当前项目整体推进中，建议持续跟进未完成任务。"
