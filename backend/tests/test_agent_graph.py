"""Tests for the ReAct-based Agent graph.

Tests are split into two categories:
  1. Confirmed action tests — test write operations that bypass LLM
  2. ReAct loop tests — test the LLM-based agent by mocking _call_llm_with_tools
"""

import json

from app.agent.confirmed_intents import build_confirmed_action_intent
from app.agent.graph import run_agent_graph, run_confirmed_agent_action
from app.agent.schemas import AgentResponse
from app.schemas.meeting import MeetingCreate
from app.services.meeting_service import create_meeting_with_actions


# ── Helpers ─────────────────────────────────────────────────

def _make_mock_llm_response(content: str = "", tool_calls: list | None = None):
    """Build a mock LLM response dict matching _call_llm_with_tools output."""
    result: dict = {"content": content}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


def _make_tool_call(name: str, args: dict, call_id: str = "call_1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args),
        },
    }


# ── Confirmed action tests (no LLM needed) ─────────────────

def test_confirmed_action_intent_mapping() -> None:
    intent = build_confirmed_action_intent(
        "update_task_owner",
        {"action_item_id": "1", "new_owner_name": "QA"},
    )
    assert intent.name == "confirm_update_task_owner"
    assert intent.filters["action_item_id"] == "1"
    assert build_confirmed_action_intent("unsupported", {}) is None


def test_confirmed_create_task(db_session) -> None:
    response = run_confirmed_agent_action(
        db_session,
        "create_task",
        {
            "title": "Prepare launch checklist",
            "owner_name": "PM",
            "deadline": "2026-06-05 18:00",
        },
    )
    assert response.handled is True
    assert response.intent_name == "confirm_create_task"
    assert response.executed_action is not None
    assert response.executed_action.status == "created"
    assert response.executed_action.target_title == "Prepare launch checklist"
    assert response.executed_action.target_owner_name == "PM"
    assert response.executed_action.action_item is not None
    assert response.executed_action.action_item.deadline_date == "2026-06-05"


def test_confirmed_deadline_update(db_session) -> None:
    meeting = create_meeting_with_actions(
        db_session,
        MeetingCreate(
            title="Deadline test",
            transcript="Action: Backend verifies webhook retry.",
        ),
    )
    aid = meeting.action_items[0].id

    response = run_confirmed_agent_action(
        db_session,
        "update_task_deadline",
        {
            "action_item_id": str(aid),
            "title": "Backend verifies webhook retry.",
            "old_deadline": "pending",
            "new_deadline": "2026-06-05 18:00",
        },
    )
    assert response.handled is True
    assert response.executed_action is not None
    assert response.executed_action.status == "updated"
    assert response.executed_action.action_item.deadline_date == "2026-06-05"


def test_confirmed_owner_update(db_session) -> None:
    meeting = create_meeting_with_actions(
        db_session,
        MeetingCreate(
            title="Owner test",
            transcript="Action: Backend verifies webhook retry.",
        ),
    )
    aid = meeting.action_items[0].id

    response = run_confirmed_agent_action(
        db_session,
        "update_task_owner",
        {
            "action_item_id": str(aid),
            "title": "Backend verifies webhook retry.",
            "old_owner_name": "Backend",
            "new_owner_name": "QA",
        },
    )
    assert response.handled is True
    assert response.executed_action is not None
    assert response.executed_action.status == "updated"
    assert response.executed_action.action_item.owner_name == "QA"


def test_confirmed_unknown_action(db_session) -> None:
    response = run_confirmed_agent_action(db_session, "unknown_action", {})
    assert response.handled is False


# ── ReAct loop tests (mocked LLM) ──────────────────────────

def test_react_agent_handles_query_with_mocked_llm(db_session, monkeypatch) -> None:
    """Agent should return handled=True when LLM calls a tool then responds."""
    import app.agent.graph as agent_graph

    call_count = [0]

    def mock_llm(messages, tools):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call: LLM decides to call query_tasks
            return _make_mock_llm_response(
                tool_calls=[
                    _make_tool_call("query_tasks", {"open_only": "true"}),
                ],
            )
        else:
            # Second call: LLM has the results, gives final answer
            return _make_mock_llm_response(content="找到 2 个任务。")

    monkeypatch.setattr(agent_graph, "_call_llm_with_tools", mock_llm)

    create_meeting_with_actions(
        db_session,
        MeetingCreate(
            title="Query test",
            transcript="Action: Fix bug. Action: Update docs.",
        ),
    )

    response = run_agent_graph(db_session, "查看所有任务", chat_id="test")
    assert response.handled is True
    # intent_name is set from the last tool execution
    assert response.intent_name == "query_tasks"
    assert len(response.items) >= 1  # at least 1 item returned


def test_react_agent_steps_are_recorded(db_session, monkeypatch) -> None:
    """ReAct steps should be recorded in AgentResponse.steps."""
    import app.agent.graph as agent_graph

    def mock_llm(messages, tools):
        return _make_mock_llm_response(
            content="任务已更新。",
            tool_calls=[
                _make_tool_call("update_task_status", {"action_item_id": 1, "target_status": "completed"}),
            ],
        )

    monkeypatch.setattr(agent_graph, "_call_llm_with_tools", mock_llm)

    response = run_agent_graph(db_session, "第一个任务完成了", chat_id="test")
    assert response.handled is True
    assert len(response.steps) > 0
    assert response.steps[0].tool_name == "update_task_status"


def test_react_agent_no_tool_calls_returns_directly(db_session, monkeypatch) -> None:
    """When LLM returns no tool_calls, agent should return directly."""
    import app.agent.graph as agent_graph

    def mock_llm(messages, tools):
        return _make_mock_llm_response(content="你好！有什么可以帮你的？")

    monkeypatch.setattr(agent_graph, "_call_llm_with_tools", mock_llm)

    response = run_agent_graph(db_session, "你好", chat_id="test")
    assert response.handled is True
    assert response.message == "你好！有什么可以帮你的？"
    assert len(response.steps) == 0


def test_react_agent_llm_failure_returns_unhandled(db_session, monkeypatch) -> None:
    """When LLM call fails, agent should return handled=False gracefully."""
    import app.agent.graph as agent_graph

    def mock_llm(messages, tools):
        return None  # Simulate API failure

    monkeypatch.setattr(agent_graph, "_call_llm_with_tools", mock_llm)

    response = run_agent_graph(db_session, "查看任务", chat_id="test")
    assert response.handled is False
    assert "不可用" in response.message
