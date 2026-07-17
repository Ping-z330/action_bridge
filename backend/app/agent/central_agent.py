"""Central Project Agent.

中央项目 Agent 持有项目计划依赖图。它持续接收来自 PersonalAssistant
的 mRNA 消息，在每次收到消息后：
1. 更新项目状态
2. 分析依赖链影响
3. 生成风险预警
4. 推送给项目负责人（通过飞书/消息通道）

The central agent is the "brain" of the A2A system — it's the hub
in the hub-and-spoke architecture.
"""

import json
import logging

from sqlalchemy.orm import Session

from app.agent.mrna_protocol import (
    MSG_ALERT_ACK,
    MSG_RISK_QUERY,
    MSG_TASK_UPDATE,
    mRNAEnvelope,
    get_mrna_hub,
)
from app.agent.schemas import AgentResponse, AgentStep
from app.agent.tool_adapters import ANALYZE_RISK, GENERATE_PROGRESS_REPORT
from app.agent.tool_registry import DEFAULT_TOOL_REGISTRY
from app.services.meeting_service import list_action_items

logger = logging.getLogger(__name__)

CENTRAL_AGENT_ID = "central"


def get_central_agent_id(project_id: int) -> str:
    return f"central:project-{project_id}"


def register_central_agent(project_id: int) -> None:
    """Register the central agent for a project in the mRNA hub."""
    hub = get_mrna_hub()
    agent_id = get_central_agent_id(project_id)
    hub.register_agent(agent_id)
    logger.info("Central agent registered: %s", agent_id)


def process_central_agent_messages(
    db: Session,
    project_id: int,
) -> AgentResponse:
    """Process all pending mRNA messages for a project's central agent.

    Called either on a schedule or triggered by incoming personal assistant
    messages. The central agent:
    1. Collects all pending mRNA messages
    2. For task_update messages: marks member activity
    3. Runs risk analysis on the project
    4. Returns a response with risk report if anything changed
    """
    hub = get_mrna_hub()
    agent_id = get_central_agent_id(project_id)
    messages = hub.poll(agent_id)

    if not messages:
        return AgentResponse(
            handled=True,
            message="No pending messages.",
            intent_name="central_idle",
        )

    steps: list[AgentStep] = []
    updated_task_count = 0
    active_members: set[str] = set()

    for msg in messages:
        member_name = msg.payload.get("member_name", "unknown")

        if msg.message_type == MSG_TASK_UPDATE:
            updated_task_count += 1
            active_members.add(member_name)
            steps.append(AgentStep(
                thought=f"Received task_update from {member_name}",
                tool_name="process_mRNA",
                tool_args={"message_type": msg.message_type, "sender": msg.sender_agent_id},
                tool_result=f"Task updated by {member_name}",
            ))

        elif msg.message_type == MSG_ALERT_ACK:
            # Project owner acknowledged an alert
            steps.append(AgentStep(
                thought="Alert acknowledged by project owner",
                tool_name="process_mRNA",
                tool_args={"message_type": msg.message_type},
                tool_result=f"Alert {msg.payload.get('alert_id')} acknowledged",
            ))

        elif msg.message_type == MSG_RISK_QUERY:
            # Project owner explicitly asked for risk analysis
            steps.append(AgentStep(
                thought="Risk query requested by project owner",
                tool_name="process_mRNA",
                tool_args={"message_type": msg.message_type},
                tool_result="Triggering risk analysis",
            ))

    # Always run risk analysis after processing messages
    action_items = list_action_items(db)
    risk_report = DEFAULT_TOOL_REGISTRY.execute(
        ANALYZE_RISK, db=db, project_id=project_id, items=action_items
    )

    steps.append(AgentStep(
        thought="Running project risk analysis after processing messages",
        tool_name=ANALYZE_RISK,
        tool_args={"project_id": project_id},
        tool_result=json.dumps({
            "risk_score": risk_report.risk_score,
            "overdue_count": risk_report.overdue_count,
            "blocked_count": risk_report.blocked_count,
            "conclusion": risk_report.conclusion,
        }, ensure_ascii=False),
    ))

    # Build response message
    member_list = ", ".join(sorted(active_members)) if active_members else "无"
    message = (
        f"已处理 {len(messages)} 条项目消息。\n"
        f"活跃成员: {member_list}\n"
        f"风险评分: {risk_report.risk_score}/100\n"
        f"{risk_report.conclusion}"
    )

    return AgentResponse(
        handled=True,
        message=message,
        steps=steps,
        risk_report=risk_report,
        intent_name="central_analysis",
        intent_filters={"project_id": str(project_id), "messages_processed": str(len(messages))},
    )


def send_alert_to_owner(
    db: Session,
    project_id: int,
    alert_type: str,
    severity: str,
    message: str,
    owner_chat_id: str,
) -> dict:
    """Send an alert from central agent to the project owner.

    This creates an mRNA message from central → owner's personal assistant,
    which can then be delivered through the messaging channel.
    """
    hub = get_mrna_hub()
    agent_id = get_central_agent_id(project_id)

    envelope = mRNAEnvelope(
        sender_agent_id=agent_id,
        receiver_agent_id=f"personal:owner-{project_id}",
        message_type=MSG_RISK_QUERY,
        payload={
            "alert_type": alert_type,
            "severity": severity,
            "message": message,
        },
    )
    hub.send(envelope)

    return {
        "status": "sent",
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
    }
