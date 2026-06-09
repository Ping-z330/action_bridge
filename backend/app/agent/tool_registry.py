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
    # 从多个 adapter 收集工具，并统一注册到一个 registry 里。
    registry = AgentToolRegistry()
    for adapter in adapters:
        for tool in adapter.list_tools():
            registry.register(tool)
    return registry


def build_default_tool_registry() -> AgentToolRegistry:
    # 默认只加载本地工具；以后如果接 MCP/外部工具，可以在这里追加 adapter。
    return build_tool_registry_from_adapters([LocalAgentToolAdapter()])


# 模块级默认注册表，其他 Agent 代码可以直接导入使用。
DEFAULT_TOOL_REGISTRY = build_default_tool_registry()
