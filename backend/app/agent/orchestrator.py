from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.agent.graph import run_agent_graph, run_confirmed_agent_action
from app.agent.schemas import AgentResponse
from app.models.pending_agent_action import PendingAgentAction
from app.services.feishu_delivery import FeishuDeliveryPort, get_default_feishu_delivery
from app.services.feishu_event_log_service import mark_feishu_event_finished
from app.services.feishu_service import FeishuDeliveryError
from app.services.agent_task_context_service import save_recent_task_context
from app.services.meeting_service import (
    list_action_items,
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
from app.services.project_channel_service import sync_completed_action_item_to_project_channel


# Agent 自然语言消息的预处理结果。
# feishu_event_router.py 会先调用 prepare_agent_text_event，
# 然后 routes.py 再把这个对象交给 handle_agent_text_event 真正执行。
@dataclass(frozen=True)
class AgentTextPreparation:
    # 用户是不是在回复“确认”或“取消”。
    confirmation_action: str | None = None

    # 当前会话里是否有一个正在等待确认的操作。
    active_pending_action: PendingAgentAction | None = None

    # 用户是否在修改待确认操作里的字段，例如“负责人改成张三”。
    pending_revision: dict[str, str] | None = None

    # Agent 图识别出来的意图和执行结果。
    agent_response: AgentResponse | None = None

    # ignored=True 表示这句话不用继续处理。
    ignored: bool = False


# Agent 自然语言流程的第一步：先判断这句话属于哪种情况。
# 它只做“预处理和分类”，真正发送飞书消息、执行更新在 handle_agent_text_event。
def prepare_agent_text_event(
    db: Session,
    message_text: str,
    pending_chat_id: str,
) -> AgentTextPreparation:
    # 先判断用户是不是在回复“确认/取消”。
    confirmation_action = detect_confirmation_message(message_text)

    # 如果不是确认/取消，再查这个会话里有没有等待确认的操作。
    active_pending_action = (
        None if confirmation_action else get_active_pending_action(db, pending_chat_id)
    )

    # 如果有等待确认的操作，再判断用户是不是想修改其中某个字段。
    pending_revision = (
        detect_pending_revision(message_text, active_pending_action)
        if active_pending_action
        else None
    )

    # 确认、取消、修改待确认字段，都不需要重新跑 Agent 图。
    if confirmation_action or pending_revision:
        return AgentTextPreparation(
            confirmation_action=confirmation_action,
            active_pending_action=active_pending_action,
            pending_revision=pending_revision,
        )

    # 空消息直接忽略。
    if not message_text:
        return AgentTextPreparation(ignored=True)

    # 普通自然语言交给 Agent ReAct 循环。
    agent_response = run_agent_graph(db, message_text, chat_id=pending_chat_id)
    if not agent_response.handled:
        # 如果用户像是在提问，但 Agent 没识别出业务意图，就发兜底帮助。
        if _should_send_fallback_help(message_text):
            return AgentTextPreparation(
                agent_response=AgentResponse(
                    handled=True,
                    intent_name="fallback_help",
                    message="Agent fallback help is ready.",
                )
            )
        return AgentTextPreparation(ignored=True, agent_response=agent_response)

    return AgentTextPreparation(agent_response=agent_response)


# 给事件去重日志使用：根据预处理结果生成一个命令类型。
def get_agent_command_type(preparation: AgentTextPreparation | None) -> str:
    if not preparation:
        return "agent"
    if preparation.confirmation_action == "confirm":
        return "confirm"
    if preparation.confirmation_action == "cancel":
        return "cancel"
    if preparation.agent_response and preparation.agent_response.intent_name:
        return preparation.agent_response.intent_name
    return "agent"


# 通用的“任务不存在”回复。
# 固定命令和 Agent 自然语言流程都会复用它。
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


# Agent 自然语言消息的主执行入口。
# 它会根据 prepare_agent_text_event 的结果，决定是确认 pending 操作、
# 修改 pending 操作，还是根据 Agent 意图执行查询/创建/更新/总结。
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

    # 用户回复“确认/取消”：处理之前保存的 pending 操作。
    if preparation.confirmation_action:
        return _handle_confirmation(
            db=db,
            confirmation_action=preparation.confirmation_action,
            pending_chat_id=pending_chat_id,
            reply_chat_id=reply_chat_id,
            dedup_key=dedup_key,
            delivery=delivery,
        )

    # 用户没有确认，而是在修改待确认内容，例如“负责人换成测试同学”。
    if preparation.active_pending_action and preparation.pending_revision:
        return _handle_pending_revision(
            db=db,
            pending=preparation.active_pending_action,
            pending_revision=preparation.pending_revision,
            reply_chat_id=reply_chat_id,
            dedup_key=dedup_key,
            delivery=delivery,
        )

    # 普通自然语言：使用预处理阶段已有的 Agent 结果；没有就现场跑一次。
    agent_response = preparation.agent_response or _build_agent_response(db, message_text)
    if not agent_response.handled:
        mark_feishu_event_finished(db, dedup_key, "ignored")
        return {"status": "ignored", "message": "No supported command found."}

    # 下面按 Agent 识别出的 intent.name 分发到不同业务分支。
    if agent_response.intent_name == "help":
        return _send_help_response(db, agent_response, reply_chat_id, dedup_key, delivery)

    if agent_response.intent_name == "fallback_help":
        return _send_fallback_help_response(db, agent_response, reply_chat_id, dedup_key, delivery)

    if agent_response.intent_name == "create_task_missing_info":
        return _send_create_task_clarification(db, agent_response, reply_chat_id, dedup_key, delivery)

    if agent_response.intent_name == "clarify_task_reference":
        return _send_task_reference_clarification(db, agent_response, reply_chat_id, dedup_key, delivery)

    if agent_response.intent_name == "create_task":
        return _request_create_task_confirmation(
            db=db,
            agent_response=agent_response,
            pending_chat_id=pending_chat_id,
            reply_chat_id=reply_chat_id,
            dedup_key=dedup_key,
            delivery=delivery,
        )

    if agent_response.intent_name == "update_task_deadline":
        return _request_deadline_update_confirmation(
            db=db,
            agent_response=agent_response,
            pending_chat_id=pending_chat_id,
            reply_chat_id=reply_chat_id,
            dedup_key=dedup_key,
            delivery=delivery,
        )

    if agent_response.intent_name == "update_task_owner":
        return _request_owner_update_confirmation(
            db=db,
            agent_response=agent_response,
            pending_chat_id=pending_chat_id,
            reply_chat_id=reply_chat_id,
            dedup_key=dedup_key,
            delivery=delivery,
        )

    if agent_response.intent_name == "update_task_status":
        return _update_task_status(db, agent_response, reply_chat_id, dedup_key, delivery)

    if agent_response.intent_name == "summarize_project":
        return _send_project_summary(db, agent_response, reply_chat_id, dedup_key, delivery)

    return _send_query_tasks_result(db, agent_response, reply_chat_id, dedup_key, delivery)


def _build_agent_response(db: Session, message_text: str) -> AgentResponse:
    # 调用 Agent 图，得到结构化意图、任务列表或执行结果。
    return run_agent_graph(db, message_text)


def _should_send_fallback_help(message_text: str) -> bool:
    # 判断一条未识别消息是否像是在求助/提问。
    # 如果像，就发兜底帮助；如果不像，就安静忽略。
    stripped = message_text.strip()
    if not stripped:
        return False
    if stripped.startswith("/"):
        return False
    return any(keyword in stripped for keyword in ("?", "？", "怎么", "如何", "哪些", "什么", "查", "看", "帮我"))


# 处理用户回复“确认”或“取消”。
# 这一步会读取之前保存的 pending action，并在确认后真正执行写操作。
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
        # 用户说了“确认”，但系统里没有等待确认的操作。
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
        # 用户取消本次待确认操作。
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

    # 用户确认执行：读取 pending payload，按 action_type 执行真正的写操作。
    payload_data = load_pending_payload(pending)
    if pending.action_type == "create_task":
        # 确认创建任务。
        confirmed_response = run_confirmed_agent_action(db, pending.action_type, payload_data)
        action_item = confirmed_response.executed_action.action_item if confirmed_response.executed_action else None
        if not action_item:
            resolve_pending_action(db, pending, "failed")
            mark_feishu_event_finished(db, dedup_key, "failed")
            return {"status": "failed", "message": "Task creation failed."}
        confirmed_intent = confirmed_response.intent_name if confirmed_response.intent else "confirm_create_task"
        success_message = "Task created after confirmation."
    elif pending.action_type == "update_task_deadline":
        # 确认修改任务截止时间。
        confirmed_response = run_confirmed_agent_action(db, pending.action_type, payload_data)
        action_item = confirmed_response.executed_action.action_item if confirmed_response.executed_action else None
        if not action_item:
            resolve_pending_action(db, pending, "failed")
            return send_task_not_found_response(
                int(payload_data["action_item_id"]),
                dedup_key,
                reply_chat_id,
                db,
                delivery,
            )
        confirmed_intent = confirmed_response.intent_name if confirmed_response.intent else "confirm_update_task_deadline"
        success_message = "Task deadline updated after confirmation."
    elif pending.action_type == "update_task_owner":
        # 确认修改任务负责人。
        confirmed_response = run_confirmed_agent_action(db, pending.action_type, payload_data)
        action_item = confirmed_response.executed_action.action_item if confirmed_response.executed_action else None
        if not action_item:
            resolve_pending_action(db, pending, "failed")
            return send_task_not_found_response(
                int(payload_data["action_item_id"]),
                dedup_key,
                reply_chat_id,
                db,
                delivery,
            )
        confirmed_intent = confirmed_response.intent_name if confirmed_response.intent else "confirm_update_task_owner"
        success_message = "Task owner updated after confirmation."
    else:
        # 理论上不会进入这里，除非数据库里保存了未知 action_type。
        resolve_pending_action(db, pending, "failed")
        mark_feishu_event_finished(db, dedup_key, "failed")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported pending action")

    # pending action 已经执行完，标记为 confirmed。
    resolve_pending_action(db, pending, "confirmed")
    try:
        # 给用户发送最新任务详情，作为执行结果回执。
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


# 处理用户对待确认操作的“修改”。
# 例如系统问“是否把负责人改成 A”，用户回复“改成 B”，就会走这里。
def _handle_pending_revision(
    db: Session,
    pending: PendingAgentAction,
    pending_revision: dict[str, str],
    reply_chat_id: str | None,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    # 先把 pending payload 里的字段更新掉。
    updated_payload = update_pending_payload(db, pending, pending_revision)
    try:
        if pending.action_type == "create_task":
            # 修改的是“待创建任务”的字段，重新发送创建确认卡片。
            delivery.send_task_create_confirmation(
                title=updated_payload["title"],
                owner_name=updated_payload["owner_name"],
                deadline=updated_payload["deadline"],
                receive_id=reply_chat_id,
            )
        elif pending.action_type == "update_task_deadline":
            # 修改的是“待修改截止时间”的字段，重新发送截止时间确认卡片。
            confirmation_kwargs = {
                "action_item_id": int(updated_payload["action_item_id"]),
                "title": updated_payload["title"],
                "old_deadline": updated_payload["old_deadline"],
                "new_deadline": updated_payload["new_deadline"],
                "receive_id": reply_chat_id,
            }
            if updated_payload.get("reference_note"):
                confirmation_kwargs["reference_note"] = updated_payload["reference_note"]
            delivery.send_task_deadline_update_confirmation(**confirmation_kwargs)
        elif pending.action_type == "update_task_owner":
            # 修改的是“待修改负责人”的字段，重新发送负责人确认卡片。
            confirmation_kwargs = {
                "action_item_id": int(updated_payload["action_item_id"]),
                "title": updated_payload["title"],
                "old_owner_name": updated_payload["old_owner_name"],
                "new_owner_name": updated_payload["new_owner_name"],
                "receive_id": reply_chat_id,
            }
            if updated_payload.get("reference_note"):
                confirmation_kwargs["reference_note"] = updated_payload["reference_note"]
            delivery.send_task_owner_update_confirmation(**confirmation_kwargs)
        else:
            # 未知 pending 类型，不继续处理。
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
    # Agent 识别到 help 意图时，发送标准帮助卡片。
    try:
        delivery.send_help_card(receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "help_sent",
            "intent": agent_response.intent_name or "unknown",
            "message": f"Help card generated, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "help_sent",
        "intent": agent_response.intent_name or "unknown",
        "message": agent_response.message,
    }


def _send_fallback_help_response(
    db: Session,
    agent_response: AgentResponse,
    reply_chat_id: str | None,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    # Agent 没识别出具体业务意图，但消息像是在提问时，发送兜底帮助。
    try:
        delivery.send_pending_action_notice(
            "🤖 我还没理解你的操作意图",
            _build_fallback_help_notice(),
            receive_id=reply_chat_id,
        )
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "agent_fallback",
            "intent": agent_response.intent_name or "fallback_help",
            "message": f"Fallback help generated, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "agent_fallback",
        "intent": agent_response.intent_name or "fallback_help",
        "message": agent_response.message,
    }


def _build_fallback_help_notice() -> str:
    # 构造兜底帮助文案。
    return "\n".join(
        [
            "我主要负责会议执行闭环，不会随意处理和任务无关的问题。",
            "",
            "**你可以这样问：**",
            "· `/tasks` 查看当前未完成任务",
            "· `查询已完成任务` 查看已完成任务",
            "· `官网改版进度怎么样` 查看项目进度",
            "· `把 12 号任务负责人改成测试同学` 修改负责人",
            "· `把 12 号任务延期到周五` 修改截止时间",
        ]
    )


def _send_create_task_clarification(
    db: Session,
    agent_response: AgentResponse,
    reply_chat_id: str | None,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    # 创建任务缺少必要信息时，提示用户补充。
    try:
        delivery.send_task_create_clarification(agent_response.message, receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "task_create_needs_info",
            "intent": agent_response.intent_name or "unknown",
            "message": f"{agent_response.message} Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "task_create_needs_info",
        "intent": agent_response.intent_name or "unknown",
        "message": agent_response.message,
    }


def _send_task_reference_clarification(
    db: Session,
    agent_response: AgentResponse,
    reply_chat_id: str | None,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    # 用户说“第几个任务”但系统无法定位时，请用户补充任务引用。
    try:
        delivery.send_task_create_clarification(agent_response.message, receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "task_reference_needs_info",
            "intent": agent_response.intent_name or "unknown",
            "message": f"{agent_response.message} Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "task_reference_needs_info",
        "intent": agent_response.intent_name or "unknown",
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
    # 创建任务属于写操作，不能直接执行，需要先保存 pending action 并让用户确认。
    if not agent_response.intent_name:
        mark_feishu_event_finished(db, dedup_key, "failed")
        return {"status": "ignored", "message": "No task intent generated."}

    # 把待创建任务保存起来，等待用户回复“确认”。
    save_pending_create_task(
        db,
        chat_id=pending_chat_id,
        title=agent_response.intent_filters["title"],
        owner_name=agent_response.intent_filters["owner_name"],
        deadline=agent_response.intent_filters["deadline"],
    )
    try:
        # 发送“请确认创建任务”的飞书卡片。
        delivery.send_task_create_confirmation(
            title=agent_response.intent_filters["title"],
            owner_name=agent_response.intent_filters["owner_name"],
            deadline=agent_response.intent_filters["deadline"],
            receive_id=reply_chat_id,
        )
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "task_create_pending",
            "intent": agent_response.intent_name,
            "message": f"Task create confirmation saved, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "task_create_pending",
        "intent": agent_response.intent_name,
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
    # 修改截止时间属于写操作，先保存 pending action，再发确认卡片。
    if not agent_response.intent_name:
        mark_feishu_event_finished(db, dedup_key, "failed")
        return {"status": "ignored", "message": "No task intent generated."}

    # 从 Agent 识别结果里拿到任务 ID 和新截止时间。
    action_item_id = int(agent_response.intent_filters["action_item_id"])
    new_deadline = agent_response.intent_filters["deadline"]
    action_item = next((item for item in list_action_items(db) if item.id == action_item_id), None)
    if not action_item:
        return send_task_not_found_response(action_item_id, dedup_key, reply_chat_id, db, delivery)

    # 保存待确认的截止时间修改。
    save_pending_update_task_deadline(
        db,
        chat_id=pending_chat_id,
        action_item_id=action_item_id,
        title=action_item.title,
        old_deadline=action_item.deadline,
        new_deadline=new_deadline,
        reference_note=agent_response.intent_filters.get("reference_note", ""),
    )
    try:
        # 发送“请确认修改截止时间”的飞书卡片。
        confirmation_kwargs = {
            "action_item_id": action_item_id,
            "title": action_item.title,
            "old_deadline": action_item.deadline,
            "new_deadline": new_deadline,
            "receive_id": reply_chat_id,
        }
        if agent_response.intent_filters.get("reference_note"):
            confirmation_kwargs["reference_note"] = agent_response.intent_filters["reference_note"]
        delivery.send_task_deadline_update_confirmation(**confirmation_kwargs)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "task_deadline_update_pending",
            "intent": agent_response.intent_name,
            "action_item_id": action_item_id,
            "message": f"Task deadline update confirmation saved, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "task_deadline_update_pending",
        "intent": agent_response.intent_name,
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
    # 修改负责人属于写操作，先保存 pending action，再发确认卡片。
    if not agent_response.intent_name:
        mark_feishu_event_finished(db, dedup_key, "failed")
        return {"status": "ignored", "message": "No task intent generated."}

    # 从 Agent 识别结果里拿到任务 ID 和新负责人。
    action_item_id = int(agent_response.intent_filters["action_item_id"])
    new_owner_name = agent_response.intent_filters["owner_name"]
    action_item = next((item for item in list_action_items(db) if item.id == action_item_id), None)
    if not action_item:
        return send_task_not_found_response(action_item_id, dedup_key, reply_chat_id, db, delivery)

    # 保存待确认的负责人修改。
    save_pending_update_task_owner(
        db,
        chat_id=pending_chat_id,
        action_item_id=action_item_id,
        title=action_item.title,
        old_owner_name=action_item.owner_name,
        new_owner_name=new_owner_name,
        reference_note=agent_response.intent_filters.get("reference_note", ""),
    )
    try:
        # 发送“请确认修改负责人”的飞书卡片。
        confirmation_kwargs = {
            "action_item_id": action_item_id,
            "title": action_item.title,
            "old_owner_name": action_item.owner_name,
            "new_owner_name": new_owner_name,
            "receive_id": reply_chat_id,
        }
        if agent_response.intent_filters.get("reference_note"):
            confirmation_kwargs["reference_note"] = agent_response.intent_filters["reference_note"]
        delivery.send_task_owner_update_confirmation(**confirmation_kwargs)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "task_owner_update_pending",
            "intent": agent_response.intent_name,
            "action_item_id": action_item_id,
            "message": f"Task owner update confirmation saved, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "task_owner_update_pending",
        "intent": agent_response.intent_name,
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
    # 更新任务状态通常可以直接执行，例如“把 12 号任务标记完成”。
    if not agent_response.intent_name:
        mark_feishu_event_finished(db, dedup_key, "failed")
        return {"status": "ignored", "message": "No task intent generated."}

    # 读取 Agent 识别出来的任务 ID 和目标状态。
    action_item_id = int(agent_response.intent_filters["action_item_id"])
    target_status = agent_response.intent_filters["status"]

    # 有些 Agent 工具已经执行过更新；如果没有，就在这里执行更新。
    if agent_response.executed_action:
        action_item = agent_response.executed_action.action_item
    else:
        action_item = update_action_item_status(db, action_item_id, target_status)

    if not action_item:
        return send_task_not_found_response(action_item_id, dedup_key, reply_chat_id, db, delivery)

    try:
        # 回复最新任务详情。
        delivery.send_task_detail_summary(action_item, receive_id=reply_chat_id)

        # 如果任务被标记为完成，也同步到项目绑定群。
        synced_receive_id = (
            sync_completed_action_item_to_project_channel(
                db,
                action_item_id=action_item.id,
                title=action_item.title,
                owner_name=action_item.owner_name,
                source_receive_id=reply_chat_id,
                send_completed_notice=delivery.send_action_item_completed_notice,
            )
            if target_status == "completed"
            else None
        )
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "agent_updated",
            "intent": agent_response.intent_name,
            "action_item_id": action_item.id,
            "target_status": target_status,
            "message": f"Task updated, but Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "agent_updated",
        "intent": agent_response.intent_name,
        "action_item_id": action_item.id,
        "target_status": target_status,
        "synced_receive_id": synced_receive_id,
        "message": "Task status updated.",
    }


def _send_project_summary(
    db: Session,
    agent_response: AgentResponse,
    reply_chat_id: str | None,
    dedup_key: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    # Agent 识别到“项目进度怎么样”时，发送项目总结卡片。
    if not agent_response.progress_summary:
        mark_feishu_event_finished(db, dedup_key, "failed")
        return {"status": "ignored", "message": "No project progress summary generated."}

    try:
        delivery.send_project_progress_summary(agent_response.progress_summary, receive_id=reply_chat_id)
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "agent_replied",
            "intent": agent_response.intent_name or "unknown",
            "task_count": len(agent_response.items),
            "message": f"{agent_response.message} Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "agent_replied",
        "intent": agent_response.intent_name or "unknown",
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
    # Agent 识别到查询任务意图时，发送查询结果。
    context_chat_id = reply_chat_id or "default"

    # 保存最近展示的任务，方便后续“第一个任务”这种指代。
    save_recent_task_context(db, context_chat_id, agent_response.items[:10])
    try:
        if agent_response.items:
            # 有结果：发送任务列表卡片。
            delivery.send_open_tasks_summary(agent_response.items[:10], receive_id=reply_chat_id)
        else:
            # 没结果：发送提示卡片，告诉用户可以怎么查。
            delivery.send_pending_action_notice(
                "🔎 没有找到符合条件的任务",
                _build_empty_query_notice(agent_response),
                receive_id=reply_chat_id,
            )
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "agent_replied",
            "intent": agent_response.intent_name or "unknown",
            "task_count": len(agent_response.items),
            "message": f"{agent_response.message} Feishu delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "agent_replied",
        "intent": agent_response.intent_name or "unknown",
        "task_count": len(agent_response.items),
        "message": agent_response.message,
    }


def _build_empty_query_notice(agent_response: AgentResponse) -> str:
    # 查询没有结果时，构造提示文案。
    filters = agent_response.intent_filters or {}
    condition = _describe_query_filters(filters)
    return "\n".join(
        [
            f"没有找到{condition}的任务。",
            "",
            "**你可以这样试试：**",
            "· `/tasks` 查看当前未完成任务",
            "· `查询已完成任务` 查看已完成任务",
            "· `官网改版进度怎么样` 查看项目进度",
            "· `官网改版相关任务` 查看指定项目任务",
        ]
    )


def _describe_query_filters(filters: dict[str, str]) -> str:
    # 把查询过滤条件转成人能看懂的描述，例如“已完成 官网改版”。
    status_label = {
        "pending": "待处理",
        "in_progress": "进行中",
        "completed": "已完成",
        "failed": "有风险",
    }.get(filters.get("status", ""), "")
    due_label = {
        "due_today": "今日到期",
        "overdue": "已逾期",
    }.get(filters.get("due_status", ""), "")
    parts = [part for part in (status_label, due_label, filters.get("owner"), filters.get("keyword")) if part]
    return "、".join(parts)
