"""Agent 工具合约：AgentTool / AgentToolAdapter / AgentToolRegistry。

每个工具现在携带 parameters_schema（JSON Schema 格式），
供 LLM Function Calling 使用。LLM 看到这些 schema 后自己决定调哪个工具、传什么参数。
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentTool:
    """Agent 可调用的单个工具。

    parameters_schema 是新增字段 —— OpenAPI/JSON Schema 风格的参数定义。
    LLM Function Calling 需要这个来决定传什么参数。
    """
    name: str
    description: str
    handler: Callable[..., Any]
    parameters_schema: dict[str, Any] = field(default_factory=dict)
    source: str = "local"
    category: str = "general"
    dangerous: bool = False
    requires_confirmation: bool = False

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema,
            "source": self.source,
            "category": self.category,
            "dangerous": self.dangerous,
            "requires_confirmation": self.requires_confirmation,
        }

    def to_openai_tool(self) -> dict[str, Any]:
        """转为 OpenAI Function Calling 兼容的工具定义。"""
        tool_def: dict[str, Any] = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
            },
        }
        if self.parameters_schema:
            tool_def["function"]["parameters"] = self.parameters_schema
        return tool_def


class AgentToolAdapter:
    """工具适配器基类：不同来源的工具都实现 list_tools。"""
    name: str = ""
    source: str = ""

    def list_tools(self) -> list[AgentTool]:
        raise NotImplementedError


class AgentToolRegistry:
    """工具注册表：按名称查找和执行工具。"""

    def __init__(self, tools: list[AgentTool] | None = None) -> None:
        self._tools: dict[str, AgentTool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: AgentTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Agent tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Agent tool not found: {name}") from exc

    def execute(self, name: str, **kwargs: Any) -> Any:
        return self.get(name).handler(**kwargs)

    def list_tools(self) -> list[AgentTool]:
        return list(self._tools.values())

    def list_tool_metadata(self) -> list[dict[str, Any]]:
        return [tool.metadata() for tool in self.list_tools()]

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """将所有已注册工具转为 OpenAI Function Calling 格式。"""
        return [tool.to_openai_tool() for tool in self.list_tools()]
