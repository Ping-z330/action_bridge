"""Project plan management: CRUD for projects, members, and tasks.

This is where project plans are stored and retrieved.
The central agent reads from here to know the plan,
and personal assistants update task statuses that feed back here.
"""

import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.action_item import ActionItem
from app.models.alert import Alert
from app.models.member import Member
from app.models.meeting import Meeting
from app.models.project import Project


# ── Project CRUD ────────────────────────────────────────────

def create_project(db: Session, name: str, description: str = "", owner_id: str = "") -> Project:
    """Create a new project."""
    project = Project(name=name, description=description, owner_id=owner_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_project(db: Session, project_id: int) -> Project | None:
    return db.query(Project).filter(Project.id == project_id).first()


def list_projects(db: Session) -> list[Project]:
    return db.query(Project).order_by(Project.created_at.desc()).all()


# ── Member CRUD ─────────────────────────────────────────────

def add_member(db: Session, project_id: int, name: str, chat_id: str = "", role: str = "member") -> Member:
    member = Member(project_id=project_id, name=name, chat_id=chat_id, role=role)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def get_project_members(db: Session, project_id: int) -> list[Member]:
    return db.query(Member).filter(Member.project_id == project_id).all()


def get_member_by_chat_id(db: Session, chat_id: str):
    """Find a project member by their Feishu open_id (chat_id)."""
    return db.query(Member).filter(Member.chat_id == chat_id).first()


def get_member_by_name(db: Session, name: str):
    """Find a project member by name."""
    return db.query(Member).filter(Member.name == name).first()


def update_member_activity(db: Session, member_name: str, project_id: int) -> None:
    """Update the last_active_at timestamp for a member."""
    member = (
        db.query(Member)
        .filter(Member.name == member_name, Member.project_id == project_id)
        .first()
    )
    if member:
        member.last_active_at = datetime.now(UTC)
        db.commit()


def get_inactive_members(db: Session, project_id: int, days_threshold: int = 3) -> list[Member]:
    """Find members who haven't been active for N days."""
    threshold = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        db.query(Member)
        .filter(
            Member.project_id == project_id,
            Member.last_active_at < threshold,
        )
        .all()
    )


# ── Alert CRUD ──────────────────────────────────────────────

def create_alert(
    db: Session,
    project_id: int,
    alert_type: str,
    severity: str,
    message: str,
) -> Alert:
    alert = Alert(
        project_id=project_id,
        alert_type=alert_type,
        severity=severity,
        message=message,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def get_active_alerts(db: Session, project_id: int) -> list[Alert]:
    return (
        db.query(Alert)
        .filter(Alert.project_id == project_id, Alert.status == "active")
        .order_by(Alert.created_at.desc())
        .all()
    )


def acknowledge_alert(db: Session, alert_id: int, acknowledged_by: str = "") -> Alert | None:
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert:
        alert.status = "acknowledged"
        alert.acknowledged_by = acknowledged_by
        db.commit()
        db.refresh(alert)
    return alert


# ── Project Health ──────────────────────────────────────────

def get_project_health(db: Session, project_id: int) -> dict:
    """Get a summary of project health for the dashboard."""
    # For now, aggregate from action_items. Phase 2+ will use proper task model.
    items = (
        db.query(ActionItem)
        .join(Meeting, ActionItem.meeting_id == Meeting.id)
        .all()
    )

    total = len(items)
    completed = len([i for i in items if i.status == "completed"])
    in_progress = len([i for i in items if i.status == "in_progress"])
    pending = len([i for i in items if i.status == "pending"])
    failed = len([i for i in items if i.status in ("failed", "blocked")])

    members = get_project_members(db, project_id)
    alerts = get_active_alerts(db, project_id)

    return {
        "project_id": project_id,
        "total_tasks": total,
        "completed": completed,
        "in_progress": in_progress,
        "pending": pending,
        "failed": failed,
        "completion_rate": round(completed / total * 100, 1) if total else 0.0,
        "member_count": len(members),
        "active_alert_count": len(alerts),
        "alerts": [
            {
                "id": a.id,
                "type": a.alert_type,
                "severity": a.severity,
                "message": a.message,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts[:5]
        ],
    }
