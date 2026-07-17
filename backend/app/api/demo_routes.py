"""Demo API — simulate A2A multi-agent collaboration.

POST /api/demo/member-message  →  simulate one member reporting progress
GET  /api/demo/mrna-feed        →  read recent mRNA messages
GET  /api/demo/project-status   →  aggregated project view for dashboard
"""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.central_agent import process_central_agent_messages, register_central_agent
from app.services.plan_service import add_member, get_member_by_chat_id, get_member_by_name
from app.agent.mrna_protocol import get_mrna_hub
from app.agent.personal_assistant import handle_personal_message
from app.db.session import get_db
from app.services.meeting_service import list_action_items
from app.services.agent_trace_service import list_agent_trace_logs
from app.agent.tool_registry import DEFAULT_TOOL_REGISTRY
from app.agent.tool_adapters import ANALYZE_RISK

demo_router = APIRouter(prefix="/api/demo")


class RegisterMemberRequest(BaseModel):
    name: str
    chat_id: str
    project_id: int = 1


@demo_router.post("/register-member")
def demo_register_member(payload: RegisterMemberRequest, db: Session = Depends(get_db)):
    """Register a Feishu user as a project member."""
    existing = get_member_by_chat_id(db, payload.chat_id)
    if existing:
        existing.name = payload.name  # 允许改名
        db.commit()
        return {"status": "updated", "member": {"name": existing.name, "chat_id": existing.chat_id, "project_id": existing.project_id}}

    # Also check if member with same name exists (Demo page simulation)
    existing_name = get_member_by_name(db, payload.name)
    if existing_name:
        # Update chat_id if member exists by name
        existing_name.chat_id = payload.chat_id
        db.commit()
        return {"status": "updated", "member": {"name": existing_name.name, "chat_id": payload.chat_id, "project_id": existing_name.project_id}}

    member = add_member(db, project_id=payload.project_id, name=payload.name, chat_id=payload.chat_id)
    return {"status": "registered", "member": {"id": member.id, "name": member.name, "chat_id": member.chat_id, "project_id": member.project_id}}


class DemoMemberMessage(BaseModel):
    member_name: str
    message: str
    project_id: int = 1


class DemoMessageResponse(BaseModel):
    status: str
    member_name: str
    message: str
    agent_reply: str
    mrna_sent: bool
    steps: list[dict]


@demo_router.post("/member-message")
def demo_member_message(payload: DemoMemberMessage, db: Session = Depends(get_db)) -> DemoMessageResponse:
    """Simulate a project member chatting with their personal AI assistant."""
    if not payload.message.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is required")

    # Ensure central agent is registered for this project
    register_central_agent(payload.project_id)

    # Route through personal assistant — same code path as real Feishu private chat
    response = handle_personal_message(
        db=db,
        message=payload.message.strip(),
        member_name=payload.member_name,
        member_chat_id=f"demo-{payload.member_name}",
        project_id=payload.project_id,
    )

    # Run central agent to process any new mRNA messages
    central_response = process_central_agent_messages(db, payload.project_id)

    # Check if mRNA was sent
    mrna_sent = response.executed_action is not None or len(response.items) > 0

    return DemoMessageResponse(
        status="ok",
        member_name=payload.member_name,
        message=payload.message.strip(),
        agent_reply=response.message,
        mrna_sent=mrna_sent,
        steps=[s.to_dict() for s in response.steps],
    )


@demo_router.get("/mrna-feed")
def demo_mrna_feed() -> list[dict]:
    """Return recent mRNA messages for the demo feed."""
    hub = get_mrna_hub()
    messages = hub.get_all_sent()
    return [
        {
            "sender": m.sender_agent_id,
            "receiver": m.receiver_agent_id,
            "type": m.message_type,
            "payload": m.payload,
            "timestamp": m.timestamp,
        }
        for m in messages[-20:]  # Last 20 messages
    ]


@demo_router.get("/project-status")
def demo_project_status(db: Session = Depends(get_db)) -> dict:
    """Aggregated project status for the demo dashboard."""
    items = list_action_items(db)

    total = len(items)
    completed = len([i for i in items if i.status == "completed"])
    in_progress = len([i for i in items if i.status == "in_progress"])
    failed = len([i for i in items if i.status in ("failed", "blocked")])
    pending = total - completed - in_progress - failed

    # Per-member stats
    members: dict[str, dict] = {}
    for item in items:
        owner = item.owner_name
        if owner in ("Pending confirmation", "Unassigned", ""):
            continue
        if owner not in members:
            members[owner] = {"name": owner, "total": 0, "completed": 0, "failed": 0}
        members[owner]["total"] += 1
        if item.status == "completed":
            members[owner]["completed"] += 1
        if item.status in ("failed", "blocked"):
            members[owner]["failed"] += 1

    member_list = []
    for m in members.values():
        rate = round(m["completed"] / m["total"] * 100) if m["total"] else 0
        member_list.append({**m, "completion_rate": rate})
    member_list.sort(key=lambda m: m["completion_rate"], reverse=True)

    # Risk report
    risk_report = DEFAULT_TOOL_REGISTRY.execute(ANALYZE_RISK, db=db, project_id=1, items=items)

    return {
        "total_tasks": total,
        "completed": completed,
        "in_progress": in_progress,
        "pending": pending,
        "failed": failed,
        "completion_rate": round(completed / total * 100, 1) if total else 0,
        "risk_score": risk_report.risk_score if risk_report else 0,
        "risk_conclusion": risk_report.conclusion if risk_report else "",
        "risks": [{"task_id": r.task_id, "title": r.task_title, "severity": r.severity, "description": r.description} for r in risk_report.risks[:5]] if risk_report else [],
        "members": member_list,
    }
