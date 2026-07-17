from sqlalchemy.orm import Session

from app.agent.schemas import (
    AgentExecutedAction,
    ProjectProgressSummary,
    ProjectRiskReport,
    RiskAssessment,
)
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


# ── 新增：项目场景工具 ──────────────────────────────────────

def analyze_project_risk(
    db: Session,
    project_id: int,
    items: list[ActionItemListItem] | None = None,
) -> ProjectRiskReport:
    """分析项目风险：扫描逾期任务、依赖链影响、长期未更新任务。

    当前 MVP 阶段基于 action_items 的 due_status 做分析。
    Phase 2 接入项目依赖图后会完整计算下游影响。
    """
    # 如果没有传入 items，从 list_action_items 获取
    if items is None:
        from app.services.meeting_service import list_action_items
        items = list_action_items(db)

    open_items = [i for i in items if i.status != "completed"]
    total = len(open_items)
    overdue = [i for i in open_items if i.due_status == "overdue"]
    no_update: list[ActionItemListItem] = []  # Phase 2 接入 last_updated_at 后填充
    blocked = [i for i in open_items if i.status in ("failed", "blocked")]

    risks: list[RiskAssessment] = []

    # 逾期任务风险
    for item in overdue:
        risks.append(RiskAssessment(
            task_id=item.id,
            task_title=item.title,
            risk_type="overdue",
            severity="critical" if item.due_status == "overdue" else "warning",
            description=f"任务「{item.title}」已逾期，负责人: {item.owner_name}",
        ))

    # 阻塞任务风险
    for item in blocked:
        risks.append(RiskAssessment(
            task_id=item.id,
            task_title=item.title,
            risk_type="blocked",
            severity="warning",
            description=f"任务「{item.title}」标记为阻塞/有风险，负责人: {item.owner_name}",
        ))

    # 计算风险评分 (0-100)
    if total == 0:
        risk_score = 0
    else:
        overdue_weight = len(overdue) / total * 60
        blocked_weight = len(blocked) / total * 30
        no_update_weight = 0  # Phase 2 补充
        risk_score = min(100, int(overdue_weight + blocked_weight + no_update_weight))

    return ProjectRiskReport(
        project_id=project_id,
        risk_score=risk_score,
        total_tasks=total,
        overdue_count=len(overdue),
        no_update_count=len(no_update),
        blocked_count=len(blocked),
        risks=risks,
        conclusion=_build_risk_conclusion(risk_score, len(overdue), len(blocked)),
    )


def _build_risk_conclusion(risk_score: int, overdue_count: int, blocked_count: int) -> str:
    if risk_score == 0:
        return "当前项目状态健康，无风险项。"
    if risk_score >= 70:
        return f"🔴 高风险：{overdue_count} 个任务逾期，{blocked_count} 个阻塞。建议立即介入。"
    if risk_score >= 30:
        return f"🟡 中等风险：{overdue_count} 个任务逾期，{blocked_count} 个阻塞。建议关注。"
    return f"🟢 低风险：少量任务需要跟进。"


def query_member_activity(
    db: Session,
    project_id: int,
    member_name: str | None = None,
    items: list[ActionItemListItem] | None = None,
) -> dict:
    """查询项目成员活跃度。

    Phase 2 接入 member 表和 activity_log 后会返回更精确的数据。
    当前 MVP 基于 action_items 的状态统计。
    """
    if items is None:
        from app.services.meeting_service import list_action_items
        items = list_action_items(db)

    # 按负责人分组统计
    members: dict[str, dict] = {}
    for item in items:
        owner = item.owner_name
        if owner in ("Pending confirmation", "Unassigned", ""):
            continue
        if member_name and owner != member_name:
            continue
        if owner not in members:
            members[owner] = {
                "name": owner,
                "total": 0,
                "completed": 0,
                "in_progress": 0,
                "pending": 0,
                "failed": 0,
                "overdue": 0,
            }
        members[owner]["total"] += 1
        if item.status == "completed":
            members[owner]["completed"] += 1
        elif item.status == "in_progress":
            members[owner]["in_progress"] += 1
        elif item.status in ("failed", "blocked"):
            members[owner]["failed"] += 1
        else:
            members[owner]["pending"] += 1
        if item.due_status == "overdue":
            members[owner]["overdue"] += 1

    result = list(members.values())
    # 按活跃度（完成率）排序
    result.sort(key=lambda m: m["completed"] / max(m["total"], 1), reverse=True)
    return {"members": result, "total_members": len(result)}


def create_project_alert(
    db: Session,
    project_id: int,
    alert_type: str,
    severity: str,
    message: str,
) -> dict:
    """创建项目预警记录。

    Phase 2 会写入 alerts 表，当前返回结构化结果供上层发送飞书通知。
    """
    return {
        "status": "created",
        "project_id": project_id,
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
    }


def generate_progress_report(
    db: Session,
    project_id: int,
    items: list[ActionItemListItem] | None = None,
) -> dict:
    """生成项目综合进度报告：合并风险分析 + 成员活跃度 + 进度统计。"""
    if items is None:
        from app.services.meeting_service import list_action_items
        items = list_action_items(db)

    risk_report = analyze_project_risk(db, project_id, items=items)
    member_activity = query_member_activity(db, project_id, items=items)

    total = len(items)
    completed = len([i for i in items if i.status == "completed"])
    in_progress = len([i for i in items if i.status == "in_progress"])

    return {
        "project_id": project_id,
        "total_tasks": total,
        "completed_count": completed,
        "in_progress_count": in_progress,
        "completion_rate": round(completed / total * 100, 1) if total else 0.0,
        "risk_score": risk_report.risk_score,
        "risk_conclusion": risk_report.conclusion,
        "overdue_count": risk_report.overdue_count,
        "blocked_count": risk_report.blocked_count,
        "member_activity": member_activity,
        "top_risks": [
            {"task_id": r.task_id, "title": r.task_title, "severity": r.severity, "description": r.description}
            for r in risk_report.risks[:5]
        ],
    }
