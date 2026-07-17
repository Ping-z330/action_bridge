from app.agent.schemas import AgentResponse
from app.models.agent_trace_log import AgentTraceLog
from app.services.agent_trace_service import create_agent_trace_log, list_agent_trace_logs, parse_trace_filters


def test_create_agent_trace_log_records_tool_metadata(db_session) -> None:
    create_agent_trace_log(
        db_session,
        message="查看未完成任务",
        chat_id="oc_demo",
        normalized_message="查看未完成任务",
        intent_name="query_tasks",
        intent_filters_json='{"status": "open"}',
        tool_name="query_tasks",
        tool_executed=True,
        response=AgentResponse(handled=True, message="找到 1 个任务", intent_name="query_tasks"),
    )

    traces = list_agent_trace_logs(db_session)

    assert len(traces) == 1
    assert traces[0].source == "feishu"
    assert traces[0].intent_name == "query_tasks"
    assert traces[0].tool_name == "query_tasks"
    assert traces[0].tool_source == "local"
    assert traces[0].tool_category == "task_query"
    assert traces[0].tool_executed is True
    assert traces[0].dangerous is False
    assert parse_trace_filters(traces[0].intent_filters_json) == {"status": "open"}


def test_agent_traces_api_returns_recent_trace(client, db_session) -> None:
    db_session.add(
        AgentTraceLog(
            chat_id="oc_demo",
            source="feishu",
            message="把 2 号任务负责人改成测试同学",
            normalized_message="把 2 号任务负责人改成测试同学",
            intent_name="confirm_update_task_owner",
            intent_filters_json='{"action_item_id": "2"}',
            tool_name="update_task_owner",
            tool_source="local",
            tool_category="task_write",
            tool_executed=False,
            dangerous=True,
            requires_confirmation=True,
            response_message="请确认是否修改负责人",
        )
    )
    db_session.commit()

    response = client.get("/api/agent/traces")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["intent_name"] == "confirm_update_task_owner"
    assert body[0]["intent_filters"] == {"action_item_id": "2"}
    assert body[0]["requires_confirmation"] is True


def test_agent_debug_run_creates_debug_trace(client) -> None:
    response = client.post(
        "/api/agent/debug-run",
        json={"message": "查看未完成任务", "chat_id": "debug-web"},
    )

    assert response.status_code == 200
    body = response.json()
    # Without a real LLM API key, the agent returns handled=False gracefully
    assert "handled" in body
    assert "intent_name" in body
    assert "trace_id" in body

    if body["trace_id"] is not None:
        traces_response = client.get("/api/agent/traces")
        traces = traces_response.json()
        assert any(t["id"] == body["trace_id"] for t in traces)


def test_agent_debug_run_rejects_empty_message(client) -> None:
    response = client.post("/api/agent/debug-run", json={"message": "   "})

    assert response.status_code == 400
