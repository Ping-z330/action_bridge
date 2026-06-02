from typing import TypedDict

from sqlalchemy.orm import Session

from app.agent.schemas import AgentResponse
from app.agent.service import handle_agent_message
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
    agent_response: AgentResponse


def is_langgraph_available() -> bool:
    return StateGraph is not None


def run_agent_graph(db: Session, message: str) -> AgentResponse:
    initial_state: AgentGraphState = {
        "db": db,
        "message": message,
    }
    result = _AGENT_GRAPH.invoke(initial_state) if _AGENT_GRAPH else _run_linear_graph(initial_state)
    return result["agent_response"]


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
        "agent_response": handle_agent_message(
            state["normalized_message"],
            state["action_items"],
        ),
    }


def _run_linear_graph(state: AgentGraphState) -> AgentGraphState:
    state = {**state, **_load_memory_node(state)}
    state = {**state, **_load_task_context_node(state)}
    state = {**state, **_detect_intent_node(state)}
    return state


def _build_agent_graph():
    if StateGraph is None:
        return None

    workflow = StateGraph(AgentGraphState)
    workflow.add_node("load_memory", _load_memory_node)
    workflow.add_node("load_task_context", _load_task_context_node)
    workflow.add_node("detect_intent", _detect_intent_node)

    workflow.set_entry_point("load_memory")
    workflow.add_edge("load_memory", "load_task_context")
    workflow.add_edge("load_task_context", "detect_intent")
    workflow.add_edge("detect_intent", END)
    return workflow.compile()


_AGENT_GRAPH = _build_agent_graph()
