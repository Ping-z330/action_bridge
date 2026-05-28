import json

from sqlalchemy.orm import Session, selectinload

from app.models.action_item import ActionItem
from app.models.meeting import Meeting
from app.models.task import Task
from app.schemas.meeting import MeetingCreate, MeetingListItem, MeetingResponse
from app.schemas.task import FeishuSendResponse
from app.services.parser_service import parse_transcript


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
            db.add(
                ActionItem(
                    meeting_id=meeting.id,
                    title=item.title,
                    owner_name=item.owner_name,
                    deadline=item.deadline,
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
    meetings = db.query(Meeting).order_by(Meeting.created_at.desc()).all()
    return [MeetingListItem.model_validate(meeting) for meeting in meetings]


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
        created_at=meeting.created_at,
        action_items=meeting.action_items,
    )


def send_meeting_to_feishu(db: Session, meeting_id: int) -> FeishuSendResponse | None:
    meeting = get_meeting_by_id(db, meeting_id)
    if not meeting:
        return None

    return FeishuSendResponse(
        meeting_id=meeting.id,
        status="queued",
        message=f"Meeting '{meeting.title}' prepared for Feishu delivery.",
    )
