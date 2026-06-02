from app.agent.graph import run_agent_graph, run_agent_graph_state
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
