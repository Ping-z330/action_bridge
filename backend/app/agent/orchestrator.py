from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.agent.graph import run_agent_graph
from app.agent.schemas import AgentResponse
from app.models.pending_agent_action import PendingAgentAction
from app.services.feishu_delivery import FeishuDeliveryPort, get_default_feishu_delivery
from app.services.feishu_event_log_service import mark_feishu_event_finished
from app.services.feishu_service import FeishuDeliveryError
from app.services.meeting_service import (
    create_action_item_from_agent,
    list_action_items,
    update_action_item_deadline,
    update_action_item_owner,
    update_action_item_status,
)
from app.services.pending_agent_action_service import (
    detect_confirmation_message,
    detect_pending_revision,
    get_active_pending_action,
    load_pending_payload,
    resolve_pending_action,
    save_pending_create_task,
    save_pending_update_task_deadline,
    save_pending_update_task_owner,
    update_pending_payload,
)


@dataclass(frozen=True)
class AgentTextPreparation:
    confirmation_action: str | None = None
    active_pending_action: PendingAgentAction | None = None
    pending_revision: dict[str, str] | None = None
    agent_response: AgentResponse | None = None
    ignored: bool = False


def prepare_agent_text_event(
    db: Session,
    message_text: str,
    pending_chat_id: str,
) -> AgentTextPreparation:
    confirmation_action = detect_confirmation_message(message_text)
    active_pending_action = (
        None if confirmation_action else get_active_pending_action(db, pending_chat_id)
    )
    pending_revision = (
        detect_pending_revision(message_text, active_pending_action)
        if active_pending_action
        else None
    )

    if confirmation_action or pending_revision:
        return AgentTextPreparation(
            confirmation_action=confirmation_action,
            active_pending_action=active_pending_action,
            pending_revision=pending_revision,
        )

    if not message_text:
        return AgentTextPreparation(ignored=True)

    agent_response = run_agent_graph(db, message_text)
    if not agent_response.handled:
        return AgentTextPreparation(ignored=True, agent_response=agent_response)

    return AgentTextPreparation(agent_response=agent_response)


def get_agent_command_type(preparation: AgentTextPreparation | None) -> str:
    if not preparation:
        return "agent"
    if preparation.confirmation_action == "confirm":
        return "confirm"
    if preparation.confirmation_action == "cancel":
        return "cancel"
    if preparation.agent_response and preparation.agent_response.intent:
        return preparation.agent_response.intent.name
    return "agent"


def send_task_not_found_response(
    action_item_id: int,
    dedup_key: str | None,
    receive_id: str | None,
    db: Session,
    delivery: FeishuDeliveryPort | None = None,
) -> dict[str, Any]:
    delivery = delivery or get_default_feishu_delivery()
    try:
        delivery.send_task_not_found_notice(action_item_id, receive_id=receive_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "task_not_found",
            "action_item_id": action_item_id,
            "message": f"Action item not found, but Feishu notice delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "task_not_found",
        "action_item_id": action_item_id,
        "message": "Action item not found notice sent.",
    }


