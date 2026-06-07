import json

from sqlalchemy.orm import Session, selectinload

from app.models.action_item import ActionItem
from app.models.meeting import Meeting
from app.models.task import Task
from app.core.time import ensure_utc
from app.schemas.action_item import ActionItemUpdate
from app.schemas.meeting import MeetingCreate, MeetingListItem, MeetingResponse
from app.schemas.task import FeishuSendResponse
from app.schemas.task_result import ActionItemListItem
from app.services.deadline_service import build_deadline_text, normalize_deadline
from app.services.due_status_service import get_due_status, get_due_status_from_date, get_due_status_label
from app.services.feishu_service import FeishuDeliveryError, send_follow_up_summary, send_meeting_summary
from app.services.parser_service import parse_transcript


# Agent 从飞书自然语言里直接创建任务时，需要挂到一个“临时会议”下面。
# 这样所有行动项仍然都有 meeting_id，不会脱离现有数据结构。
AGENT_CREATED_MEETING_TITLE = "飞书临时任务"


# 创建会议，并把会议记录解析成摘要、决策和行动项。
# 这是首页“AI 生成会议纪要”和飞书 /meeting 命令最终会调用的核心函数。
def create_meeting_with_actions(db: Session, payload: MeetingCreate) -> MeetingResponse:
    # 先创建 Meeting 主记录。此时还没有解析结果，所以 summary 先写临时状态。
    meeting = Meeting(
        title=payload.title,
        raw_transcript=payload.transcript,
        summary="Parsing in progress",
        decisions="[]",
    )
    db.add(meeting)

    # flush 会把 meeting.id 写出来，但还不提交事务。
    # 后面创建 Task 和 ActionItem 时需要用这个 meeting.id。
    db.flush()

    # Task 表用来记录“会议解析”这个后台任务的输入、输出和状态。
    task = Task(
        meeting_id=meeting.id,
        task_type="meeting_parse",
        status="running",
        input_json=json.dumps({"title": payload.title, "transcript": payload.transcript}),
        output_json="{}",
    )
    db.add(task)

    try:
        # 调用 parser_service.py。它会优先用 LLM，失败或未配置时走规则解析。
        parsed = parse_transcript(payload.title, payload.transcript)
        meeting.summary = parsed.summary
        meeting.decisions = json.dumps(parsed.decisions)

        # 把解析出来的每个行动项保存到 action_items 表。
        for item in parsed.action_items:
            # deadline 是原始文本；deadline_date/deadline_time 是标准化后的日期和时间。
            deadline_date, deadline_time = normalize_deadline(item.deadline, meeting.created_at)
            db.add(
                ActionItem(
                    meeting_id=meeting.id,
                    title=item.title,
                    owner_name=item.owner_name,
                    deadline=item.deadline,
                    deadline_date=deadline_date,
                    deadline_time=deadline_time,
                    status=item.status,
                )
            )

        # 解析成功后，把 Task 状态改成 completed，并保存解析输出。
        task.status = "completed"
        task.output_json = json.dumps(
            {
                "summary": parsed.summary,
                "decisions": parsed.decisions,
                "action_items": [item.__dict__ for item in parsed.action_items],
            }
        )
        db.commit()
    except Exception:
        # 如果解析或保存失败，至少把 Task 标记成 failed，方便后续排查。
        task.status = "failed"
        db.commit()
        raise

    # 重新查询一次，返回带 action_items 的完整会议响应。
    return get_meeting_by_id(db, meeting.id)


def list_meetings(db: Session) -> list[MeetingListItem]:
    # 查询会议列表，并为每个会议计算任务统计数据。
    # 前端首页、历史页会用这个结果。
    # selectinload 会一次性预加载 action_items，避免循环里反复查数据库。
    meetings = db.query(Meeting).options(selectinload(Meeting.action_items)).order_by(Meeting.created_at.desc()).all()
    results: list[MeetingListItem] = []

    for meeting in meetings:
        # 统计这个会议产生了多少行动项，以及完成/未完成情况。
        action_count = len(meeting.action_items)
        completed_count = len([item for item in meeting.action_items if item.status == "completed"])
        pending_count = action_count - completed_count

        # 统计今日到期的未完成任务数量。
        due_today_count = len(
            [
                item
                for item in meeting.action_items
                if item.status != "completed"
                and _get_action_item_due_status(item) == "due_today"
            ]
        )

        # 统计已逾期的未完成任务数量。
        overdue_count = len(
            [
                item
                for item in meeting.action_items
                if item.status != "completed"
                and _get_action_item_due_status(item) == "overdue"
            ]
        )

        # 如果有行动项且全部完成，就认为这个会议执行闭环。
        closure_status = "closed" if action_count > 0 and pending_count == 0 else "open"

        results.append(
            MeetingListItem(
                id=meeting.id,
                title=meeting.title,
                summary=meeting.summary,
                created_at=ensure_utc(meeting.created_at),
                action_count=action_count,
                pending_count=pending_count,
                completed_count=completed_count,
                due_today_count=due_today_count,
                overdue_count=overdue_count,
                closure_status=closure_status,
            )
        )

    return results


