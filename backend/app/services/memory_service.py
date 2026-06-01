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
    normalized_alias = alias.strip()
    normalized_target = target.strip()
    normalized_type = memory_type.strip() or "alias"

    existing = db.query(MemoryAlias).filter(MemoryAlias.alias == normalized_alias).first()
    if existing:
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
    normalized_alias = alias.strip()
    row = db.query(MemoryAlias).filter(MemoryAlias.alias == normalized_alias).first()
    if not row:
        return None

    item = _to_item(row)
    db.delete(row)
    db.commit()
    return item


def list_memory_aliases(db: Session) -> list[MemoryAliasItem]:
    rows = db.query(MemoryAlias).order_by(MemoryAlias.created_at.desc()).all()
    return [_to_item(row) for row in rows]


def normalize_message_with_memory(db: Session, message: str) -> str:
    normalized = message
    aliases = db.query(MemoryAlias).order_by(MemoryAlias.alias.desc()).all()
    for item in aliases:
        if item.alias and item.alias in normalized:
            normalized = normalized.replace(item.alias, item.target)
    return normalized


def _to_item(row: MemoryAlias) -> MemoryAliasItem:
    return MemoryAliasItem(
        id=row.id,
        alias=row.alias,
        target=row.target,
        memory_type=row.memory_type,
        created_at=ensure_utc(row.created_at),
    )
