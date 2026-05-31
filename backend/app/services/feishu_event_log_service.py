from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.feishu_event_log import FeishuEventLog


def register_feishu_event(db: Session, event_key: str | None, command_type: str) -> bool:
    if not event_key:
        return True

    db.add(FeishuEventLog(event_key=event_key, command_type=command_type, status="processing"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False

    return True


def mark_feishu_event_finished(db: Session, event_key: str | None, status: str = "finished") -> None:
    if not event_key:
        return

    event_log = db.query(FeishuEventLog).filter(FeishuEventLog.event_key == event_key).first()
    if not event_log:
        return

    event_log.status = status
    db.commit()
