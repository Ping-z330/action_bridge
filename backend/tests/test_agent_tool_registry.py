import pytest
from datetime import UTC, datetime

from app.agent.tool_contracts import AgentTool, AgentToolRegistry
from app.agent.tool_adapters import LocalAgentToolAdapter
from app.agent.tool_registry import (
    CREATE_TASK,
    DEFAULT_TOOL_REGISTRY,
    QUERY_TASKS,
    SUMMARIZE_PROJECT,
    UPDATE_TASK_DEADLINE,
    UPDATE_TASK_OWNER,
    UPDATE_TASK_STATUS,
    build_tool_registry_from_adapters,
)
from app.schemas.task_result import ActionItemListItem


def test_default_tool_registry_exposes_core_agent_tools() -> None:
    tool_names = {tool.name for tool in DEFAULT_TOOL_REGISTRY.list_tools()}

    assert {
        QUERY_TASKS,
        SUMMARIZE_PROJECT,
        UPDATE_TASK_STATUS,
        CREATE_TASK,
        UPDATE_TASK_DEADLINE,
        UPDATE_TASK_OWNER,
    }.issubset(tool_names)


def test_tool_registry_rejects_duplicate_tool_names() -> None:
    registry = AgentToolRegistry()
    tool = AgentTool(name="demo", description="Demo tool", handler=lambda: None)

    registry.register(tool)

    with pytest.raises(ValueError):
        registry.register(tool)


def test_tool_registry_executes_query_tool() -> None:
    item = ActionItemListItem(
        id=1,
        meeting_id=1,
        meeting_title="官网改版同步",
        title="修复移动端导航",
        owner_name="前端同学",
        deadline="周五",
        deadline_date="",
        deadline_time="",
        status="pending",
        due_status="upcoming",
        due_status_label="未到期",
        created_at=datetime.now(UTC),
    )

    results = DEFAULT_TOOL_REGISTRY.execute(
        QUERY_TASKS,
        items=[item],
        filters={"owner": "前端"},
    )

    assert results == [item]


def test_default_tool_registry_exposes_mcp_ready_metadata() -> None:
    metadata_by_name = {
        metadata["name"]: metadata
        for metadata in DEFAULT_TOOL_REGISTRY.list_tool_metadata()
    }

    assert metadata_by_name[QUERY_TASKS]["source"] == "local"
    assert metadata_by_name[QUERY_TASKS]["category"] == "task_query"
    assert metadata_by_name[QUERY_TASKS]["dangerous"] is False
    assert metadata_by_name[CREATE_TASK]["category"] == "task_write"
    assert metadata_by_name[CREATE_TASK]["dangerous"] is True
    assert metadata_by_name[CREATE_TASK]["requires_confirmation"] is True
    assert metadata_by_name[UPDATE_TASK_DEADLINE]["requires_confirmation"] is True
    assert metadata_by_name[UPDATE_TASK_OWNER]["requires_confirmation"] is True


def test_tool_registry_can_be_built_from_adapters() -> None:
    registry = build_tool_registry_from_adapters([LocalAgentToolAdapter()])

    assert registry.get(QUERY_TASKS).source == "local"
    assert registry.get(UPDATE_TASK_STATUS).dangerous is True
