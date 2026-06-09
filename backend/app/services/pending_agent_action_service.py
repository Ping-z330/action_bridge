import json
from datetime import timedelta
import re

from sqlalchemy.orm import Session

from app.core.time import ensure_utc, utc_now
from app.models.pending_agent_action import PendingAgentAction


# 用户确认/取消待执行动作时常用的口语词。
CONFIRM_WORDS = {"确认", "确定", "是的", "是", "可以", "ok", "OK", "Ok", "好", "好的"}
CANCEL_WORDS = {"取消", "不用", "算了", "不用了", "撤销", "放弃"}

# 待确认动作的有效期，超过后自动失效。
PENDING_ACTION_TTL_MINUTES = 30

# 识别中文自然语言截止时间的正则。
DEADLINE_PATTERN = (
    r"(?:今天|今日|明天|后天|本周[一二三四五六日天]|下周[一二三四五六日天]|"
    r"周[一二三四五六日天]|星期[一二三四五六日天]|"
    r"\d{4}-\d{1,2}-\d{1,2}|\d{4}年\d{1,2}月\d{1,2}日)"
    r"(?:\s*(?:上午|中午|下午|晚上|今晚|下班前|晚些时候|"
    r"\d{1,2}(?::|：|点)\d{0,2}))?(?:前|之前)?"
)


def detect_confirmation_message(message: str) -> str | None:
    # 判断用户回复是不是“确认”或“取消”。
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
    # 暂存一个“创建任务”的待确认动作。
    # 保存前先取消同一 chat 里旧的 pending 动作，避免多个确认项互相冲突。
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
    reference_note: str = "",
) -> PendingAgentAction:
    # 暂存一个“修改任务截止时间”的待确认动作。
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
                "reference_note": reference_note,
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
    reference_note: str = "",
) -> PendingAgentAction:
    # 暂存一个“修改任务负责人”的待确认动作。
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
                "reference_note": reference_note,
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
    # 获取某个聊天里最新的未过期待确认动作。
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
        # 过期的动作会标记为 expired，并且不再返回给调用方。
        pending.status = "expired"
        db.commit()
        return None

    return pending


def resolve_pending_action(db: Session, pending: PendingAgentAction, status: str) -> None:
    # 把待确认动作标记成 confirmed / cancelled / expired 等最终状态。
    pending.status = status
    db.commit()


def cancel_pending_actions(db: Session, chat_id: str) -> int:
    # 取消某个聊天里所有还在 pending 的动作。
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
    # 读取待确认动作的 JSON payload，并统一转成字符串字典。
    data = json.loads(pending.payload_json)
    return {key: str(value) for key, value in data.items()}


def detect_pending_revision(message: str, pending: PendingAgentAction) -> dict[str, str] | None:
    # 用户在确认前可能说“改成明天”“负责人换张三”，这里识别这些修改。
    normalized = message.strip()
    if not normalized:
        return None

    if pending.action_type == "update_task_deadline":
        deadline = _extract_deadline_revision(normalized)
        return {"new_deadline": deadline} if deadline else None

    if pending.action_type == "update_task_owner":
        owner_name = _extract_owner_revision(normalized)
        return {"new_owner_name": owner_name} if owner_name else None

    if pending.action_type == "create_task":
        deadline = _extract_deadline_revision(normalized)
        if deadline:
            return {"deadline": deadline}

        owner_name = _extract_owner_revision(normalized)
        if owner_name:
            return {"owner_name": owner_name}

        title = _extract_title_revision(normalized)
        if title:
            return {"title": title}

    return None


def update_pending_payload(
    db: Session,
    pending: PendingAgentAction,
    updates: dict[str, str],
) -> dict[str, str]:
    # 把用户补充/修正的信息写回待确认动作 payload。
    payload = load_pending_payload(pending)
    payload.update({key: value for key, value in updates.items() if value})
    pending.payload_json = json.dumps(payload, ensure_ascii=False)
    db.commit()
    db.refresh(pending)
    return payload


def _extract_deadline_revision(message: str) -> str | None:
    # 从用户修正话术里提取新的截止时间。
    patterns = (
        rf"(?:截止时间|截止日期)?\s*(?:改成|改为|改到|调整到|设置为|换成|延期到|延到)\s*(?P<deadline>{DEADLINE_PATTERN})",
        rf"^(?P<deadline>{DEADLINE_PATTERN})$",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return _clean_field(match.group("deadline"))
    return None


def _extract_owner_revision(message: str) -> str | None:
    # 从用户修正话术里提取新的负责人。
    patterns = (
        r"(?:负责人)?\s*(?:改成|改为|换成|转给|交给|分配给)\s*(?P<owner>.{1,20}?)(?:负责)?$",
        r"负责人\s*(?P<owner>.{1,20})$",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return _clean_field(match.group("owner"))
    return None


def _extract_title_revision(message: str) -> str | None:
    # 从用户修正话术里提取新的任务标题。
    patterns = (
        r"(?:任务目标|任务内容|任务|标题)\s*(?:改成|改为|换成)\s*(?P<title>.{2,80})$",
        r"改成\s*(?P<title>.{2,80})$",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            title = _clean_field(match.group("title"))
            if not re.search(DEADLINE_PATTERN, title):
                return title
    return None


def _clean_field(value: str) -> str:
    # 清理字段两端的空格和常见中文标点。
    return value.strip(" ，。！？：:；;、")
