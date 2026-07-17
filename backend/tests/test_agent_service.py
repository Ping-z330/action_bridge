"""Tests for personal assistant (replaces old agent_service tests).

The old detect_intent / handle_agent_message functions have been removed.
Agent logic is now handled by the ReAct loop in graph.py.
"""

import pytest

from app.agent.personal_assistant import build_personal_assistant_response
from app.agent.schemas import AgentResponse


def test_build_personal_assistant_reply_with_steps() -> None:
    from app.agent.schemas import AgentStep
    response = AgentResponse(
        handled=True,
        message="",
        steps=[
            AgentStep(tool_name="query_tasks", tool_args={"owner": "张三"}, tool_result="找到 2 个任务"),
        ],
        intent_name="query_tasks",
        intent_filters={"owner": "张三"},
    )
    reply = build_personal_assistant_response(response, "张三")
    assert "张三" in reply
    assert "query_tasks" in reply


def test_build_personal_assistant_reply_unhandled() -> None:
    response = AgentResponse(handled=False, message="")
    reply = build_personal_assistant_response(response, "李四")
    assert "暂时不太理解" in reply


def test_build_personal_assistant_reply_uses_llm_message() -> None:
    response = AgentResponse(handled=True, message="你已完成 3 个任务，还有 2 个待处理。")
    reply = build_personal_assistant_response(response, "张三")
    assert "已处理您的请求" not in reply
    assert "3 个任务" in reply


@pytest.mark.skip(reason="Old detect_intent-based tests removed")
def test_detect_intent_legacy() -> None:
    pass
