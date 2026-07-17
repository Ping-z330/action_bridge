"""ActionBridge Agent 核心：ReAct 循环。

旧实现用 LangGraph StateGraph + 7 个线性节点做意图分类 → 路由工具。
新实现用 ReAct 循环：LLM 拿到带 JSON Schema 的工具列表，
自主决定调哪个工具、传什么参数、调几次、什么时候停。

保留向后兼容的入口函数，但内部全部走 ReAct。
"""

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.agent.confirmed_intents import build_confirmed_action_intent
from app.agent.schemas import AgentResponse, AgentStep
from app.agent.tool_registry import (
    DEFAULT_TOOL_REGISTRY,
)
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
)
from app.services.meeting_service import list_action_items
from app.services.agent_task_context_service import load_recent_task_ids, save_recent_task_context
from app.services.agent_trace_service import create_agent_trace_log
from app.services.memory_service import normalize_message_with_memory

logger = logging.getLogger(__name__)

# ReAct 循环最大步数，防止 LLM 无限循环。
MAX_REACT_STEPS = 8

# 系统提示词：告诉 LLM 它的角色、可用工具、行为规则。
SYSTEM_PROMPT = """你是 ActionBridge 的项目管理 AI 助手。
你负责帮助团队成员跟踪项目进度、分析风险、执行任务管理操作。

## 行为规则
1. 收到用户消息后，分析其意图，选择合适的工具完成任务。
2. 查询类请求（"有哪些逾期任务""张三负责什么"）→ 使用 query_tasks 或 query_member_activity
3. 风险分析请求（"项目有什么风险""帮我看看项目状态"）→ 使用 analyze_risk 或 generate_progress_report
4. 修改类请求（"把 X 任务标记完成""改截止时间"）→ 优先使用 update_task_status（可直接执行），创建和修改负责人/截止时间需要用户二次确认
5. 不确定任务编号时，先用 query_tasks 查出任务列表，再操作。
6. 一次能完成的查询不要分多次。需要多步操作时（先查再改），自己安排顺序。
7. 工具执行后根据结果生成简洁的中文回复。回复应清晰、直接，不啰嗦。
8. 用户问"项目进展""项目进度"时，按项目（meeting）分别概述，不要把所有项目混在一起。
9. 如果你认为用户请求不需要调用工具，直接回复文本即可。"""


# ── 公共入口 ────────────────────────────────────────────────

def run_agent_graph(db: Session, message: str, chat_id: str | None = None, member_name: str | None = None) -> AgentResponse:
    """普通自然语言入口。飞书消息、Web Agent Debug 都走这里。

    如果 member_name 不为空，Agent 会以该成员的视角工作：
    - "我的任务" 自动过滤 owner=member_name
    - "我的职责" 返回该成员负责的任务
    """

    effective_chat_id = chat_id or "default"

    # 1. Memory 别名归一化
    normalized = normalize_message_with_memory(db, message)

    # 2. 加载上下文
    action_items = list_action_items(db)
    recent_task_ids = load_recent_task_ids(db, effective_chat_id)

    # 3. ReAct 循环
    response = _run_react_loop(
        db=db,
        user_message=normalized,
        chat_id=effective_chat_id,
        action_items=action_items,
        recent_task_ids=recent_task_ids,
        member_name=member_name,
    )

    # 4. 保存任务上下文
    if response.items:
        save_recent_task_context(db, effective_chat_id, response.items[:10])

    # 5. 记录 Trace
    create_agent_trace_log(
        db,
        message=message,
        chat_id=effective_chat_id,
        normalized_message=normalized,
        intent_name=response.intent_name,
        intent_filters_json=json.dumps(response.intent_filters, ensure_ascii=False),
        tool_name=",".join(s.tool_name for s in response.steps if s.tool_name),
        tool_executed=any(s.tool_name for s in response.steps),
        response=response,
    )

    return response


