from typing import TypedDict

from sqlalchemy.orm import Session

from app.agent.confirmed_intents import build_confirmed_action_intent
from app.agent.response_builder import build_agent_response_from_intent
from app.agent.schemas import AgentExecutedAction, AgentIntent, AgentResponse, ProjectProgressSummary
from app.agent.service import detect_intent_with_fallback
from app.agent.task_reference_resolver import resolve_task_reference_intent
from app.agent.tool_registry import (
    CREATE_TASK,
    DEFAULT_TOOL_REGISTRY,
    QUERY_TASKS,
    SUMMARIZE_PROJECT,
    UPDATE_TASK_DEADLINE,
    UPDATE_TASK_OWNER,
    UPDATE_TASK_STATUS,
)
from app.schemas.task_result import ActionItemListItem
from app.services.meeting_service import list_action_items
from app.services.agent_task_context_service import load_recent_task_ids
from app.services.agent_trace_service import create_agent_trace_log
from app.services.memory_service import normalize_message_with_memory

try:
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover - exercised when optional dependency is absent.
    END = "__end__"
    StateGraph = None


# Agent 图在每个节点之间传递的状态对象。
# 可以把它理解成“Agent 执行过程中的共享上下文”。
class AgentGraphState(TypedDict, total=False):
    # 数据库会话。
    db: Session

    # 用户原始输入。
    message: str

    # 当前飞书会话 ID，用于读取最近任务上下文和记录 trace。
    chat_id: str

    # confirmed_action_type / pending_payload 用于“用户确认后”的执行流程。
    # 例如用户回复“确认”后，不再重新理解自然语言，而是执行之前保存的 pending payload。
    confirmed_action_type: str
    pending_payload: dict[str, str]

    # 经过 Memory 别名归一化后的消息。
    normalized_message: str

    # 当前系统里的行动项列表，以及当前会话最近展示过的任务 ID。
    action_items: list[ActionItemListItem]
    recent_task_ids: list[int]

    # Agent 识别出来的意图，以及路由名。
    intent: AgentIntent | None
    intent_route: str

    # 工具执行结果。
    tool_executed: bool
    tool_items: list[ActionItemListItem]
    progress_summary: ProjectProgressSummary
    executed_action: AgentExecutedAction

    # 最终要返回给上层 orchestrator 的 AgentResponse。
    agent_response: AgentResponse


def is_langgraph_available() -> bool:
    # LangGraph 是可选依赖；不可用时会走 _run_linear_graph 线性兜底。
    return StateGraph is not None


# 普通自然语言入口。
# 飞书自然语言消息、Web Agent Debug 都会调用这里。
def run_agent_graph(db: Session, message: str, chat_id: str | None = None) -> AgentResponse:
    initial_state: AgentGraphState = {
        "db": db,
        "message": message,
        "chat_id": chat_id or "",
    }
    result = run_agent_graph_state(initial_state)
    return result["agent_response"]


# 用户回复“确认”后的入口。
# 这里用 pending payload 构造确认意图，并真正执行创建/修改任务。
def run_confirmed_agent_action(db: Session, action_type: str, payload: dict[str, str]) -> AgentResponse:
    initial_state: AgentGraphState = {
        "db": db,
        "message": "",
        "confirmed_action_type": action_type,
        "pending_payload": payload,
    }
    result = run_agent_graph_state(initial_state)
    return result["agent_response"]


def run_agent_graph_state(initial_state: AgentGraphState) -> AgentGraphState:
    # 优先使用 LangGraph；如果依赖不可用，则按相同顺序手动线性执行各节点。
    return _AGENT_GRAPH.invoke(initial_state) if _AGENT_GRAPH else _run_linear_graph(initial_state)


# 节点 1：加载 Memory。
# 把用户消息里的别名替换成标准说法，例如“官网” -> “官网改版”。
def _load_memory_node(state: AgentGraphState) -> AgentGraphState:
    # 确认后的执行不需要再归一化消息，因为 payload 已经是结构化数据。
    if state.get("confirmed_action_type"):
        return {"normalized_message": state.get("message", "")}

    return {
        "normalized_message": normalize_message_with_memory(state["db"], state["message"]),
    }


# 节点 2：加载任务上下文。
# 包括全部行动项，以及这个会话最近展示过的任务 ID。
def _load_task_context_node(state: AgentGraphState) -> AgentGraphState:
    return {
        "action_items": list_action_items(state["db"]),
        "recent_task_ids": load_recent_task_ids(state["db"], state.get("chat_id")),
    }


# 节点 3：识别意图。
# 普通消息走规则/LLM 识别；确认后的操作则直接用 pending payload 构造确认意图。
def _detect_intent_node(state: AgentGraphState) -> AgentGraphState:
    confirmed_intent = build_confirmed_action_intent(
        state.get("confirmed_action_type"),
        state.get("pending_payload"),
    )
    if confirmed_intent:
        return {
            "intent": confirmed_intent,
        }

    return {
        "intent": detect_intent_with_fallback(state["normalized_message"]),
    }


# 节点 4：记录意图路由名。
# 当前代码主要用于调试/trace，真正分支执行在 _execute_tool_node。
def _route_intent_node(state: AgentGraphState) -> AgentGraphState:
    intent = state.get("intent")
    return {
        "intent_route": intent.name if intent else "unhandled",
    }


# 节点 5：解析任务引用。
# 把“第一个任务”“login page 那个任务”这类说法解析成具体 action_item_id。
def _resolve_task_reference_node(state: AgentGraphState) -> AgentGraphState:
    return {
        "intent": resolve_task_reference_intent(
            state.get("intent"),
            state["normalized_message"],
            state["action_items"],
            state.get("recent_task_ids", []),
        ),
    }


