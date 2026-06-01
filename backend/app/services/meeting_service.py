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


AGENT_CREATED_MEETING_TITLE = "飞书临时任务"


def create_meeting_with_actions(db: Session, payload: MeetingCreate) -> MeetingResponse:
    meeting = Meeting(
        title=payload.title,
        raw_transcript=payload.transcript,
        summary="Parsing in progress",
        decisions="[]",
    )
    db.add(meeting)
    db.flush()

    task = Task(
        meeting_id=meeting.id,
        task_type="meeting_parse",
        status="running",
        input_json=json.dumps({"title": payload.title, "transcript": payload.transcript}),
        output_json="{}",
    )
    db.add(task)

    try:
        parsed = parse_transcript(payload.title, payload.transcript)
        meeting.summary = parsed.summary
        meeting.decisions = json.dumps(parsed.decisions)

        for item in parsed.action_items:
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
        task.status = "failed"
        db.commit()
        raise

    return get_meeting_by_id(db, meeting.id)


def list_meetings(db: Session) -> list[MeetingListItem]:
    meetings = db.query(Meeting).options(selectinload(Meeting.action_items)).order_by(Meeting.created_at.desc()).all()
    results: list[MeetingListItem] = []

    for meeting in meetings:
        action_count = len(meeting.action_items)
        completed_count = len([item for item in meeting.action_items if item.status == "completed"])
        pending_count = action_count - completed_count
        due_today_count = len(
            [
                item
                for item in meeting.action_items
                if item.status != "completed"
                and _get_action_item_due_status(item) == "due_today"
            ]
        )
        overdue_count = len(
            [
                item
                for item in meeting.action_items
                if item.status != "completed"
                and _get_action_item_due_status(item) == "overdue"
            ]
        )
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
    rows = (
        db.query(ActionItem, Meeting.title.label("meeting_title"))
        .join(Meeting, ActionItem.meeting_id == Meeting.id)
        .order_by(ActionItem.created_at.desc())
        .all()
    )

    results: list[ActionItemListItem] = []
    for action_item, meeting_title in rows:
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
    meeting = _get_or_create_agent_created_meeting(db)
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

    return next(item for item in list_action_items(db) if item.id == action_item.id)


def _get_or_create_agent_created_meeting(db: Session) -> Meeting:
    meeting = db.query(Meeting).filter(Meeting.title == AGENT_CREATED_MEETING_TITLE).first()
    if meeting:
        return meeting

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
    meeting = (
        db.query(Meeting)
        .options(selectinload(Meeting.action_items))
        .filter(Meeting.id == meeting_id)
        .first()
    )
    if not meeting:
        return None

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
    meeting = get_meeting_by_id(db, meeting_id)
    if not meeting:
        return None

    try:
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
    meeting = get_meeting_by_id(db, meeting_id)
    if not meeting:
        return None

    try:
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
    action_item = db.query(ActionItem).filter(ActionItem.id == action_item_id).first()
    if not action_item:
        return None

    action_item.owner_name = payload.owner_name
    action_item.deadline_date = payload.deadline_date
    action_item.deadline_time = payload.deadline_time
    action_item.deadline = build_deadline_text(payload.deadline_date, payload.deadline_time, payload.deadline)
    action_item.status = payload.status
    db.commit()

    return get_meeting_by_id(db, action_item.meeting_id)


def complete_action_item(db: Session, action_item_id: int) -> ActionItem | None:
    action_item = db.query(ActionItem).filter(ActionItem.id == action_item_id).first()
    if not action_item:
        return None

    action_item.status = "completed"
    db.commit()
    db.refresh(action_item)
    return action_item


def update_action_item_status(db: Session, action_item_id: int, status: str) -> ActionItemListItem | None:
    action_item = db.query(ActionItem).filter(ActionItem.id == action_item_id).first()
    if not action_item:
        return None

    action_item.status = status
    db.commit()

    return next((item for item in list_action_items(db) if item.id == action_item_id), None)


def update_action_item_deadline(db: Session, action_item_id: int, deadline: str) -> ActionItemListItem | None:
    action_item = db.query(ActionItem).filter(ActionItem.id == action_item_id).first()
    if not action_item:
        return None

    deadline_date, deadline_time = normalize_deadline(deadline, action_item.created_at)
    action_item.deadline = build_deadline_text(deadline_date, deadline_time, deadline)
    action_item.deadline_date = deadline_date
    action_item.deadline_time = deadline_time
    db.commit()

    return next((item for item in list_action_items(db) if item.id == action_item_id), None)


def _get_action_item_due_status(action_item: ActionItem) -> str:
    if action_item.deadline_date:
        return get_due_status_from_date(action_item.deadline_date, action_item.status)
    return get_due_status(action_item.deadline, action_item.created_at)