def handle_agent_text_event(
    db: Session,
    preparation: AgentTextPreparation,
    message_text: str,
    reply_chat_id: str | None,
    pending_chat_id: str,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort | None = None,
) -> dict[str, Any]:
    delivery = delivery or get_default_feishu_delivery()
    if preparation.confirmation_action:
        return _handle_confirmation(
            db=db,
            confirmation_action=preparation.confirmation_action,
            pending_chat_id=pending_chat_id,
            reply_chat_id=reply_chat_id,
            dedup_key=dedup_key,
            delivery=delivery,
        )

    if preparation.active_pending_action and preparation.pending_revision:
        return _handle_pending_revision(
            db=db,
            pending=preparation.active_pending_action,
            pending_revision=preparation.pending_revision,
            reply_chat_id=reply_chat_id,
            dedup_key=dedup_key,
            delivery=delivery,
        )

    agent_response = preparation.agent_response or _build_agent_response(db, message_text)
    if not agent_response.handled:
        mark_feishu_event_finished(db, dedup_key, "ignored")
        return {"status": "ignored", "message": "No supported command found."}

    if agent_response.intent and agent_response.intent.name == "help":
        return _send_help_response(db, agent_response, reply_chat_id, dedup_key, delivery)

    if agent_response.intent and agent_response.intent.name == "create_task_missing_info":
        return _send_create_task_clarification(db, agent_response, reply_chat_id, dedup_key, delivery)

    if agent_response.intent and agent_response.intent.name == "create_task":
        return _request_create_task_confirmation(
            db=db,
            agent_response=agent_response,
            pending_chat_id=pending_chat_id,
            reply_chat_id=reply_chat_id,
            dedup_key=dedup_key,
            delivery=delivery,
        )

    if agent_response.intent and agent_response.intent.name == "update_task_deadline":
        return _request_deadline_update_confirmation(
            db=db,
            agent_response=agent_response,
            pending_chat_id=pending_chat_id,
            reply_chat_id=reply_chat_id,
            dedup_key=dedup_key,
            delivery=delivery,
        )

    if agent_response.intent and agent_response.intent.name == "update_task_owner":
        return _request_owner_update_confirmation(
            db=db,
            agent_response=agent_response,
            pending_chat_id=pending_chat_id,
            reply_chat_id=reply_chat_id,
            dedup_key=dedup_key,
            delivery=delivery,
        )

    if agent_response.intent and agent_response.intent.name == "update_task_status":
        return _update_task_status(db, agent_response, reply_chat_id, dedup_key, delivery)

    if agent_response.intent and agent_response.intent.name == "summarize_project":
        return _send_project_summary(db, agent_response, reply_chat_id, dedup_key, delivery)

    return _send_query_tasks_result(db, agent_response, reply_chat_id, dedup_key, delivery)


def _build_agent_response(db: Session, message_text: str) -> AgentResponse:
    return run_agent_graph(db, message_text)


