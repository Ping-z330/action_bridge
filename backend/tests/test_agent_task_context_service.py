from app.schemas.meeting import MeetingCreate
from app.services.agent_task_context_service import load_recent_task_ids, save_recent_task_context
from app.services.meeting_service import create_meeting_with_actions, list_action_items


def test_save_and_load_recent_task_context(db_session) -> None:
    meeting = create_meeting_with_actions(
        db_session,
        MeetingCreate(
            title="Context memory test",
            transcript="Action: Frontend fixes login page.\nAction: QA verifies checkout flow.",
        ),
    )

    save_recent_task_context(db_session, "oc_test", list_action_items(db_session))

    assert load_recent_task_ids(db_session, "oc_test") == [
        meeting.action_items[0].id,
        meeting.action_items[1].id,
    ]
