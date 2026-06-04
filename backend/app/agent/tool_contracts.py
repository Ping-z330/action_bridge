from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    handler: Callable[..., Any]
    source: str = "local"
    category: str = "general"
    dangerous: bool = False
    requires_confirmation: bool = False

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "category": self.category,
            "dangerous": self.dangerous,
            "requires_confirmation": self.requires_confirmation,
        }


class AgentToolAdapter:
    name: str
    source: str

    def list_tools(self) -> list[AgentTool]:
        raise NotImplementedError


class AgentToolRegistry:
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
