# 这个文件负责处理“固定格式”的飞书命令。
# 常见例子：
# - /done 12：把 12 号任务标记为完成。
# - /task 12：查看 12 号任务详情。
# - /tasks：查看当前未完成任务列表。
# - /help：查看机器人帮助。
# - /remember、/memory、/forget：管理记忆别名。
# 如果消息不是固定命令，routes.py 会继续交给 Agent 自然语言流程处理。

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.agent.orchestrator import send_task_not_found_response
from app.services.agent_task_context_service import save_recent_task_context
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
from app.services.project_channel_service import bind_project_channel, sync_completed_action_item_to_project_channel


# 固定飞书命令的统一入口。
# 它接收 feishu_event_router.py 解析好的命令对象，
# 然后分发给下面对应的私有处理函数。
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
    bind_channel_command: Any | None,
    follow_up_reply: Any | None,
    dedup_key: str | None,
    reply_chat_id: str | None,
    delivery: FeishuDeliveryPort | None = None,
) -> dict[str, Any] | None:
    # delivery 是“飞书发送工具箱”。
    # 测试时可以传入假的 delivery，避免真的往飞书发消息。
    delivery = delivery or get_default_feishu_delivery()

    # 命令处理优先级：先处理明确的写操作，再处理查询和帮助类命令。
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
    if bind_channel_command:
        return _handle_bind_channel_command(db, bind_channel_command, dedup_key, reply_chat_id, delivery)
    if follow_up_reply:
        return _handle_follow_up_reply(db, follow_up_reply, dedup_key, reply_chat_id, delivery)
    return None


# 处理 /done <任务ID>。
# 它会更新数据库中的任务状态，发送完成通知，
# 如果任务命中了已绑定的项目群，还会同步一份完成通知过去。
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
        # 先回复触发命令的当前会话。
        delivery.send_action_item_completed_notice(
            action_item.id,
            action_item.title,
            action_item.owner_name,
            receive_id=reply_chat_id,
        )

        # 如果这个任务匹配了某个已绑定项目群，也同步通知到那个群。
        synced_receive_id = sync_completed_action_item_to_project_channel(
            db,
            action_item_id=action_item.id,
            title=action_item.title,
            owner_name=action_item.owner_name,
            source_receive_id=reply_chat_id,
            send_completed_notice=delivery.send_action_item_completed_notice,
        )
    except FeishuDeliveryError as exc:
        # 数据库更新已经成功；即使飞书通知失败，也返回 completed。
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
        "synced_receive_id": synced_receive_id,
        "message": "Action item marked as completed.",
    }


# 处理 /task <任务ID>。
# 它会查找单个任务，并把任务详情卡片发回飞书。
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


# 处理 /tasks。
# 它会列出未完成任务，并保存最近任务上下文。
# 这样用户后续说“第一个任务”“第二个任务”时，Agent 更容易理解指代。
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
    save_recent_task_context(db, reply_chat_id or "default", open_tasks[: tasks_command.limit])

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


# 处理 /help。
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


# 处理 /remember <别名> = <标准名称>。
# 它会保存结构化记忆别名，例如“官网” = “官网改版”。
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


# 处理 /memory。
# 它会列出当前所有记忆别名。
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


# 处理 /forget <别名>。
# 它会删除一个记忆别名。
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


# 处理项目群绑定命令。
# 它会把某个项目关键词和当前飞书群绑定起来。
# 后续该项目相关任务完成时，可以自动同步通知到这个群。
def _handle_bind_channel_command(
    db: Session,
    bind_channel_command: Any,
    dedup_key: str | None,
    reply_chat_id: str | None,
    delivery: FeishuDeliveryPort,
) -> dict[str, Any]:
    if not reply_chat_id:
        mark_feishu_event_finished(db, dedup_key, "failed")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Feishu chat_id is required.")

    item = bind_project_channel(db, bind_channel_command.project_keyword, reply_chat_id)
    try:
        delivery.send_pending_action_notice(
            "Project channel bound",
            (
                f"Project keyword `{item.project_keyword}` is bound to this chat. "
                "Completed matching tasks will be synced here."
            ),
            receive_id=reply_chat_id,
        )
    except FeishuDeliveryError as exc:
        mark_feishu_event_finished(db, dedup_key, "finished")
        return {
            "status": "project_channel_bound",
            "project_keyword": item.project_keyword,
            "receive_id": item.receive_id,
            "message": f"Project channel bound, but Feishu notice delivery failed: {exc}",
        }

    mark_feishu_event_finished(db, dedup_key, "finished")
    return {
        "status": "project_channel_bound",
        "project_keyword": item.project_keyword,
        "receive_id": item.receive_id,
        "message": "Project channel bound.",
    }


# 处理用户对跟进提醒的回复。
# 例如用户收到提醒后回复“完成了 #12”或“#12 有风险”。
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
        # 发送任务最新详情，让用户确认状态已经更新。
        delivery.send_task_detail_summary(action_item, receive_id=reply_chat_id)

        # 如果任务变成 completed，也同步完成通知到已绑定的项目群。
        synced_receive_id = (
            sync_completed_action_item_to_project_channel(
                db,
                action_item_id=action_item.id,
                title=action_item.title,
                owner_name=action_item.owner_name,
                source_receive_id=reply_chat_id,
                send_completed_notice=delivery.send_action_item_completed_notice,
            )
            if action_item.status == "completed"
            else None
        )
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
        "synced_receive_id": synced_receive_id,
        "message": "Follow-up reply handled.",
    }
