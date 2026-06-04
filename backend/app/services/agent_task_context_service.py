import json

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.agent_task_context import AgentTaskContext
from app.schemas.task_result import ActionItemListItem


def save_recent_task_context(
    db: Session,
    chat_id: str,
    items: list[ActionItemListItem],
    limit: int = 10,
) -> AgentTaskContext:
    item_ids = [item.id for item in items[:limit]]
    context = db.query(AgentTaskContext).filter(AgentTaskContext.chat_id == chat_id).first()
    now = utc_now()
    if context:
        context.item_ids_json = json.dumps(item_ids)
        context.updated_at = now
    else:
        context = AgentTaskContext(
            chat_id=chat_id,
            item_ids_json=json.dumps(item_ids),
            created_at=now,
            updated_at=now,
        )
        db.add(context)
    db.commit()
    db.refresh(context)
    return context


def load_recent_task_ids(db: Session, chat_id: str | None) -> list[int]:
    if not chat_id:
        return []

    context = db.query(AgentTaskContext).filter(AgentTaskContext.chat_id == chat_id).first()
    if not context:
        return []

    try:
        raw_ids = json.loads(context.item_ids_json)
    except json.JSONDecodeError:
        return []

    return [int(item_id) for item_id in raw_ids if isinstance(item_id, int | str) and str(item_id).isdigit()]
