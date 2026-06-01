import json
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.time import ensure_utc, utc_now
from app.models.pending_agent_action import PendingAgentAction


CONFIRM_WORDS = {"确认", "确定", "是的", "是", "可以", "ok", "OK", "Ok", "好", "好的"}
CANCEL_WORDS = {"取消", "不用", "算了", "不用了", "撤销", "放弃"}
PENDING_ACTION_TTL_MINUTES = 30


def detect_confirmation_message(message: str) -> str | None:
    normalized = message.strip()
    if normalized in CONFIRM_WORDS:
        return "confirm"
    if normalized in CANCEL_WORDS:
        return "cancel"
    return None


def save_pending_create_task(
    db: Session,
    chat_id: str,
    title: str,
    owner_name: str,
    deadline: str,
) -> PendingAgentAction:
    cancel_pending_actions(db, chat_id)
    pending = PendingAgentAction(
        chat_id=chat_id,
        action_type="create_task",
        payload_json=json.dumps(
            {
                "title": title,
                "owner_name": owner_name,
                "deadline": deadline,
            },
            ensure_ascii=False,
        ),
        status="pending",
        expires_at=utc_now() + timedelta(minutes=PENDING_ACTION_TTL_MINUTES),
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    return pending


def save_pending_update_task_deadline(
    db: Session,
    chat_id: str,
    action_item_id: int,
    title: str,
    old_deadline: str,
    new_deadline: str,
) -> PendingAgentAction:
    cancel_pending_actions(db, chat_id)
    pending = PendingAgentAction(
        chat_id=chat_id,
        action_type="update_task_deadline",
        payload_json=json.dumps(
            {
                "action_item_id": action_item_id,
                "title": title,
                "old_deadline": old_deadline,
                "new_deadline": new_deadline,
            },
            ensure_ascii=False,
        ),
        status="pending",
        expires_at=utc_now() + timedelta(minutes=PENDING_ACTION_TTL_MINUTES),
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    return pending


def save_pending_update_task_owner(
    db: Session,
    chat_id: str,
    action_item_id: int,
    title: str,
    old_owner_name: str,
    new_owner_name: str,
) -> PendingAgentAction:
    cancel_pending_actions(db, chat_id)
    pending = PendingAgentAction(
        chat_id=chat_id,
        action_type="update_task_owner",
        payload_json=json.dumps(
            {
                "action_item_id": action_item_id,
                "title": title,
                "old_owner_name": old_owner_name,
                "new_owner_name": new_owner_name,
            },
            ensure_ascii=False,
        ),
        status="pending",
        expires_at=utc_now() + timedelta(minutes=PENDING_ACTION_TTL_MINUTES),
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    return pending


def get_active_pending_action(db: Session, chat_id: str) -> PendingAgentAction | None:
    pending = (
        db.query(PendingAgentAction)
        .filter(
            PendingAgentAction.chat_id == chat_id,
            PendingAgentAction.status == "pending",
        )
        .order_by(PendingAgentAction.created_at.desc())
        .first()
    )
    if not pending:
        return None

    if ensure_utc(pending.expires_at) <= utc_now():
        pending.status = "expired"
        db.commit()
        return None

    return pending


def resolve_pending_action(db: Session, pending: PendingAgentAction, status: str) -> None:
    pending.status = status
    db.commit()


def cancel_pending_actions(db: Session, chat_id: str) -> int:
    rows = (
        db.query(PendingAgentAction)
        .filter(
            PendingAgentAction.chat_id == chat_id,
            PendingAgentAction.status == "pending",
        )
        .all()
    )
    for row in rows:
        row.status = "cancelled"
    db.commit()
    return len(rows)


def load_pending_payload(pending: PendingAgentAction) -> dict[str, str]:
    data = json.loads(pending.payload_json)
    return {key: str(value) for key, value in data.items()}
