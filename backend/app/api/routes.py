"""FastAPI route definitions for ActionBridge.

这个文件是后端 API 的入口层，主要负责：
1. 定义前端可以调用的 HTTP 接口。
2. 把请求参数交给 service 层处理。
3. 把 service 返回的数据整理成前端/飞书需要的响应。

注意：这里尽量不写复杂业务逻辑，真正的业务处理通常放在 `services/` 或 `agent/` 目录。
"""

from typing import Any

# FastAPI路由层文件

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

# 导入应用内部的各种服务和工具，包括数据库会话、会议服务、飞书事件处理、代理图执行等，这些都是实现业务逻辑的核心组件
from app.agent.graph import run_agent_graph
from app.agent.orchestrator import handle_agent_text_event
from app.db.session import SessionLocal, get_db
from app.schemas.action_item import ActionItemUpdate, FeishuCardCallbackResponse
from app.schemas.agent_trace import AgentDebugRunRequest, AgentDebugRunResponse, AgentTraceLogItem
from app.schemas.follow_up import FollowUpRunResponse
from app.schemas.meeting import MeetingCreate, MeetingListItem, MeetingResponse
from app.schemas.task import FeishuSendResponse
from app.schemas.task_result import ActionItemListItem
from app.services.feishu_event_log_service import mark_feishu_event_finished, register_feishu_event
from app.services.feishu_event_router import parse_feishu_event
from app.agent.personal_assistant import handle_personal_message, build_personal_assistant_response
from app.services.plan_service import get_member_by_chat_id
from app.services.feishu_service import (
    extract_card_callback_action,
    send_text_reply,
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
from app.services.agent_trace_service import get_latest_agent_trace_log, list_agent_trace_logs, parse_trace_filters
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

# 说明文件里的所有接口都会以/api开头
router = APIRouter(prefix="/api")


def _extract_chat_type(payload: dict) -> str | None:
    """Extract chat_type from Feishu raw payload."""
    try:
        return payload.get("event", {}).get("message", {}).get("chat_type")
    except Exception:
        return None


def _extract_sender_open_id(payload: dict) -> str | None:
    """Extract sender open_id from Feishu raw payload."""
    try:
        return payload.get("event", {}).get("sender", {}).get("sender_id", {}).get("open_id")
    except Exception:
        return None


# 构建一个 FeishuDeliveryPort 实例，封装了所有发送消息到飞书的函数，
# 这样在处理飞书事件时就可以通过这个接口来发送各种类型的消息，而不需要直接依赖具体的发送函数
def _build_feishu_delivery() -> FeishuDeliveryPort:
    """构建飞书消息发送工具箱，供命令处理器和 Agent 编排器使用。"""

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


# 在后台任务中处理 `/meeting` 命令。
# 因为会议解析可能调用 LLM 或做较多数据库写入，所以飞书事件入口先返回 accepted，
# 实际创建会议和发送摘要卡片放到 FastAPI BackgroundTasks 里执行。
def process_feishu_meeting_command(title: str, transcript: str, receive_id: str | None = None) -> None:
    """Create a meeting from Feishu text and send the summary card back."""

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
    """创建会议：接收会议标题和记录，解析出摘要、决策和行动项。"""

    try:
        return create_meeting_with_actions(db, payload)
    except OperationalError as exc:
        detail = "Database is temporarily locked. Please retry in a few seconds."
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail) from exc


@router.get("/meetings", response_model=list[MeetingListItem])
def get_meetings(db: Session = Depends(get_db)) -> list[MeetingListItem]:
    """获取会议历史列表，用于首页/历史页展示。"""

    return list_meetings(db)


@router.get("/action-items", response_model=list[ActionItemListItem])
def get_action_items(db: Session = Depends(get_db)) -> list[ActionItemListItem]:
    """获取所有行动项，用于任务结果页和飞书任务查询。"""

    return list_action_items(db)


