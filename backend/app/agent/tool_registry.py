"""全局工具注册表：从多个 adapter 收集工具 → 注册到统一 registry。

DEFAULT_TOOL_REGISTRY 是模块级单例，Agent 核心代码直接导入使用。
"""

from app.agent.tool_adapters import (
    ANALYZE_RISK,
    CREATE_ALERT,
    CREATE_TASK,
    GENERATE_PROGRESS_REPORT,
    QUERY_MEMBER_ACTIVITY,
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
    # 默认加载本地工具。以后接 MCP/外部工具可以在这里追加 adapter。
    return build_tool_registry_from_adapters([LocalAgentToolAdapter()])


# 模块级默认注册表，其他 Agent 代码可以直接导入使用。
DEFAULT_TOOL_REGISTRY = build_default_tool_registry()