def list_action_items(db: Session) -> list[ActionItemListItem]:
    # 查询所有行动项，并带上来源会议标题和到期风险状态。
    # 任务看板、飞书 /tasks、Agent 查询任务都会用这个函数。
    # join Meeting 是为了给每个行动项补充 meeting_title。
    rows = (
        db.query(ActionItem, Meeting.title.label("meeting_title"))
        .join(Meeting, ActionItem.meeting_id == Meeting.id)
        .order_by(ActionItem.created_at.desc())
        .all()
    )

    results: list[ActionItemListItem] = []
    for action_item, meeting_title in rows:
        # 已完成任务的 due_status 固定为 completed；未完成任务再判断到期风险。
        due_status = (
            "completed"
            if action_item.status == "completed"
            else _get_action_item_due_status(action_item)
        )
        results.append(
            ActionItemListItem(
                id=action_item.id,
                meeting_id=action_item.meeting_id,
                meeting_title=meeting_title,
                title=action_item.title,
                owner_name=action_item.owner_name,
                deadline=action_item.deadline,
                deadline_date=action_item.deadline_date or "",
                deadline_time=action_item.deadline_time or "",
                status=action_item.status,
                due_status=due_status,
                due_status_label=get_due_status_label(due_status),
                created_at=ensure_utc(action_item.created_at),
            )
        )

    return results


def create_action_item_from_agent(
    db: Session,
    title: str,
    owner_name: str,
    deadline: str,
) -> ActionItemListItem:
    # Agent 确认创建任务后调用这里。
    # 这个任务不是来自正式会议，所以挂到“飞书临时任务”这个特殊会议下。
    meeting = _get_or_create_agent_created_meeting(db)

    # 把自然语言截止时间转成标准日期/时间。
    deadline_date, deadline_time = normalize_deadline(deadline, meeting.created_at)
    action_item = ActionItem(
        meeting_id=meeting.id,
        title=title,
        owner_name=owner_name,
        deadline=build_deadline_text(deadline_date, deadline_time, deadline),
        deadline_date=deadline_date,
        deadline_time=deadline_time,
        status="pending",
    )
    db.add(action_item)

    # 记录一条 Task，表示这个行动项是由 Agent 创建的。
    db.add(
        Task(
            meeting_id=meeting.id,
            task_type="agent_create_action_item",
            status="completed",
            input_json=json.dumps(
                {
                    "title": title,
                    "owner_name": owner_name,
                    "deadline": deadline,
                },
                ensure_ascii=False,
            ),
            output_json="{}",
        )
    )
    db.commit()

    # 返回统一的 ActionItemListItem 结构，方便上层直接发飞书卡片。
    return next(item for item in list_action_items(db) if item.id == action_item.id)


def _get_or_create_agent_created_meeting(db: Session) -> Meeting:
    # 获取或创建 Agent 专用的“飞书临时任务”会议。
    meeting = db.query(Meeting).filter(Meeting.title == AGENT_CREATED_MEETING_TITLE).first()
    if meeting:
        return meeting

    # 如果还没有临时会议，就新建一个，用来承载飞书自然语言创建的任务。
    meeting = Meeting(
        title=AGENT_CREATED_MEETING_TITLE,
        raw_transcript="由飞书自然语言消息创建的临时行动项。",
        summary="这里汇总从飞书自然语言对话中直接创建的行动项。",
        decisions="[]",
    )
    db.add(meeting)
    db.flush()
    return meeting


def get_meeting_by_id(db: Session, meeting_id: int) -> MeetingResponse | None:
    # 根据会议 ID 查询会议详情。
    # 返回值是给 API/前端使用的 MeetingResponse，而不是数据库模型本身。
    meeting = (
        db.query(Meeting)
        .options(selectinload(Meeting.action_items))
        .filter(Meeting.id == meeting_id)
        .first()
    )
    if not meeting:
        return None

    # meeting.decisions 在数据库里是 JSON 字符串，这里转回 list[str]。
    return MeetingResponse(
        id=meeting.id,
        title=meeting.title,
        raw_transcript=meeting.raw_transcript,
        summary=meeting.summary,
        decisions=json.loads(meeting.decisions or "[]"),
        created_at=ensure_utc(meeting.created_at),
        action_items=meeting.action_items,
    )


