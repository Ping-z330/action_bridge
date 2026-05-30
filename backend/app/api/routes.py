from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.action_item import ActionItemUpdate, FeishuCardCallbackResponse
from app.schemas.follow_up import FollowUpRunResponse
from app.schemas.meeting import MeetingCreate, MeetingListItem, MeetingResponse
from app.schemas.task import FeishuSendResponse
from app.schemas.task_result import ActionItemListItem
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
from app.services.feishu_service import extract_card_callback_action

router = APIRouter(prefix="/api")


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