@router.get("/meetings/{meeting_id}", response_model=MeetingResponse)
def get_meeting(meeting_id: int, db: Session = Depends(get_db)) -> MeetingResponse:
    """按会议 ID 获取会议详情，包括摘要、决策和行动项。"""

    meeting = get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return meeting


@router.post("/meetings/{meeting_id}/send-feishu", response_model=FeishuSendResponse)
def send_to_feishu(meeting_id: int, db: Session = Depends(get_db)) -> FeishuSendResponse:
    """把指定会议的摘要卡片发送到飞书。"""

    response = send_meeting_to_feishu(db, meeting_id)
    if not response:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return response


@router.post("/meetings/{meeting_id}/follow-up", response_model=FeishuSendResponse)
def send_follow_up(meeting_id: int, db: Session = Depends(get_db)) -> FeishuSendResponse:
    """给指定会议发送一次飞书跟进提醒。"""

    response = send_follow_up_to_feishu(db, meeting_id)
    if not response:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return response


@router.post("/follow-ups/run", response_model=FollowUpRunResponse)
def run_follow_ups(db: Session = Depends(get_db)) -> FollowUpRunResponse:
    """手动触发全局跟进扫描，找出需要提醒的未完成任务。"""

    return run_follow_up_scan(db)


@router.get("/agent/traces", response_model=list[AgentTraceLogItem])
def get_agent_traces(limit: int = 50, db: Session = Depends(get_db)) -> list[AgentTraceLogItem]:
    """获取最近的 Agent 执行记录，用于 agent-debug 页面观察链路。"""

    return [
        AgentTraceLogItem(
            id=trace.id,
            chat_id=trace.chat_id,
            source=trace.source,
            message=trace.message,
            normalized_message=trace.normalized_message,
            intent_name=trace.intent_name,
            intent_filters=parse_trace_filters(trace.intent_filters_json),
            tool_name=trace.tool_name,
            tool_source=trace.tool_source,
            tool_category=trace.tool_category,
            tool_executed=trace.tool_executed,
            dangerous=trace.dangerous,
            requires_confirmation=trace.requires_confirmation,
            response_message=trace.response_message,
            created_at=trace.created_at,
        )
        for trace in list_agent_trace_logs(db, limit=limit)
    ]


@router.post("/agent/debug-run", response_model=AgentDebugRunResponse)
def run_agent_debug(payload: AgentDebugRunRequest, db: Session = Depends(get_db)) -> AgentDebugRunResponse:
    """在 Web 调试页手动运行一次 Agent，并返回识别结果和 trace ID。"""

    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is required")

    chat_id = payload.chat_id.strip() or "debug-web"
    agent_response = run_agent_graph(db, message, chat_id=chat_id)
    trace = get_latest_agent_trace_log(db, chat_id=chat_id)

    return AgentDebugRunResponse(
        handled=agent_response.handled,
        intent_name=agent_response.intent_name or "unhandled",
        message=agent_response.message,
        trace_id=trace.id if trace else None,
        steps=[s.to_dict() for s in agent_response.steps],
    )


@router.patch("/action-items/{action_item_id}", response_model=MeetingResponse)
def patch_action_item(
    action_item_id: int,
    payload: ActionItemUpdate,
    db: Session = Depends(get_db),
) -> MeetingResponse:
    """更新行动项负责人、截止时间或状态，并返回所属会议的最新详情。"""

    meeting = update_action_item(db, action_item_id, payload)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found")
    return meeting