def _handle_confirmation(
    db: Session,
    confirmation_action: str,
    pending_chat_id: str,
    reply_chat_id: str | None,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    pending = get_active_pending_action(db, pending_chat_id)
    if not pending:
        mark_feishu_event_finished(db, dedup_key, "ignored")
        try:
            delivery.send_pending_action_notice(
                "ℹ️ 没有待确认操作",
                "当前没有需要确认的操作。你可以重新发送一句创建或修改任务的话。",
                receive_id=reply_chat_id,
            )
        except FeishuDeliveryError:
            pass
        return {"status": "no_pending_action", "message": "No pending action found."}

    if confirmation_action == "cancel":
        resolve_pending_action(db, pending, "cancelled")
        try:
            delivery.send_pending_action_notice(
                "已取消",
                "已取消这次待确认操作。",
                receive_id=reply_chat_id,
            )
        except FeishuDeliveryError as exc:
            mark_feishu_event_finished(db, dedup_key, "finished")
            return {
                "status": "pending_cancelled",
                "message": f"Pending action cancelled, but Feishu delivery failed: {exc}",
            }

        mark_feishu_event_finished(db, dedup_key, "finished")
        return {"status": "pending_cancelled", "message": "Pending action cancelled."}

    payload_data = load_pending_payload(pending)
    if pending.action_type == "create_task":
        action_item = create_action_item_from_agent(
            db,
            title=payload_data["title"],
            owner_name=payload_data["owner_name"],
            deadline=payload_data["deadline"],
        )
        confirmed_intent = "confirm_create_task"
        success_message = "Task created after confirmation."
    elif pending.action_type == "update_task_deadline":
        action_item = update_action_item_deadline(
            db,
            action_item_id=int(payload_data["action_item_id"]),
            deadline=payload_data["new_deadline"],
        )
        if not action_item:
            resolve_pending_action(db, pending, "failed")
            return send_task_not_found_response(
                int(payload_data["action_item_id"]),
                dedup_key,
                reply_chat_id,
                db,
                delivery,
            )
        confirmed_intent = "confirm_update_task_deadline"
        success_message = "Task deadline updated after confirmation."
    elif pending.action_type == "update_task_owner":
        action_item = update_action_item_owner(
            db,
            action_item_id=int(payload_data["action_item_id"]),
            owner_name=payload_data["new_owner_name"],
        )
        if not action_item:
            resolve_pending_action(db, pending, "failed")
            return send_task_not_found_response(
                int(payload_data["action_item_id"]),
                dedup_key,
                reply_chat_id,
                db,
                delivery,
            )
        confirmed_intent = "confirm_update_task_owner"
        success_message = "Task owner updated after confirmation."
    else:
        resolve_pending_action(db, pending, "failed")
        mark_feishu_event_finished(db, dedup_key, "failed")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported pending action")

    resolve_pending_action(db, pending, "confirmed")
    try:
        delivery.send_task_detail_summary(action_item, receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "agent_confirmed",
            "intent": confirmed_intent,
            "action_item_id": action_item.id,
            "message": f"{success_message} Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "agent_confirmed",
        "intent": confirmed_intent,
        "action_item_id": action_item.id,
        "message": success_message,
    }


def _handle_pending_revision(
    db: Session,
    pending: PendingAgentAction,
    pending_revision: dict[str, str],
    reply_chat_id: str | None,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    updated_payload = update_pending_payload(db, pending, pending_revision)
    try:
        if pending.action_type == "create_task":
            delivery.send_task_create_confirmation(
                title=updated_payload["title"],
                owner_name=updated_payload["owner_name"],
                deadline=updated_payload["deadline"],
                receive_id=reply_chat_id,
            )
        elif pending.action_type == "update_task_deadline":
            delivery.send_task_deadline_update_confirmation(
                action_item_id=int(updated_payload["action_item_id"]),
                title=updated_payload["title"],
                old_deadline=updated_payload["old_deadline"],
                new_deadline=updated_payload["new_deadline"],
                receive_id=reply_chat_id,
            )
        elif pending.action_type == "update_task_owner":
            delivery.send_task_owner_update_confirmation(
                action_item_id=int(updated_payload["action_item_id"]),
                title=updated_payload["title"],
                old_owner_name=updated_payload["old_owner_name"],
                new_owner_name=updated_payload["new_owner_name"],
                receive_id=reply_chat_id,
            )
        else:
            mark_feishu_event_finished(db, dedup_key, "failed")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported pending action")
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "pending_revised",
            "action_type": pending.action_type,
            "message": f"Pending action revised, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "pending_revised",
        "action_type": pending.action_type,
        "message": "Pending action revised.",
    }


def _send_help_response(
    db: Session,
    agent_response: AgentResponse,
    reply_chat_id: str | None,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    try:
        delivery.send_help_card(receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "help_sent",
            "intent": agent_response.intent.name if agent_response.intent else "unknown",
            "message": f"Help card generated, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "help_sent",
        "intent": agent_response.intent.name if agent_response.intent else "unknown",
        "message": agent_response.message,
    }


def _send_create_task_clarification(
    db: Session,
    agent_response: AgentResponse,
    reply_chat_id: str | None,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    try:
        delivery.send_task_create_clarification(agent_response.message, receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "task_create_needs_info",
            "intent": agent_response.intent.name if agent_response.intent else "unknown",
            "message": f"{agent_response.message} Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "task_create_needs_info",
        "intent": agent_response.intent.name if agent_response.intent else "unknown",
        "message": agent_response.message,
    }


def _request_create_task_confirmation(
    db: Session,
    agent_response: AgentResponse,
    pending_chat_id: str,
    reply_chat_id: str | None,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    if not agent_response.intent:
        mark_feishu_event_finished(db, dedup_key, "failed")
        return {"status": "ignored", "message": "No task intent generated."}

    save_pending_create_task(
        db,
        chat_id=pending_chat_id,
        title=agent_response.intent.filters["title"],
        owner_name=agent_response.intent.filters["owner_name"],
        deadline=agent_response.intent.filters["deadline"],
    )
    try:
        delivery.send_task_create_confirmation(
            title=agent_response.intent.filters["title"],
            owner_name=agent_response.intent.filters["owner_name"],
            deadline=agent_response.intent.filters["deadline"],
            receive_id=reply_chat_id,
        )
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "task_create_pending",
            "intent": agent_response.intent.name,
            "message": f"Task create confirmation saved, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "task_create_pending",
        "intent": agent_response.intent.name,
        "message": "Task create confirmation requested.",
    }


def _request_deadline_update_confirmation(
    db: Session,
    agent_response: AgentResponse,
    pending_chat_id: str,
    reply_chat_id: str | None,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    if not agent_response.intent:
        mark_feishu_event_finished(db, dedup_key, "failed")
        return {"status": "ignored", "message": "No task intent generated."}

    action_item_id = int(agent_response.intent.filters["action_item_id"])
    new_deadline = agent_response.intent.filters["deadline"]
    action_item = next((item for item in list_action_items(db) if item.id == action_item_id), None)
    if not action_item:
        return send_task_not_found_response(action_item_id, dedup_key, reply_chat_id, db, delivery)

    save_pending_update_task_deadline(
        db,
        chat_id=pending_chat_id,
        action_item_id=action_item_id,
        title=action_item.title,
        old_deadline=action_item.deadline,
        new_deadline=new_deadline,
    )
    try:
        delivery.send_task_deadline_update_confirmation(
            action_item_id=action_item_id,
            title=action_item.title,
            old_deadline=action_item.deadline,
            new_deadline=new_deadline,
            receive_id=reply_chat_id,
        )
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "task_deadline_update_pending",
            "intent": agent_response.intent.name,
            "action_item_id": action_item_id,
            "message": f"Task deadline update confirmation saved, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "task_deadline_update_pending",
        "intent": agent_response.intent.name,
        "action_item_id": action_item_id,
        "message": "Task deadline update confirmation requested.",
    }


def _request_owner_update_confirmation(
    db: Session,
    agent_response: AgentResponse,
    pending_chat_id: str,
    reply_chat_id: str | None,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    if not agent_response.intent:
        mark_feishu_event_finished(db, dedup_key, "failed")
        return {"status": "ignored", "message": "No task intent generated."}

    action_item_id = int(agent_response.intent.filters["action_item_id"])
    new_owner_name = agent_response.intent.filters["owner_name"]
    action_item = next((item for item in list_action_items(db) if item.id == action_item_id), None)
    if not action_item:
        return send_task_not_found_response(action_item_id, dedup_key, reply_chat_id, db, delivery)

    save_pending_update_task_owner(
        db,
        chat_id=pending_chat_id,
        action_item_id=action_item_id,
        title=action_item.title,
        old_owner_name=action_item.owner_name,
        new_owner_name=new_owner_name,
    )
    try:
        delivery.send_task_owner_update_confirmation(
            action_item_id=action_item_id,
            title=action_item.title,
            old_owner_name=action_item.owner_name,
            new_owner_name=new_owner_name,
            receive_id=reply_chat_id,
        )
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "task_owner_update_pending",
            "intent": agent_response.intent.name,
            "action_item_id": action_item_id,
            "message": f"Task owner update confirmation saved, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "task_owner_update_pending",
        "intent": agent_response.intent.name,
        "action_item_id": action_item_id,
        "message": "Task owner update confirmation requested.",
    }


def _update_task_status(
    db: Session,
    agent_response: AgentResponse,
    reply_chat_id: str | None,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    if not agent_response.intent:
        mark_feishu_event_finished(db, dedup_key, "failed")
        return {"status": "ignored", "message": "No task intent generated."}

    action_item_id = int(agent_response.intent.filters["action_item_id"])
    target_status = agent_response.intent.filters["status"]
    action_item = update_action_item_status(db, action_item_id, target_status)
    if not action_item:
        return send_task_not_found_response(action_item_id, dedup_key, reply_chat_id, db, delivery)

    try:
        delivery.send_task_detail_summary(action_item, receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "agent_updated",
            "intent": agent_response.intent.name,
            "action_item_id": action_item.id,
            "target_status": target_status,
            "message": f"Task updated, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "agent_updated",
        "intent": agent_response.intent.name,
        "action_item_id": action_item.id,
        "target_status": target_status,
        "message": "Task status updated.",
    }


def _send_project_summary(
    db: Session,
    agent_response: AgentResponse,
    reply_chat_id: str | None,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    if not agent_response.progress_summary:
        mark_feishu_event_finished(db, dedup_key, "failed")
        return {"status": "ignored", "message": "No project progress summary generated."}

    try:
        delivery.send_project_progress_summary(agent_response.progress_summary, receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "agent_replied",
            "intent": agent_response.intent.name if agent_response.intent else "unknown",
            "task_count": len(agent_response.items),
            "message": f"{agent_response.message} Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "agent_replied",
        "intent": agent_response.intent.name if agent_response.intent else "unknown",
        "task_count": len(agent_response.items),
        "message": agent_response.message,
    }


def _send_query_tasks_result(
    db: Session,
    agent_response: AgentResponse,
    reply_chat_id: str | None,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    try:
        delivery.send_open_tasks_summary(agent_response.items[:10], receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "agent_replied",
            "intent": agent_response.intent.name if agent_response.intent else "unknown",
            "task_count": len(agent_response.items),
            "message": f"{agent_response.message} Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "agent_replied",
        "intent": agent_response.intent.name if agent_response.intent else "unknown",
        "task_count": len(agent_response.items),
        "message": agent_response.message,
    }
