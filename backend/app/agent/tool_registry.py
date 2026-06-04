from app.agent.tool_adapters import (
    CREATE_TASK,
    QUERY_TASKS,
    SUMMARIZE_PROJECT,
    UPDATE_TASK_DEADLINE,
    UPDATE_TASK_OWNER,
    UPDATE_TASK_STATUS,
    LocalAgentToolAdapter,
)
from app.agent.tool_contracts import AgentToolAdapter, AgentToolRegistry


def build_tool_registry_from_adapters(adapters: list[AgentToolAdapter]) -> AgentToolRegistry:
    registry = AgentToolRegistry()
    for adapter in adapters:
        for tool in adapter.list_tools():
            registry.register(tool)
    return registry


def build_default_tool_registry() -> AgentToolRegistry:
    return build_tool_registry_from_adapters([LocalAgentToolAdapter()])


DEFAULT_TOOL_REGISTRY = build_default_tool_registry()
