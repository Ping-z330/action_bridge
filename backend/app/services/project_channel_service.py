from sqlalchemy.orm import Session
from typing import Callable, Any

from app.core.time import utc_now
from app.models.action_item import ActionItem
from app.models.meeting import Meeting
from app.models.project_channel import ProjectChannel


def bind_project_channel(db: Session, project_keyword: str, receive_id: str) -> ProjectChannel:
    keyword = project_keyword.strip()
    target_receive_id = receive_id.strip()
    existing = db.query(ProjectChannel).filter(ProjectChannel.project_keyword == keyword).first()
    if existing:
        existing.receive_id = target_receive_id
        existing.updated_at = utc_now()
        db.commit()
        db.refresh(existing)
        return existing

    item = ProjectChannel(project_keyword=keyword, receive_id=target_receive_id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_project_channels(db: Session) -> list[ProjectChannel]:
    return db.query(ProjectChannel).order_by(ProjectChannel.project_keyword.asc()).all()


def resolve_project_channel_for_action_item(db: Session, action_item_id: int) -> ProjectChannel | None:
    row = (
        db.query(ActionItem, Meeting)
        .join(Meeting, ActionItem.meeting_id == Meeting.id)
        .filter(ActionItem.id == action_item_id)
        .first()
    )
    if not row:
        return None

    action_item, meeting = row
    searchable_text = f"{meeting.title} {meeting.summary} {action_item.title}".lower()
    channels = sorted(list_project_channels(db), key=lambda item: len(item.project_keyword), reverse=True)
    for channel in channels:
        if channel.project_keyword.lower() in searchable_text:
            return channel
    return None


def sync_completed_action_item_to_project_channel(
    db: Session,
    *,
    action_item_id: int,
    title: str,
    owner_name: str,
    source_receive_id: str | None,
    send_completed_notice: Callable[..., Any],
) -> str | None:
    channel = resolve_project_channel_for_action_item(db, action_item_id)
    if not channel or channel.receive_id == source_receive_id:
        return None

    send_completed_notice(
        action_item_id,
        title,
        owner_name,
        receive_id=channel.receive_id,
    )
    return channel.receive_id
