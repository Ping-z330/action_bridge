from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.agent.orchestrator import handle_agent_text_event
from app.db.session import SessionLocal, get_db
from app.schemas.action_item import ActionItemUpdate, FeishuCardCallbackResponse
from app.schemas.follow_up import FollowUpRunResponse
from app.schemas.meeting import MeetingCreate, MeetingListItem, MeetingResponse
from app.schemas.task import FeishuSendResponse
from app.schemas.task_result import ActionItemListItem
from app.services.feishu_event_log_service import mark_feishu_event_finished, register_feishu_event
from app.services.feishu_event_router import parse_feishu_event
from app.services.feishu_service import (
    extract_card_callback_action,
    send_action_item_completed_notice,
    send_help_card,
    send_meeting_summary,
    send_memory_deleted_notice,
    send_memory_list_summary,
    send_memory_saved_notice,
    send_open_tasks_summary,
    send_pending_action_notice,
    send_project_progress_summary,
    send_task_create_clarification,
    send_task_create_confirmation,
    send_task_deadline_update_confirmation,
    send_task_detail_summary,
    send_task_not_found_notice,
    send_task_owner_update_confirmation,
)
from app.services.feishu_command_handler import handle_fixed_feishu_command
from app.services.feishu_delivery import FeishuDeliveryPort
from app.services.follow_up_service import run_follow_up_scan
from app.services.meeting_service import (
    complete_action_item,
    create_meeting_with_actions,
    get_meeting_by_id,
    list_action_items,
    list_meetings,
    send_follow_up_to_feishu,
    send_meeting_to_feishu,
    update_action_item,
)

router = APIRouter(prefix="/api")


def _build_feishu_delivery() -> FeishuDeliveryPort:
    return FeishuDeliveryPort(
        send_action_item_completed_notice=send_action_item_completed_notice,
        send_help_card=send_help_card,
        send_memory_deleted_notice=send_memory_deleted_notice,
        send_memory_list_summary=send_memory_list_summary,
        send_memory_saved_notice=send_memory_saved_notice,
        send_open_tasks_summary=send_open_tasks_summary,
        send_pending_action_notice=send_pending_action_notice,
        send_project_progress_summary=send_project_progress_summary,
        send_task_create_clarification=send_task_create_clarification,
        send_task_create_confirmation=send_task_create_confirmation,
        send_task_deadline_update_confirmation=send_task_deadline_update_confirmation,
        send_task_detail_summary=send_task_detail_summary,
        send_task_not_found_notice=send_task_not_found_notice,
        send_task_owner_update_confirmation=send_task_owner_update_confirmation,
    )


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
    try:
        event = parse_feishu_event(payload, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if event.challenge:
        return {"challenge": event.challenge}
    if event.ignored:
        return {"status": "ignored", "message": event.ignored_message}

    delivery = _build_feishu_delivery()
    if not register_feishu_event(db, event.dedup_key, event.command_type):
        return {"status": "duplicated", "message": "Duplicated Feishu event ignored."}

    fixed_response = handle_fixed_feishu_command(
        db,
        done_command=event.done_command,
        task_command=event.task_command,
        tasks_command=event.tasks_command,
        help_command=event.help_command,
        remember_command=event.remember_command,
        memory_command=event.memory_command,
        forget_command=event.forget_command,
        follow_up_reply=event.follow_up_reply,
        dedup_key=event.dedup_key,
        reply_chat_id=event.reply_chat_id,
        delivery=delivery,
    )
    if fixed_response:
        return fixed_response

    if not event.meeting_command and event.agent_preparation:
        return handle_agent_text_event(
            db=db,
            preparation=event.agent_preparation,
            message_text=event.message_text,
            reply_chat_id=event.reply_chat_id,
            pending_chat_id=event.pending_chat_id,
            dedup_key=event.dedup_key,
            delivery=delivery,
        )

    background_tasks.add_task(
        process_feishu_meeting_command,
        event.meeting_command.title,
        event.meeting_command.transcript,
        event.reply_chat_id,
    )
    mark_feishu_event_finished(db, event.dedup_key, "accepted")
    return {
        "status": "accepted",
        "message": "Meeting command accepted and will be processed in background.",
    }
