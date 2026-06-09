from sqlalchemy.orm import Session

from app.core.time import ensure_utc
from app.models.memory_alias import MemoryAlias
from app.schemas.memory import MemoryAliasItem


def remember_alias(
    db: Session,
    alias: str,
    target: str,
    memory_type: str = "alias",
) -> MemoryAliasItem:
    # 保存或更新记忆别名，例如“官网” -> “官网改版项目”。
    normalized_alias = alias.strip()
    normalized_target = target.strip()
    normalized_type = memory_type.strip() or "alias"

    existing = db.query(MemoryAlias).filter(MemoryAlias.alias == normalized_alias).first()
    if existing:
        # 同一个别名再次保存时，覆盖它指向的新目标。
        existing.target = normalized_target
        existing.memory_type = normalized_type
        db.commit()
        db.refresh(existing)
        return _to_item(existing)

    row = MemoryAlias(alias=normalized_alias, target=normalized_target, memory_type=normalized_type)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_item(row)


def forget_alias(db: Session, alias: str) -> MemoryAliasItem | None:
    # 删除一个记忆别名；返回被删除的数据，方便飞书提示用户。
    normalized_alias = alias.strip()
    row = db.query(MemoryAlias).filter(MemoryAlias.alias == normalized_alias).first()
    if not row:
        return None

    item = _to_item(row)
    db.delete(row)
    db.commit()
    return item


def list_memory_aliases(db: Session) -> list[MemoryAliasItem]:
    # 按创建时间倒序列出所有记忆别名。
    rows = db.query(MemoryAlias).order_by(MemoryAlias.created_at.desc()).all()
    return [_to_item(row) for row in rows]


def normalize_message_with_memory(db: Session, message: str) -> str:
    # 把用户消息里的别名替换成真实名称，提升 Agent 意图识别准确度。
    normalized = message
    # 较长/字典序靠后的别名先替换，减少短别名误伤长文本的概率。
    aliases = db.query(MemoryAlias).order_by(MemoryAlias.alias.desc()).all()
    for item in aliases:
        if item.alias and item.alias in normalized:
            normalized = normalized.replace(item.alias, item.target)
    return normalized


def _to_item(row: MemoryAlias) -> MemoryAliasItem:
    # ORM 模型转成接口 schema，顺便确保时间带 UTC。
    return MemoryAliasItem(
        id=row.id,
        alias=row.alias,
        target=row.target,
        memory_type=row.memory_type,
        created_at=ensure_utc(row.created_at),
    )