def run_confirmed_agent_action(db: Session, action_type: str, payload: dict[str, str]) -> AgentResponse:
    """用户确认后的入口。用 pending payload 构造确认操作，真正执行写操作。"""
    confirmed = build_confirmed_action_intent(action_type, payload)
    if not confirmed:
        return AgentResponse(handled=False, message="Unknown confirmed action type.")

    # 确认操作直接执行工具，不走 ReAct 循环。
    response = _execute_confirmed_action(db, action_type, confirmed.filters)
    create_agent_trace_log(
        db,
        message="[confirmed]",
        chat_id="",
        normalized_message="",
        intent_name=f"confirm_{action_type}",
        intent_filters_json=json.dumps(confirmed.filters, ensure_ascii=False),
        tool_executed=True,
        response=response,
    )
    return response


# ── ReAct 核心循环 ──────────────────────────────────────────

def _run_react_loop(
    db: Session,
    user_message: str,
    chat_id: str,
    action_items: list,
    recent_task_ids: list[int],
    member_name: str | None = None,
) -> AgentResponse:
    """ReAct 循环：给 LLM 工具列表 → LLM 选工具 → 执行 → 结果喂回 → 循环。"""

    tools = DEFAULT_TOOL_REGISTRY.to_openai_tools()

    # 给任务上下文，让 LLM 能理解"第3个任务"这类指代
    context_info = _build_context_prompt(action_items, recent_task_ids, member_name)

    # 如果知道当前成员，在 system prompt 中注入角色上下文
    system_content = SYSTEM_PROMPT
    if member_name:
        system_content += (
            f"\n\n## 当前用户\n你正在和项目成员 **{member_name}** 对话。"
            f"当用户说\"我的任务\"\"我的职责\"\"我负责的\"\"我做完了\"等第一人称表述时，"
            f"默认查询和操作 owner_name=\"{member_name}\" 的任务，不要查其他人的。"
            f"用户说\"查看所有任务\"时仍然查全局。"
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": f"{context_info}\n\n用户消息: {user_message}"},
    ]

    steps: list[AgentStep] = []
    all_items: list = []
    executed_action = None
    progress_summary = None
    risk_report = None
    intent_name = ""
    intent_filters: dict[str, str] = {}

    for step_index in range(MAX_REACT_STEPS):
        response = _call_llm_with_tools(messages, tools)

        if response is None:
            # LLM 调用失败
            return AgentResponse(
                handled=False,
                message="AI 服务暂时不可用，请稍后重试。",
                steps=steps,
            )

        if not response.get("tool_calls"):
            # LLM 不再调工具 → 输出最终回复
            content = response.get("content", "")
            return AgentResponse(
                handled=True,
                message=content or "已处理您的请求。",
                steps=steps,
                items=all_items,
                progress_summary=progress_summary,
                executed_action=executed_action,
                risk_report=risk_report,
                intent_name=intent_name or "agent_response",
                intent_filters=intent_filters,
            )

        # 构建 assistant 消息（包含所有 tool_calls + reasoning_content）
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": response.get("content") or None,
            "tool_calls": response["tool_calls"],
        }
        if response.get("reasoning_content"):
            assistant_msg["reasoning_content"] = response["reasoning_content"]
        messages.append(assistant_msg)

        # 执行 LLM 选中的所有工具
        for tc in response["tool_calls"]:
            tool_name = tc["function"]["name"]
            try:
                tool_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                tool_args = {}

            step = AgentStep(
                thought=f"LLM 选择调用工具: {tool_name}",
                tool_name=tool_name,
                tool_args=tool_args,
            )

            # 执行工具 — 需要 db 的工具在这传入
            result = None
            try:
                result = _execute_tool(db, tool_name, tool_args, action_items)
                step.tool_result = json.dumps(result, ensure_ascii=False, default=str)[:500]
            except Exception as exc:
                step.tool_error = str(exc)
                step.tool_result = f"工具执行失败: {exc}"

            steps.append(step)

            # 追加工具执行结果
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", f"call_{step_index}"),
                "content": step.tool_result,
            })

            # 从结果中提取 AgentResponse 需要的字段
            if result is not None:
                intent_name, intent_filters, all_items, progress_summary, executed_action, risk_report = \
                    _extract_result_fields(tool_name, tool_args, result, action_items)

    # 超过最大步数
    return AgentResponse(
        handled=True,
        message=f"已完成 {len(steps)} 步操作。如需更多分析请再告诉我。",
        steps=steps,
        items=all_items,
        progress_summary=progress_summary,
        executed_action=executed_action,
        risk_report=risk_report,
        intent_name=intent_name,
        intent_filters=intent_filters,
    )