def send_meeting_to_feishu(db: Session, meeting_id: int) -> FeishuSendResponse | None:
    # 把指定会议的摘要卡片发送到飞书。
    meeting = get_meeting_by_id(db, meeting_id)
    if not meeting:
        return None

    try:
        # 真实的飞书卡片构造和发送在 feishu_service.py。
        message = send_meeting_summary(meeting)
        return FeishuSendResponse(
            meeting_id=meeting.id,
            status="sent",
            message=message,
        )
    except FeishuDeliveryError as exc:
        return FeishuSendResponse(
            meeting_id=meeting.id,
            status="failed",
            message=str(exc),
        )


def send_follow_up_to_feishu(db: Session, meeting_id: int) -> FeishuSendResponse | None:
    # 把指定会议的未完成任务跟进提醒发送到飞书。
    meeting = get_meeting_by_id(db, meeting_id)
    if not meeting:
        return None

    try:
        # 真实的跟进卡片构造和发送在 feishu_service.py。
        message = send_follow_up_summary(meeting)
        return FeishuSendResponse(
            meeting_id=meeting.id,
            status="sent",
            message=message,
        )
    except FeishuDeliveryError as exc:
        return FeishuSendResponse(
            meeting_id=meeting.id,
            status="failed",
            message=str(exc),
        )


def update_action_item(db: Session, action_item_id: int, payload: ActionItemUpdate) -> MeetingResponse | None:
    # 前端会议详情页保存行动项时调用。
    # 可以同时更新负责人、截止日期、截止时间和状态。
    action_item = db.query(ActionItem).filter(ActionItem.id == action_item_id).first()
    if not action_item:
        return None

    # deadline_date/deadline_time 是结构化字段；deadline 是给用户看的合成文本。
    action_item.owner_name = payload.owner_name
    action_item.deadline_date = payload.deadline_date
    action_item.deadline_time = payload.deadline_time
    action_item.deadline = build_deadline_text(payload.deadline_date, payload.deadline_time, payload.deadline)
    action_item.status = payload.status
    db.commit()

    # 返回所属会议的最新详情，让前端能刷新整块会议数据。
    return get_meeting_by_id(db, action_item.meeting_id)


def complete_action_item(db: Session, action_item_id: int) -> ActionItem | None:
    # 把行动项标记为 completed。
    # 飞书 /done 命令和一些跟进回复会用它。
    action_item = db.query(ActionItem).filter(ActionItem.id == action_item_id).first()
    if not action_item:
        return None

    action_item.status = "completed"
    db.commit()
    db.refresh(action_item)
    return action_item


def update_action_item_status(db: Session, action_item_id: int, status: str) -> ActionItemListItem | None:
    # 只更新行动项状态，例如 pending、in_progress、completed、failed。
    action_item = db.query(ActionItem).filter(ActionItem.id == action_item_id).first()
    if not action_item:
        return None

    action_item.status = status
    db.commit()

    # 返回列表页统一使用的结构，包含 meeting_title 和 due_status。
    return next((item for item in list_action_items(db) if item.id == action_item_id), None)


def update_action_item_deadline(db: Session, action_item_id: int, deadline: str) -> ActionItemListItem | None:
    # 更新行动项截止时间。
    # deadline 可以是自然语言文本，normalize_deadline 会尽量转成日期/时间。
    action_item = db.query(ActionItem).filter(ActionItem.id == action_item_id).first()
    if not action_item:
        return None

    deadline_date, deadline_time = normalize_deadline(deadline, action_item.created_at)
    action_item.deadline = build_deadline_text(deadline_date, deadline_time, deadline)
    action_item.deadline_date = deadline_date
    action_item.deadline_time = deadline_time
    db.commit()

    return next((item for item in list_action_items(db) if item.id == action_item_id), None)


def update_action_item_owner(db: Session, action_item_id: int, owner_name: str) -> ActionItemListItem | None:
    # 更新行动项负责人。
    action_item = db.query(ActionItem).filter(ActionItem.id == action_item_id).first()
    if not action_item:
        return None

    action_item.owner_name = owner_name
    db.commit()

    return next((item for item in list_action_items(db) if item.id == action_item_id), None)


def _get_action_item_due_status(action_item: ActionItem) -> str:
    # 计算行动项的到期状态。
    # 优先使用结构化 deadline_date；如果没有，再退回到原始 deadline 文本判断。
    if action_item.deadline_date:
        return get_due_status_from_date(action_item.deadline_date, action_item.status)
    return get_due_status(action_item.deadline, action_item.created_at)
