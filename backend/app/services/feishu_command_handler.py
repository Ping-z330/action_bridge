from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.agent.orchestrator import send_task_not_found_response
from app.services.feishu_delivery import FeishuDeliveryPort, get_default_feishu_delivery
from app.services.feishu_event_log_service import mark_feishu_event_finished
from app.services.feishu_service import FeishuDeliveryError
from app.services.follow_up_service import record_follow_up_reply
from app.services.meeting_service import (
    complete_action_item,
    list_action_items,
    update_action_item_status,
)
from app.services.memory_service import forget_alias, list_memory_aliases, remember_alias


def handle_fixed_feishu_command(
    db: Session,
    *,
    done_command: Any | None,
    task_command: Any | None,
    tasks_command: Any | None,
    help_command: Any | None,
    remember_command: Any | None,
    memory_command: Any | None,
    forget_command: Any | None,
    follow_up_reply: Any | None,
    dedup_key: str | None,
    reply_chat_id: str | None,
    delivery: FeishuDeliveryPort | None = None,
) -> dict[str, Any] | None:
    delivery = delivery or get_default_feishu_delivery()
    if done_command:
        return _handle_done_command(db, done_command, dedup_key, reply_chat_id, delivery)
    if task_command:
        return _handle_task_command(db, task_command, dedup_key, reply_chat_id, delivery)
    if tasks_command:
        return _handle_tasks_command(db, tasks_command, dedup_key, reply_chat_id, delivery)
    if help_command:
        return _handle_help_command(db, dedup_key, reply_chat_id, delivery)
    if remember_command:
        return _handle_remember_command(db, remember_command, dedup_key, reply_chat_id, delivery)
    if memory_command:
        return _handle_memory_command(db, dedup_key, reply_chat_id, delivery)
    if forget_command:
        return _handle_forget_command(db, forget_command, dedup_key, reply_chat_id, delivery)
    if follow_up_reply:
        return _handle_follow_up_reply(db, follow_up_reply, dedup_key, reply_chat_id, delivery)
    return None


def _handle_done_command(
    db: Session,
    done_command: Any,
    dedup_key: str | None,
    reply_chat_id: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    action_item = complete_action_item(db, done_command.action_item_id)
    if not action_item:
        return send_task_not_found_response(done_command.action_item_id, dedup_key, reply_chat_id, db, delivery)

    try:
        delivery.send_action_item_completed_notice(
            action_item.id,
            action_item.title,
            action_item.owner_name,
            receive_id=reply_chat_id,
        )
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "completed",
            "action_item_id": action_item.id,
            "message": f"Action item completed, but Feishu notice delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "completed",
        "action_item_id": action_item.id,
        "message": "Action item marked as completed.",
    }


def _handle_task_command(
    db: Session,
    task_command: Any,
    dedup_key: str | None,
    reply_chat_id: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    action_item = next(
        (item for item in list_action_items(db) if item.id == task_command.action_item_id),
        None,
    )
    if not action_item:
        return send_task_not_found_response(task_command.action_item_id, dedup_key, reply_chat_id, db, delivery)

    try:
        delivery.send_task_detail_summary(action_item, receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "task_found",
            "action_item_id": action_item.id,
            "message": f"Task detail found, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "task_found",
        "action_item_id": action_item.id,
        "message": "Task detail sent.",
    }


def _handle_tasks_command(
    db: Session,
    tasks_command: Any,
    dedup_key: str | None,
    reply_chat_id: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    open_tasks = [
        item
        for item in list_action_items(db)
        if item.status in {"pending", "in_progress", "failed"}
    ]

    try:
        delivery.send_open_tasks_summary(open_tasks[: tasks_command.limit], receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "listed",
            "task_count": len(open_tasks),
            "message": f"Open tasks listed, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "listed",
        "task_count": len(open_tasks),
        "message": "Open tasks summary sent.",
    }


def _handle_help_command(
    db: Session,
    dedup_key: str | None,
    reply_chat_id: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    try:
        delivery.send_help_card(receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "help_sent",
            "message": f"Help card generated, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "help_sent",
        "message": "Help card sent.",
    }


def _handle_remember_command(
    db: Session,
    remember_command: Any,
    dedup_key: str | None,
    reply_chat_id: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    item = remember_alias(
        db,
        remember_command.alias,
        remember_command.target,
        remember_command.memory_type,
    )
    try:
        delivery.send_memory_saved_notice(item, receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "memory_saved",
            "alias": item.alias,
            "target": item.target,
            "message": f"Memory saved, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "memory_saved",
        "alias": item.alias,
        "target": item.target,
        "message": "Memory alias saved.",
    }


def _handle_memory_command(
    db: Session,
    dedup_key: str | None,
    reply_chat_id: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    items = list_memory_aliases(db)
    try:
        delivery.send_memory_list_summary(items, receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "memory_listed",
            "memory_count": len(items),
            "message": f"Memory listed, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "memory_listed",
        "memory_count": len(items),
        "message": "Memory aliases listed.",
    }


def _handle_forget_command(
    db: Session,
    forget_command: Any,
    dedup_key: str | None,
    reply_chat_id: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    item = forget_alias(db, forget_command.alias)
    if not item:
        mark_feishu_event_finished(db, dedup_key, "failed")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory alias not found")

    try:
        delivery.send_memory_deleted_notice(item, receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "memory_deleted",
            "alias": item.alias,
            "message": f"Memory deleted, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "memory_deleted",
        "alias": item.alias,
        "message": "Memory alias deleted.",
    }


def _handle_follow_up_reply(
    db: Session,
    follow_up_reply: Any,
    dedup_key: str | None,
    reply_chat_id: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    action_item = update_action_item_status(db, follow_up_reply.action_item_id, follow_up_reply.status)
    if not action_item:
        return send_task_not_found_response(follow_up_reply.action_item_id, dedup_key, reply_chat_id, db, delivery)

    record_follow_up_reply(
        db,
        meeting_id=action_item.meeting_id,
        action_item_id=action_item.id,
        status=follow_up_reply.status,
    )
    try:
        delivery.send_task_detail_summary(action_item, receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "follow_up_replied",
            "action_item_id": action_item.id,
            "target_status": follow_up_reply.status,
            "message": f"Follow-up reply handled, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "follow_up_replied",
        "action_item_id": action_item.id,
        "target_status": follow_up_reply.status,
        "message": "Follow-up reply handled.",
    }
