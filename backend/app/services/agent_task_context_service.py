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
    # 保存最近展示给某个聊天的任务 ID 列表。
    # 用途：用户后续说“第一个任务”“刚才那个任务”时，可以解析到具体任务。
    item_ids = [item.id for item in items[:limit]]
    context = db.query(AgentTaskContext).filter(AgentTaskContext.chat_id == chat_id).first()
    now = utc_now()
    if context:
        # 如果这个聊天已经有上下文，就覆盖成最新列表。
        context.item_ids_json = json.dumps(item_ids)
        context.updated_at = now
    else:
        # 如果是第一次保存，就创建新的上下文记录。
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
    # 读取某个聊天最近展示过的任务 ID 列表。
    if not chat_id:
        return []

    context = db.query(AgentTaskContext).filter(AgentTaskContext.chat_id == chat_id).first()
    if not context:
        return []

    try:
        raw_ids = json.loads(context.item_ids_json)
    except json.JSONDecodeError:
        # 数据异常时不抛给调用方，直接当作没有上下文。
        return []

    # 只保留可以转成整数的 ID，避免脏数据影响后续任务引用解析。
    return [int(item_id) for item_id in raw_ids if isinstance(item_id, int | str) and str(item_id).isdigit()]