@router.post("/feishu/card-callback")
def handle_feishu_card_callback(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
) -> FeishuCardCallbackResponse | dict[str, str]:
    """处理飞书交互卡片回调，目前主要支持从卡片按钮完成任务。"""

    # 飞书配置回调地址时会发送 challenge，这里要原样返回才能通过校验。
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
    """飞书消息事件入口：解析事件、去重、分发固定命令或自然语言 Agent。"""

    # 调试：打印原始 payload 的关键字段
    import json as _json
    try:
        _evt = payload.get("event", {})
        _msg = _evt.get("message", {})
        print(f"\n[FEISHU RAW] chat_type={_msg.get('chat_type')} msg_type={_msg.get('message_type')} content={str(_msg.get('content',''))[:100]}")
        print(f"[FEISHU RAW] sender={_evt.get('sender',{}).get('sender_id',{})}")
    except Exception:
        pass

    # 第一步：把飞书原始 payload 解析成项目内部统一的事件对象。
    try:
        event = parse_feishu_event(payload, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # 飞书首次配置事件订阅时会发送 challenge，需要直接返回。
    if event.challenge:
        return {"challenge": event.challenge}

    # 有些事件不是文本消息，或者不是 ActionBridge 应该处理的消息。
    if event.ignored:
        return {"status": "ignored", "message": event.ignored_message}

    delivery = _build_feishu_delivery()

    # 飞书可能重试同一个事件。先按 dedup_key 去重，避免重复创建任务或重复发卡片。
    if not register_feishu_event(db, event.dedup_key, event.command_type):
        return {"status": "duplicated", "message": "Duplicated Feishu event ignored."}

    # 第二步：优先处理固定命令，例如 /help、/tasks、/task、/done、/remember。
    fixed_response = handle_fixed_feishu_command(
        db,
        done_command=event.done_command,
        task_command=event.task_command,
        tasks_command=event.tasks_command,
        help_command=event.help_command,
        remember_command=event.remember_command,
        memory_command=event.memory_command,
        forget_command=event.forget_command,
        bind_channel_command=event.bind_channel_command,
        follow_up_reply=event.follow_up_reply,
        dedup_key=event.dedup_key,
        reply_chat_id=event.reply_chat_id,
        delivery=delivery,
    )
    if fixed_response:
        return fixed_response

    # 第三步：检查是否是项目成员的私聊消息 → 走个人助手。
    chat_type = _extract_chat_type(payload)
    sender_open_id = _extract_sender_open_id(payload)
    # 调试日志：打印飞书事件关键信息
    import logging
    _logger = logging.getLogger("feishu_debug")
    _logger.setLevel(logging.INFO)
    if not _logger.handlers:
        _h = logging.StreamHandler()
        _h.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(_h)
    _logger.info(f"[FEISHU] chat_type={chat_type} open_id={sender_open_id} text={event.message_text[:50] if event.message_text else 'none'}")

    if chat_type in ("private", "p2p") and sender_open_id:
        member = get_member_by_chat_id(db, sender_open_id)
        if member is not None:
            personal_response = handle_personal_message(
                db=db,
                message=event.message_text or "",
                member_name=member.name,
                member_chat_id=sender_open_id,
            )
            reply_text = build_personal_assistant_response(personal_response, member.name)
            # 通过飞书 API 主动回复消息
            try:
                send_text_reply(reply_text, sender_open_id)
            except Exception:
                pass  # 飞书回复失败不阻塞事件响应
            mark_feishu_event_finished(db, event.dedup_key, "finished")
            return {
                "status": "personal_assistant",
                "member": member.name,
                "message": reply_text,
            }
        else:
            # Unknown member: tell them their open_id
            unknown_msg = f"你还未注册为项目成员。\n请在 Demo 页注册，chat_id 填: {sender_open_id}"
            try:
                send_text_reply(unknown_msg, sender_open_id)
            except Exception:
                pass
            mark_feishu_event_finished(db, event.dedup_key, "finished")
            return {
                "status": "unknown_member",
                "message": unknown_msg,
                "open_id": sender_open_id,
            }

    # 第四步：如果不是 /meeting，但可以交给 Agent 理解，就走自然语言 Agent。
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

    # 第四步：剩下的是 /meeting 命令。放到后台任务中创建会议并发送摘要卡片。
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
