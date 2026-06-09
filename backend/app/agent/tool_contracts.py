from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentTool:
    # Agent 可调用工具的统一描述：名字、说明、执行函数、来源和安全属性。
    name: str
    description: str
    handler: Callable[..., Any]
    source: str = "local"
    category: str = "general"
    dangerous: bool = False
    requires_confirmation: bool = False

    def metadata(self) -> dict[str, Any]:
        # 给前端、调试页面或 MCP 风格工具列表使用的只读元信息。
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "category": self.category,
            "dangerous": self.dangerous,
            "requires_confirmation": self.requires_confirmation,
        }


class AgentToolAdapter:
    # 工具适配器基类：不同来源的工具都实现 list_tools，然后交给 registry 注册。
    name: str
    source: str

    def list_tools(self) -> list[AgentTool]:
        # 子类必须返回自己提供的工具列表。
        raise NotImplementedError


class AgentToolRegistry:
    def __init__(self, tools: list[AgentTool] | None = None) -> None:
        # 用字典按工具名保存工具，方便通过名字快速查找和执行。
        self._tools: dict[str, AgentTool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: AgentTool) -> None:
        # 工具名必须唯一，否则 Agent 调用时会不知道该执行哪一个。
        if tool.name in self._tools:
            raise ValueError(f"Agent tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool:
        # 根据工具名取工具；找不到时给出更清晰的错误信息。
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Agent tool not found: {name}") from exc

    def execute(self, name: str, **kwargs: Any) -> Any:
        # 统一执行入口：先找到工具，再把参数传给工具的 handler。
        return self.get(name).handler(**kwargs)

    def list_tools(self) -> list[AgentTool]:
        # 返回完整工具对象，通常给后端内部逻辑使用。
        return list(self._tools.values())

    def list_tool_metadata(self) -> list[dict[str, Any]]:
        # 返回工具元信息，适合给调试接口或外部系统查看。
        return [tool.metadata() for tool in self.list_tools()]
