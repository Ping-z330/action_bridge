from app.agent.confirmed_intents import build_confirmed_action_intent
from app.agent.graph import run_agent_graph, run_agent_graph_state, run_confirmed_agent_action
from app.schemas.meeting import MeetingCreate
from app.services.meeting_service import create_meeting_with_actions


def test_agent_graph_returns_agent_response(db_session) -> None:
    response = run_agent_graph(db_session, "help")

    assert response.handled is True
    assert response.intent is not None
    assert response.intent.name == "help"


def test_agent_graph_routes_detected_intent(db_session) -> None:
    state = run_agent_graph_state({"db": db_session, "message": "help"})

    assert state["intent_route"] == "help"
    assert state["agent_response"].handled is True


def test_agent_graph_executes_query_tool(db_session) -> None:
    meeting = create_meeting_with_actions(
        db_session,
        MeetingCreate(
            title="Query tool test",
            transcript="Action: Frontend fixes mobile navigation issue.",
        ),
    )

    state = run_agent_graph_state({"db": db_session, "message": "task"})

    assert state["intent_route"] == "query_tasks"
    assert [item.id for item in state["tool_items"]] == [meeting.action_items[0].id]
    assert state["agent_response"].items == state["tool_items"]


def test_confirmed_action_intent_mapping() -> None:
    intent = build_confirmed_action_intent(
        "update_task_owner",
        {"action_item_id": "1", "new_owner_name": "QA"},
    )

    assert intent.name == "confirm_update_task_owner"
    assert intent.filters["action_item_id"] == "1"
    assert build_confirmed_action_intent("unsupported", {}) is None


def test_agent_graph_executes_status_update_tool(db_session) -> None:
    meeting = create_meeting_with_actions(
        db_session,
        MeetingCreate(
            title="Status update tool test",
            transcript="Action: Backend verifies webhook retry logic.",
        ),
    )
    action_item_id = meeting.action_items[0].id

    state = run_agent_graph_state({"db": db_session, "message": f"#{action_item_id} done"})

    assert state["intent_route"] == "update_task_status"
    assert state["tool_executed"] is True
    assert state["executed_action"].status == "updated"
    assert state["executed_action"].action_item_id == action_item_id
    assert state["executed_action"].target_status == "completed"
    assert state["agent_response"].executed_action == state["executed_action"]
    assert state["executed_action"].action_item.status == "completed"


def test_agent_graph_executes_confirmed_create_task_tool(db_session) -> None:
    response = run_confirmed_agent_action(
        db_session,
        "create_task",
        {
            "title": "Prepare launch checklist",
            "owner_name": "PM",
            "deadline": "2026-06-05 18:00",
        },
    )

    assert response.intent.name == "confirm_create_task"
    assert response.executed_action.status == "created"
    assert response.executed_action.action_item_id
    assert response.executed_action.target_title == "Prepare launch checklist"
    assert response.executed_action.target_owner_name == "PM"
    assert response.executed_action.target_deadline == "2026-06-05 18:00"
    assert response.executed_action.action_item.title == "Prepare launch checklist"
    assert response.executed_action.action_item.owner_name == "PM"
    assert response.executed_action.action_item.deadline_date == "2026-06-05"
    assert response.executed_action.action_item.deadline_time == "18:00"


def test_agent_graph_executes_confirmed_deadline_update_tool(db_session) -> None:
    meeting = create_meeting_with_actions(
        db_session,
        MeetingCreate(
            title="Deadline update tool test",
            transcript="Action: Backend verifies webhook retry logic.",
        ),
    )
    action_item_id = meeting.action_items[0].id

    response = run_confirmed_agent_action(
        db_session,
        "update_task_deadline",
        {
            "action_item_id": str(action_item_id),
            "title": "Backend verifies webhook retry logic.",
            "old_deadline": "pending",
            "new_deadline": "2026-06-05 18:00",
        },
    )

    assert response.intent.name == "confirm_update_task_deadline"
    assert response.executed_action.status == "updated"
    assert response.executed_action.action_item_id == action_item_id
    assert response.executed_action.target_deadline == "2026-06-05 18:00"
    assert response.executed_action.action_item.deadline_date == "2026-06-05"
    assert response.executed_action.action_item.deadline_time == "18:00"


def test_agent_graph_executes_confirmed_owner_update_tool(db_session) -> None:
    meeting = create_meeting_with_actions(
        db_session,
        MeetingCreate(
            title="Owner update tool test",
            transcript="Action: Backend verifies webhook retry logic.",
        ),
    )
    action_item_id = meeting.action_items[0].id

    response = run_confirmed_agent_action(
        db_session,
        "update_task_owner",
        {
            "action_item_id": str(action_item_id),
            "title": "Backend verifies webhook retry logic.",
            "old_owner_name": "Backend",
            "new_owner_name": "QA",
        },
    )

    assert response.intent.name == "confirm_update_task_owner"
    assert response.executed_action.status == "updated"
    assert response.executed_action.action_item_id == action_item_id
    assert response.executed_action.target_owner_name == "QA"
    assert response.executed_action.action_item.owner_name == "QA"
