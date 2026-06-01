from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.agent.service import handle_agent_message
from app.db.session import SessionLocal, get_db
from app.schemas.action_item import ActionItemUpdate, FeishuCardCallbackResponse
from app.schemas.follow_up import FollowUpRunResponse
from app.schemas.meeting import MeetingCreate, MeetingListItem, MeetingResponse
from app.schemas.task import FeishuSendResponse
from app.schemas.task_result import ActionItemListItem
from app.services.feishu_event_service import (
    extract_challenge,
    extract_done_command,
    extract_event_dedup_key,
    extract_forget_command,
    extract_help_command,
    extract_message_text,
    extract_memory_command,
    extract_meeting_command,
    extract_remember_command,
    extract_reply_chat_id,
    extract_task_command,
    extract_tasks_command,
)
from app.services.feishu_event_log_service import mark_feishu_event_finished, register_feishu_event
from app.services.feishu_service import (
    FeishuDeliveryError,
    extract_card_callback_action,
    send_action_item_completed_notice,
    send_help_card,
    send_meeting_summary,
    send_memory_deleted_notice,
    send_memory_list_summary,
    send_memory_saved_notice,
    send_open_tasks_summary,
    send_project_progress_summary,
    send_task_create_clarification,
    send_task_detail_summary,
)
from app.services.follow_up_service import run_follow_up_scan
from app.services.meeting_service import (
    complete_action_item,
    create_action_item_from_agent,
    create_meeting_with_actions,
    get_meeting_by_id,
    list_action_items,
    list_meetings,
    send_follow_up_to_feishu,
    send_meeting_to_feishu,
    update_action_item,
    update_action_item_status,
)
from app.services.memory_service import (
    forget_alias,
    list_memory_aliases,
    normalize_message_with_memory,
    remember_alias,
)

router = APIRouter(prefix="/api")


def process_feishu_meeting_command(title: str, transcript: str, receive_id: str | None = None) -> None:
    db = SessionLocal()
    try:
        meeting = create_meeting_with_actions(
            db,
            MeetingCreate(title=title, transcript=transcript),
        )
        send_meeting_summary(meeting, receive_id=receive_id)
    finally:
        db.close()


@router.post("/meetings", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
def create_meeting(payload: MeetingCreate, db: Session = Depends(get_db)) -> MeetingResponse:
    try:
        return create_meeting_with_actions(db, payload)
    except OperationalError as exc:
        detail = "Database is temporarily locked. Please retry in a few seconds."
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail) from exc


@router.get("/meetings", response_model=list[MeetingListItem])
def get_meetings(db: Session = Depends(get_db)) -> list[MeetingListItem]:
    return list_meetings(db)


@router.get("/action-items", response_model=list[ActionItemListItem])
def get_action_items(db: Session = Depends(get_db)) -> list[ActionItemListItem]:
    return list_action_items(db)


@router.get("/meetings/{meeting_id}", response_model=MeetingResponse)
def get_meeting(meeting_id: int, db: Session = Depends(get_db)) -> MeetingResponse:
    meeting = get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return meeting


@router.post("/meetings/{meeting_id}/send-feishu", response_model=FeishuSendResponse)
def send_to_feishu(meeting_id: int, db: Session = Depends(get_db)) -> FeishuSendResponse:
    response = send_meeting_to_feishu(db, meeting_id)
    if not response:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return response


@router.post("/meetings/{meeting_id}/follow-up", response_model=FeishuSendResponse)
def send_follow_up(meeting_id: int, db: Session = Depends(get_db)) -> FeishuSendResponse:
    response = send_follow_up_to_feishu(db, meeting_id)
    if not response:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return response


@router.post("/follow-ups/run", response_model=FollowUpRunResponse)
def run_follow_ups(db: Session = Depends(get_db)) -> FollowUpRunResponse:
    return run_follow_up_scan(db)


@router.patch("/action-items/{action_item_id}", response_model=MeetingResponse)
def patch_action_item(
    action_item_id: int,
    payload: ActionItemUpdate,
    db: Session = Depends(get_db),
) -> MeetingResponse:
    meeting = update_action_item(db, action_item_id, payload)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found")
    return meeting