# ── LLM 调用 ────────────────────────────────────────────────

def _call_llm_with_tools(messages: list[dict], tools: list[dict]) -> dict | None:
    """调用 LLM（当前用 DeepSeek），带 Function Calling 工具列表。"""
    from app.core.config import (
        DEEPSEEK_API_KEY,
        DEEPSEEK_BASE_URL,
        DEEPSEEK_MODEL,
    )

    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package not installed")
        return None

    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY.startswith("replace_with_"):
        logger.warning("DeepSeek API key not configured, falling back to rule-based handling")
        return None

    try:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.3,  # 低温度 -> 更确定性的工具选择
        )
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        return None

    choice = response.choices[0] if response.choices else None
    if not choice:
        return None

    msg = choice.message
    result: dict[str, Any] = {"content": msg.content or ""}

    # DeepSeek thinking mode: must preserve reasoning_content in subsequent requests
    if hasattr(msg, "reasoning_content") and msg.reasoning_content:
        result["reasoning_content"] = msg.reasoning_content

    if msg.tool_calls:
        result["tool_calls"] = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]

    return result


# ── 工具执行调度 ────────────────────────────────────────────

def _execute_tool(db: Session, tool_name: str, tool_args: dict, action_items: list) -> Any:
    """根据 LLM 选择的工具名，执行对应工具并返回结果。"""
    reg = DEFAULT_TOOL_REGISTRY

    # 需要 db 的写操作 + 分析工具
    if tool_name in (UPDATE_TASK_STATUS,):
        return reg.execute(tool_name, db=db, **tool_args)

    if tool_name in (UPDATE_TASK_DEADLINE, UPDATE_TASK_OWNER):
        # 危险写操作：只返回预览，不直接执行 → 需要用户确认
        return reg.execute(tool_name, db=db, **tool_args)

    if tool_name == CREATE_TASK:
        return reg.execute(tool_name, db=db, **tool_args)

    if tool_name == ANALYZE_RISK:
        return reg.execute(tool_name, db=db, **tool_args)

    if tool_name == GENERATE_PROGRESS_REPORT:
        return reg.execute(tool_name, db=db, **tool_args)

    if tool_name == CREATE_ALERT:
        return reg.execute(tool_name, db=db, **tool_args)

    # 查询类工具：将 LLM 的平铺参数转为 filters dict
    if tool_name in (QUERY_TASKS,):
        filters = _tool_args_to_filters(tool_args)
        return reg.execute(tool_name, items=action_items, filters=filters)

    if tool_name in (SUMMARIZE_PROJECT,):
        return reg.execute(tool_name, items=action_items, **tool_args)

    if tool_name == QUERY_MEMBER_ACTIVITY:
        return reg.execute(tool_name, db=db, items=action_items, **tool_args)

    logger.warning("Unknown tool requested by LLM: %s", tool_name)
    return {"error": f"Unknown tool: {tool_name}"}


# ── 确认操作执行 ────────────────────────────────────────────

def _execute_confirmed_action(db: Session, action_type: str, filters: dict[str, str]) -> AgentResponse:
    """执行用户确认后的写操作。不走 ReAct，直接执行工具。"""
    reg = DEFAULT_TOOL_REGISTRY

    try:
        if action_type == "create_task":
            result = reg.execute(CREATE_TASK, db=db,
                                title=filters["title"],
                                owner_name=filters["owner_name"],
                                deadline=filters.get("deadline", filters.get("new_deadline", "")))
        elif action_type == "update_task_deadline":
            result = reg.execute(UPDATE_TASK_DEADLINE, db=db,
                                action_item_id=int(filters["action_item_id"]),
                                target_deadline=filters.get("new_deadline", filters.get("deadline", "")))
        elif action_type == "update_task_owner":
            result = reg.execute(UPDATE_TASK_OWNER, db=db,
                                action_item_id=int(filters["action_item_id"]),
                                target_owner_name=filters.get("new_owner_name", filters.get("owner_name", "")))
        else:
            return AgentResponse(handled=False, message=f"Unsupported action type: {action_type}")
    except Exception as exc:
        return AgentResponse(handled=False, message=f"Action execution failed: {exc}")

    return AgentResponse(
        handled=True,
        message=f"Action {action_type} executed successfully.",
        executed_action=result,
        intent_name=f"confirm_{action_type}",
        intent_filters=filters,
    )


