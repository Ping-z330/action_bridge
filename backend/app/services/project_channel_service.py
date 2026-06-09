from sqlalchemy.orm import Session
from typing import Callable, Any

from app.core.time import utc_now
from app.models.action_item import ActionItem
from app.models.meeting import Meeting
from app.models.project_channel import ProjectChannel


def bind_project_channel(db: Session, project_keyword: str, receive_id: str) -> ProjectChannel:
    # 绑定项目关键词到飞书群。
    # 后续任务完成时，如果任务/会议命中这个关键词，就可以同步通知到对应群。
    keyword = project_keyword.strip()
    target_receive_id = receive_id.strip()
    existing = db.query(ProjectChannel).filter(ProjectChannel.project_keyword == keyword).first()
    if existing:
        # 已有绑定时更新群 ID，相当于重新绑定。
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
    # 列出所有项目群绑定，按项目关键词排序。
    return db.query(ProjectChannel).order_by(ProjectChannel.project_keyword.asc()).all()


def resolve_project_channel_for_action_item(db: Session, action_item_id: int) -> ProjectChannel | None:
    # 根据行动项内容和所属会议内容，判断它应该同步到哪个项目群。
    row = (
        db.query(ActionItem, Meeting)
        .join(Meeting, ActionItem.meeting_id == Meeting.id)
        .filter(ActionItem.id == action_item_id)
        .first()
    )
    if not row:
        return None

    action_item, meeting = row
    # 搜索范围包括会议标题、会议总结、行动项标题。
    searchable_text = f"{meeting.title} {meeting.summary} {action_item.title}".lower()
    # 关键词越长越具体，优先匹配长关键词。
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
    # 当某个任务完成时，尝试同步一条完成通知到绑定的项目群。
    channel = resolve_project_channel_for_action_item(db, action_item_id)
    if not channel or channel.receive_id == source_receive_id:
        # 没有命中项目群，或目标群就是当前消息来源群，都不重复发送。
        return None

    send_completed_notice(
        action_item_id,
        title,
        owner_name,
        receive_id=channel.receive_id,
    )
    return channel.receive_id