@router.post("/feishu/card-callback")
def handle_feishu_card_callback(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
) -> FeishuCardCallbackResponse | dict[str, str]:
    if "challenge" in payload:
        return {"challenge": payload["challenge"]}

    action_item_id, action = extract_card_callback_action(payload)
    if action_item_id is None or action != "complete_action_item":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported Feishu card action")

    action_item = complete_action_item(db, action_item_id)
    if not action_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found")

    return FeishuCardCallbackResponse(
        status="ok",
        message="行动项已标记为完成。",
        action_item_id=action_item.id,
    )


@router.post("/feishu/events")
def handle_feishu_events(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    challenge = extract_challenge(payload)
    if challenge:
        return {"challenge": challenge}

    reply_chat_id = extract_reply_chat_id(payload)

    try:
        done_command = extract_done_command(payload)
        task_command = extract_task_command(payload)
        tasks_command = extract_tasks_command(payload)
        help_command = extract_help_command(payload)
        remember_command = extract_remember_command(payload)
        memory_command = extract_memory_command(payload)
        forget_command = extract_forget_command(payload)
        meeting_command = extract_meeting_command(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if (
        not done_command
        and not task_command
        and not tasks_command
        and not help_command
        and not remember_command
        and not memory_command
        and not forget_command
        and not meeting_command
    ):
        message_text = extract_message_text(payload)
        if not message_text:
            return {"status": "ignored", "message": "No supported command found."}

        normalized_message = normalize_message_with_memory(db, message_text)
        agent_response = handle_agent_message(normalized_message, list_action_items(db))
        if not agent_response.handled:
            return {"status": "ignored", "message": "No supported command found."}

    dedup_key = extract_event_dedup_key(payload)
    command_type = (
        "done"
        if done_command
        else "task"
        if task_command
        else "tasks"
        if tasks_command
        else "help"
        if help_command
        else "remember"
        if remember_command
        else "memory"
        if memory_command
        else "forget"
        if forget_command
        else "meeting"
        if meeting_command
        else agent_response.intent.name
        if agent_response.intent
        else "agent"
    )
    if not register_feishu_event(db, dedup_key, command_type):
        return {"status": "duplicated", "message": "Duplicated Feishu event ignored."}

    if done_command:
        action_item = complete_action_item(db, done_command.action_item_id)
        if not action_item:
            mark_feishu_event_finished(db, dedup_key, "failed")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found")

        try:
            send_action_item_completed_notice(
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

    if task_command:
        action_item = next(
            (item for item in list_action_items(db) if item.id == task_command.action_item_id),
            None,
        )
        if not action_item:
            mark_feishu_event_finished(db, dedup_key, "failed")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found")

        try:
            send_task_detail_summary(action_item, receive_id=reply_chat_id)
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

    if tasks_command:
        open_tasks = [
            item
            for item in list_action_items(db)
            if item.status in {"pending", "in_progress", "failed"}
        ]

        try:
            send_open_tasks_summary(open_tasks[: tasks_command.limit], receive_id=reply_chat_id)
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

    if help_command:
        try:
            send_help_card(receive_id=reply_chat_id)
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

    if remember_command:
        item = remember_alias(
            db,
            remember_command.alias,
            remember_command.target,
            remember_command.memory_type,
        )
        try:
            send_memory_saved_notice(item, receive_id=reply_chat_id)
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

    if memory_command:
        items = list_memory_aliases(db)
        try:
            send_memory_list_summary(items, receive_id=reply_chat_id)
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

    if forget_command:
        item = forget_alias(db, forget_command.alias)
        if not item:
            mark_feishu_event_finished(db, dedup_key, "failed")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory alias not found")

        try:
            send_memory_deleted_notice(item, receive_id=reply_chat_id)
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

    if not meeting_command:
        message_text = extract_message_text(payload) or ""
        normalized_message = normalize_message_with_memory(db, message_text)
        agent_response = handle_agent_message(normalized_message, list_action_items(db))
        if not agent_response.handled:
            mark_feishu_event_finished(db, dedup_key, "ignored")
            return {"status": "ignored", "message": "No supported command found."}

        if agent_response.intent and agent_response.intent.name == "help":
            try:
                send_help_card(receive_id=reply_chat_id)
            except FeishuDeliveryError as exc:
                mark_feishu_event_finished(db, dedup_key, "finished")
                return {
                    "status": "help_sent",
                    "intent": agent_response.intent.name,
                    "message": f"Help card generated, but Feishu delivery failed: {exc}",
                }

            mark_feishu_event_finished(db, dedup_key, "finished")
            return {
                "status": "help_sent",
                "intent": agent_response.intent.name,
                "message": agent_response.message,
            }

        if agent_response.intent and agent_response.intent.name == "create_task_missing_info":
            try:
                send_task_create_clarification(agent_response.message, receive_id=reply_chat_id)
            except FeishuDeliveryError as exc:
                mark_feishu_event_finished(db, dedup_key, "finished")
                return {
                    "status": "task_create_needs_info",
                    "intent": agent_response.intent.name,
                    "message": f"{agent_response.message} Feishu delivery failed: {exc}",
                }

            mark_feishu_event_finished(db, dedup_key, "finished")
            return {
                "status": "task_create_needs_info",
                "intent": agent_response.intent.name,
                "message": agent_response.message,
            }

        if agent_response.intent and agent_response.intent.name == "create_task":
            action_item = create_action_item_from_agent(
                db,
                title=agent_response.intent.filters["title"],
                owner_name=agent_response.intent.filters["owner_name"],
                deadline=agent_response.intent.filters["deadline"],
            )
            try:
                send_task_detail_summary(action_item, receive_id=reply_chat_id)
            except FeishuDeliveryError as exc:
                mark_feishu_event_finished(db, dedup_key, "finished")
                return {
                    "status": "agent_created",
                    "intent": agent_response.intent.name,
                    "action_item_id": action_item.id,
                    "message": f"Task created, but Feishu delivery failed: {exc}",
                }

            mark_feishu_event_finished(db, dedup_key, "finished")
            return {
                "status": "agent_created",
                "intent": agent_response.intent.name,
                "action_item_id": action_item.id,
                "message": "Task created.",
            }

        if agent_response.intent and agent_response.intent.name == "update_task_status":
            action_item_id = int(agent_response.intent.filters["action_item_id"])
            target_status = agent_response.intent.filters["status"]
            action_item = update_action_item_status(db, action_item_id, target_status)
            if not action_item:
                mark_feishu_event_finished(db, dedup_key, "failed")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found")

            try:
                send_task_detail_summary(action_item, receive_id=reply_chat_id)
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

        if agent_response.intent and agent_response.intent.name == "summarize_project":
            if not agent_response.progress_summary:
                mark_feishu_event_finished(db, dedup_key, "failed")
                return {"status": "ignored", "message": "No project progress summary generated."}

            try:
                send_project_progress_summary(agent_response.progress_summary, receive_id=reply_chat_id)
            except FeishuDeliveryError as exc:
                mark_feishu_event_finished(db, dedup_key, "finished")
                return {
                    "status": "agent_replied",
                    "intent": agent_response.intent.name,
                    "task_count": len(agent_response.items),
                    "message": f"{agent_response.message} Feishu delivery failed: {exc}",
                }

            mark_feishu_event_finished(db, dedup_key, "finished")
            return {
                "status": "agent_replied",
                "intent": agent_response.intent.name,
                "task_count": len(agent_response.items),
                "message": agent_response.message,
            }

        try:
            send_open_tasks_summary(agent_response.items[:10], receive_id=reply_chat_id)
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

    background_tasks.add_task(
        process_feishu_meeting_command,
        meeting_command.title,
        meeting_command.transcript,
        reply_chat_id,
    )
    mark_feishu_event_finished(db, dedup_key, "accepted")
    return {
        "status": "accepted",
        "message": "Meeting command accepted and will be processed in background.",
    }