# ── 辅助函数 ─────────────────────────────────────────────────

def _build_context_prompt(action_items: list, recent_task_ids: list[int], member_name: str | None = None) -> str:
    """构造给 LLM 的任务上下文，按项目（会议）分组，让它知道当前有哪些任务。

    如果 member_name 有值，会把该成员的任务排在最前面并标注。
    """
    if not action_items:
        return "当前系统中没有任何任务。"

    # 按项目（meeting）分组
    projects: dict[str, list] = {}
    for item in action_items:
        key = item.meeting_title or "未分类"
        if key not in projects:
            projects[key] = []
        projects[key].append(item)

    lines = ["当前系统中的项目及任务列表（按项目分组）:"]

    # 如果知道当前成员，把他的任务相关的项目排前面
    if member_name:
        my_projects = set(i.meeting_title for i in action_items if i.owner_name == member_name)
        sorted_project_keys = sorted(projects.keys(), key=lambda k: (k not in my_projects, k))
    else:
        sorted_project_keys = sorted(projects.keys())

    total_shown = 0
    for project_name in sorted_project_keys:
        tasks = projects[project_name]
        total_shown += len(tasks)
        completed = len([t for t in tasks if t.status == "completed"])
        lines.append(f"\n## {project_name} ({completed}/{len(tasks)} 完成)")
        for item in tasks:
            marker = " ★" if item.id in recent_task_ids else ""
            is_mine = " 👈" if member_name and item.owner_name == member_name else ""
            lines.append(
                f"  #{item.id} [{item.status}] {item.title} "
                f"(负责人: {item.owner_name}, 截止: {item.deadline}){marker}{is_mine}"
            )

    return "\n".join(lines)


def _tool_args_to_filters(tool_args: dict) -> dict[str, str]:
    """Convert LLM's flat tool arguments into a filters dict for query_tasks.

    LLM sees: {"status": "pending", "due_status": "due_today", "open_only": true}
    filter_tasks expects: {"status": "pending", "due_status": "due_today", "open_only": "true"}
    """
    filters: dict[str, str] = {}
    for key, value in tool_args.items():
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            filters[key] = "true" if value else "false"
        else:
            filters[key] = str(value)
    return filters


def _extract_result_fields(
    tool_name: str,
    tool_args: dict,
    result: Any,
    action_items: list,
) -> tuple[str, dict, list, Any, Any, Any]:
    """从工具执行结果中提取 AgentResponse 需要的字段。"""
    intent_name = tool_name
    intent_filters: dict[str, str] = {str(k): str(v) for k, v in tool_args.items()}
    items = []
    progress_summary = None
    executed_action = None
    risk_report = None

    if tool_name == QUERY_TASKS and isinstance(result, list):
        items = result
    elif tool_name == SUMMARIZE_PROJECT:
        progress_summary = result
        if hasattr(result, 'items'):
            items = result.items
    elif tool_name == ANALYZE_RISK:
        risk_report = result
    elif tool_name == GENERATE_PROGRESS_REPORT and isinstance(result, dict):
        if "top_risks" in result:
            # 构建简化的 RiskReport 供展示
            from app.agent.schemas import ProjectRiskReport
            risk_report = ProjectRiskReport(
                project_id=result.get("project_id", 0),
                risk_score=result.get("risk_score", 0),
                total_tasks=result.get("total_tasks", 0),
                overdue_count=result.get("overdue_count", 0),
                no_update_count=0,
                blocked_count=result.get("blocked_count", 0),
                conclusion=result.get("risk_conclusion", ""),
            )
    elif tool_name in (UPDATE_TASK_STATUS, UPDATE_TASK_DEADLINE, UPDATE_TASK_OWNER, CREATE_TASK):
        executed_action = result
    elif tool_name == QUERY_MEMBER_ACTIVITY and isinstance(result, dict):
        pass  # member activity 数据在 result 里，暂时不做特殊处理

    return intent_name, intent_filters, items, progress_summary, executed_action, risk_report
