"""Personal Assistant Agent.

每个项目成员在飞书私聊里拥有一个 PersonalAssistant。
它负责：
1. 接收成员的进度汇报（"XX任务做完了"）
2. 结构化翻译成 mRNA 消息（task_update）
3. 通过 mRNA Hub 发送给中央 Agent
4. 回复成员确认消息

PersonalAssistant 不是通用聊天机器人——它只做一件事：
把自然语言进度汇报变成结构化数据。
"""

from sqlalchemy.orm import Session

from app.agent.graph import run_agent_graph
from app.agent.mrna_protocol import (
    MSG_STATUS_REPORT,
    MSG_TASK_UPDATE,
    mRNAEnvelope,
    get_mrna_hub,
)
from app.agent.schemas import AgentResponse


PERSONAL_ASSISTANT_PROMPT = """你是 {member_name} 的个人项目助手。
你的任务是把 {member_name} 的进度汇报转换成结构化的任务状态更新。

## 规则
1. 如果 {member_name} 说某个具体任务完成了/做完了/搞定了 → 用 query_tasks 找到对应任务，然后用 update_task_status 更新为 completed
2. 如果 {member_name} 说某个任务在进行中/遇到问题 → 提取任务信息，更新状态
3. 如果只是闲聊或模糊的话（"今天好累"）→ 直接回复，不需要操作
4. 回复要简短、友好。告诉 {member_name} 已经同步了进度。
5. 更新完状态后，告诉我你更新了什么，我会转给中央系统做风险分析。
"""


def handle_personal_message(
    db: Session,
    message: str,
    member_name: str,
    member_chat_id: str,
    project_id: int | None = None,
) -> AgentResponse:
    """Handle a private message from a project member.

    1. Run the ReAct Agent with personal context
    2. If tasks were updated, send mRNA to central agent
    3. Return the agent response for the member to see
    """
    # Build personalized system prompt
    personalized_prompt = PERSONAL_ASSISTANT_PROMPT.format(member_name=member_name)

    # Run the standard ReAct Agent — the tools will operate on behalf of this member
    # The message context already includes task list, so the LLM can find their tasks
    response = run_agent_graph(
        db, message,
        chat_id=f"personal:{member_chat_id}",
        member_name=member_name,
    )

    # If the LLM updated any task status, send mRNA to central agent
    if response.executed_action:
        hub = get_mrna_hub()

        # task_update: a concrete task was updated
        envelope = mRNAEnvelope(
            sender_agent_id=f"personal:{member_name}",
            receiver_agent_id=f"central:project-{project_id or 0}",
            message_type=MSG_TASK_UPDATE,
            payload={
                "member_name": member_name,
                "member_chat_id": member_chat_id,
                "action_type": response.executed_action.action_type,
                "action_item_id": response.executed_action.action_item_id,
                "target_status": getattr(response.executed_action, "target_status", ""),
                "target_deadline": getattr(response.executed_action, "target_deadline", ""),
                "target_owner_name": getattr(response.executed_action, "target_owner_name", ""),
                "steps": [s.to_dict() for s in response.steps],
            },
        )
        hub.send(envelope)

    elif response.items:
        # status_report: the member queried or viewed tasks — worth noting activity
        hub = get_mrna_hub()
        envelope = mRNAEnvelope(
            sender_agent_id=f"personal:{member_name}",
            receiver_agent_id=f"central:project-{project_id or 0}",
            message_type=MSG_STATUS_REPORT,
            payload={
                "member_name": member_name,
                "member_chat_id": member_chat_id,
                "activity": f"{member_name} queried tasks, found {len(response.items)} results",
                "intent_name": response.intent_name,
            },
        )
        hub.send(envelope)

    return response


def build_personal_assistant_response(response: AgentResponse, member_name: str) -> str:
    """Build a user-friendly reply for the member."""
    if not response.handled:
        return f"抱歉 {member_name}，我暂时不太理解。你可以说'XX任务做完了'或者'查看我的任务'。"

    # If the LLM produced a final message, use it
    if response.message and response.message != "已处理您的请求。":
        return response.message

    # Fallback: build a summary from the steps
    if response.steps:
        step_descriptions = [
            f"  - {s.tool_name}: {s.tool_result[:80]}"
            for s in response.steps
            if s.tool_name
        ]
        if step_descriptions:
            return f"收到，{member_name}。已完成以下操作:\n" + "\n".join(step_descriptions)

    return f"收到，{member_name}。已同步你的进度。"
