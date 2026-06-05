from app.models.action_item import ActionItem
from app.models.meeting import Meeting
from app.services.project_channel_service import (
    bind_project_channel,
    resolve_project_channel_for_action_item,
    sync_completed_action_item_to_project_channel,
)


def test_bind_project_channel_allows_one_group_to_bind_multiple_projects(db_session) -> None:
    first = bind_project_channel(db_session, "website", "oc_group")
    second = bind_project_channel(db_session, "mobile", "oc_group")

    assert first.receive_id == "oc_group"
    assert second.receive_id == "oc_group"
    assert first.project_keyword == "website"
    assert second.project_keyword == "mobile"


def test_resolve_project_channel_matches_meeting_or_task_keyword(db_session) -> None:
    meeting = Meeting(title="website launch sync", raw_transcript="raw", summary="summary", decisions="[]")
    db_session.add(meeting)
    db_session.flush()
    action_item = ActionItem(
        meeting_id=meeting.id,
        title="fix mobile nav",
        owner_name="frontend",
        deadline="Friday",
        status="pending",
    )
    db_session.add(action_item)
    db_session.commit()
    bind_project_channel(db_session, "website", "oc_website")

    channel = resolve_project_channel_for_action_item(db_session, action_item.id)

    assert channel is not None
    assert channel.receive_id == "oc_website"


def test_sync_completed_action_item_skips_source_group_to_avoid_duplicate(db_session) -> None:
    meeting = Meeting(title="website launch sync", raw_transcript="raw", summary="summary", decisions="[]")
    db_session.add(meeting)
    db_session.flush()
    action_item = ActionItem(
        meeting_id=meeting.id,
        title="fix mobile nav",
        owner_name="frontend",
        deadline="Friday",
        status="completed",
    )
    db_session.add(action_item)
    db_session.commit()
    bind_project_channel(db_session, "website", "oc_website")
    sent: list[str | None] = []

    receive_id = sync_completed_action_item_to_project_channel(
        db_session,
        action_item_id=action_item.id,
        title=action_item.title,
        owner_name=action_item.owner_name,
        source_receive_id="oc_website",
        send_completed_notice=lambda *_args, receive_id=None, **_kwargs: sent.append(receive_id),
    )

    assert receive_id is None
    assert sent == []