# 节点 6：执行工具。
# 查询、总结、状态更新、确认后的创建/修改任务都会在这里调用 Tool Registry。
def _execute_tool_node(state: AgentGraphState) -> AgentGraphState:
    intent = state.get("intent")
    if not intent:
        return {"tool_executed": False}

    # 查询任务：只在内存列表上过滤，不写数据库。
    if intent.name == "query_tasks":
        return {
            "tool_executed": True,
            "tool_items": DEFAULT_TOOL_REGISTRY.execute(
                QUERY_TASKS,
                items=state["action_items"],
                filters=intent.filters,
            ),
        }

    # 总结项目进度：根据行动项统计完成率、风险任务等。
    if intent.name == "summarize_project":
        return {
            "tool_executed": True,
            "progress_summary": DEFAULT_TOOL_REGISTRY.execute(
                SUMMARIZE_PROJECT,
                items=state["action_items"],
                keyword=intent.filters["keyword"],
            ),
        }

    # 更新任务状态：这类状态更新可以直接执行。
    if intent.name == "update_task_status":
        action_item_id = int(intent.filters["action_item_id"])
        target_status = intent.filters["status"]
        return {
            "tool_executed": True,
            "executed_action": DEFAULT_TOOL_REGISTRY.execute(
                UPDATE_TASK_STATUS,
                db=state["db"],
                action_item_id=action_item_id,
                target_status=target_status,
            ),
        }

    # 确认创建任务：只有用户回复“确认”后才会走到这里。
    if intent.name == "confirm_create_task":
        return {
            "tool_executed": True,
            "executed_action": DEFAULT_TOOL_REGISTRY.execute(
                CREATE_TASK,
                db=state["db"],
                title=intent.filters["title"],
                owner_name=intent.filters["owner_name"],
                deadline=intent.filters["deadline"],
            ),
        }

    # 确认修改截止时间。
    if intent.name == "confirm_update_task_deadline":
        action_item_id = int(intent.filters["action_item_id"])
        target_deadline = intent.filters["new_deadline"]
        return {
            "tool_executed": True,
            "executed_action": DEFAULT_TOOL_REGISTRY.execute(
                UPDATE_TASK_DEADLINE,
                db=state["db"],
                action_item_id=action_item_id,
                target_deadline=target_deadline,
            ),
        }

    # 确认修改负责人。
    if intent.name == "confirm_update_task_owner":
        action_item_id = int(intent.filters["action_item_id"])
        target_owner_name = intent.filters["new_owner_name"]
        return {
            "tool_executed": True,
            "executed_action": DEFAULT_TOOL_REGISTRY.execute(
                UPDATE_TASK_OWNER,
                db=state["db"],
                action_item_id=action_item_id,
                target_owner_name=target_owner_name,
            ),
        }

    return {"tool_executed": False}


# 节点 7：构造最终 AgentResponse，并写入 Agent Trace。
def _build_response_node(state: AgentGraphState) -> AgentGraphState:
    agent_response = build_agent_response_from_intent(
        state.get("intent"),
        state["action_items"],
        tool_items=state.get("tool_items"),
        progress_summary=state.get("progress_summary"),
        executed_action=state.get("executed_action"),
    )

    # 记录本次 Agent 执行过程，给 /agent-debug 页面查看。
    create_agent_trace_log(
        state["db"],
        message=state.get("message", ""),
        chat_id=state.get("chat_id", ""),
        normalized_message=state.get("normalized_message", ""),
        intent=state.get("intent"),
        tool_executed=state.get("tool_executed", False),
        response=agent_response,
    )
    return {
        "agent_response": agent_response,
    }


# LangGraph 不可用时的线性兜底执行。
# 顺序必须和 _build_agent_graph 里的边保持一致。
def _run_linear_graph(state: AgentGraphState) -> AgentGraphState:
    state = {**state, **_load_memory_node(state)}
    state = {**state, **_load_task_context_node(state)}
    state = {**state, **_detect_intent_node(state)}
    state = {**state, **_resolve_task_reference_node(state)}
    state = {**state, **_route_intent_node(state)}
    state = {**state, **_execute_tool_node(state)}
    state = {**state, **_build_response_node(state)}
    return state


# 构建 LangGraph 工作流。
# 每个 node 都是上面定义的一个小函数，edge 决定执行顺序。
def _build_agent_graph():
    if StateGraph is None:
        return None

    workflow = StateGraph(AgentGraphState)

    # 注册节点。
    workflow.add_node("load_memory", _load_memory_node)
    workflow.add_node("load_task_context", _load_task_context_node)
    workflow.add_node("detect_intent", _detect_intent_node)
    workflow.add_node("resolve_task_reference", _resolve_task_reference_node)
    workflow.add_node("route_intent", _route_intent_node)
    workflow.add_node("execute_tool", _execute_tool_node)
    workflow.add_node("build_response", _build_response_node)

    # 设置执行顺序。
    workflow.set_entry_point("load_memory")
    workflow.add_edge("load_memory", "load_task_context")
    workflow.add_edge("load_task_context", "detect_intent")
    workflow.add_edge("detect_intent", "resolve_task_reference")
    workflow.add_edge("resolve_task_reference", "route_intent")
    workflow.add_edge("route_intent", "execute_tool")
    workflow.add_edge("execute_tool", "build_response")
    workflow.add_edge("build_response", END)
    return workflow.compile()


# 模块加载时构建一次图，后续每次 run_agent_graph 直接复用。
_AGENT_GRAPH = _build_agent_graph()
