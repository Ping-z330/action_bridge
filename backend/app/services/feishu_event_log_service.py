from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.feishu_event_log import FeishuEventLog


def register_feishu_event(db: Session, event_key: str | None, command_type: str) -> bool:
    # 记录飞书事件，用于去重。
    # 返回 True 表示可以继续处理；返回 False 表示这个 event_key 已经处理过。
    if not event_key:
        # 没有事件 key 时无法去重，只能放行。
        return True

    db.add(FeishuEventLog(event_key=event_key, command_type=command_type, status="processing"))
    try:
        db.commit()
    except IntegrityError:
        # event_key 有唯一索引，插入失败通常代表重复事件。
        db.rollback()
        return False

    return True


def mark_feishu_event_finished(db: Session, event_key: str | None, status: str = "finished") -> None:
    # 事件处理完成后更新状态，方便排查飞书回调处理情况。
    if not event_key:
        return

    event_log = db.query(FeishuEventLog).filter(FeishuEventLog.event_key == event_key).first()
    if not event_log:
        return

    event_log.status = status
    db.commit()
