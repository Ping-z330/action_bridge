from typing import TypedDict

from sqlalchemy.orm import Session

from app.agent.response_builder import build_agent_response_from_intent
from app.agent.schemas import AgentIntent, AgentResponse, ProjectProgressSummary
from app.agent.service import detect_intent_with_fallback
from app.agent.tools import filter_tasks, summarize_project_progress
from app.schemas.task_result import ActionItemListItem
from app.services.meeting_service import list_action_items
from app.services.memory_service import normalize_message_with_memory

try:
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover - exercised when optional dependency is absent.
    END = "__end__"
    StateGraph = None


class AgentGraphState(TypedDict, total=False):
    db: Session
    message: str
    normalized_message: str
    action_items: list[ActionItemListItem]
    intent: AgentIntent | None
    intent_route: str
    tool_executed: bool
    tool_items: list[ActionItemListItem]
    progress_summary: ProjectProgressSummary
    agent_response: AgentResponse


def is_langgraph_available() -> bool:
    return StateGraph is not None


def run_agent_graph(db: Session, message: str) -> AgentResponse:
    initial_state: AgentGraphState = {
        "db": db,
        "message": message,
    }
    result = run_agent_graph_state(initial_state)
    return result["agent_response"]


def run_agent_graph_state(initial_state: AgentGraphState) -> AgentGraphState:
    return _AGENT_GRAPH.invoke(initial_state) if _AGENT_GRAPH else _run_linear_graph(initial_state)


def _load_memory_node(state: AgentGraphState) -> AgentGraphState:
    return {
        "normalized_message": normalize_message_with_memory(state["db"], state["message"]),
    }


def _load_task_context_node(state: AgentGraphState) -> AgentGraphState:
    return {
        "action_items": list_action_items(state["db"]),
    }


def _detect_intent_node(state: AgentGraphState) -> AgentGraphState:
    return {
        "intent": detect_intent_with_fallback(state["normalized_message"]),
    }


def _route_intent_node(state: AgentGraphState) -> AgentGraphState:
    intent = state.get("intent")
    return {
        "intent_route": intent.name if intent else "unhandled",
    }


def _execute_tool_node(state: AgentGraphState) -> AgentGraphState:
    intent = state.get("intent")
    if not intent:
        return {"tool_executed": False}

    if intent.name == "query_tasks":
        return {
            "tool_executed": True,
            "tool_items": filter_tasks(state["action_items"], intent.filters),
        }

    if intent.name == "summarize_project":
        return {
            "tool_executed": True,
            "progress_summary": summarize_project_progress(
                state["action_items"],
                intent.filters["keyword"],
            ),
        }

    return {"tool_executed": False}


def _build_response_node(state: AgentGraphState) -> AgentGraphState:
    return {
        "agent_response": build_agent_response_from_intent(
            state.get("intent"),
            state["action_items"],
            tool_items=state.get("tool_items"),
            progress_summary=state.get("progress_summary"),
        ),
    }


def _run_linear_graph(state: AgentGraphState) -> AgentGraphState:
    state = {**state, **_load_memory_node(state)}
    state = {**state, **_load_task_context_node(state)}
    state = {**state, **_detect_intent_node(state)}
    state = {**state, **_route_intent_node(state)}
    state = {**state, **_execute_tool_node(state)}
    state = {**state, **_build_response_node(state)}
    return state


def _build_agent_graph():
    if StateGraph is None:
        return None

    workflow = StateGraph(AgentGraphState)
    workflow.add_node("load_memory", _load_memory_node)
    workflow.add_node("load_task_context", _load_task_context_node)
    workflow.add_node("detect_intent", _detect_intent_node)
    workflow.add_node("route_intent", _route_intent_node)
    workflow.add_node("execute_tool", _execute_tool_node)
    workflow.add_node("build_response", _build_response_node)

    workflow.set_entry_point("load_memory")
    workflow.add_edge("load_memory", "load_task_context")
    workflow.add_edge("load_task_context", "detect_intent")
    workflow.add_edge("detect_intent", "route_intent")
    workflow.add_edge("route_intent", "execute_tool")
    workflow.add_edge("execute_tool", "build_response")
    workflow.add_edge("build_response", END)
    return workflow.compile()


_AGENT_GRAPH = _build_agent_graph()
