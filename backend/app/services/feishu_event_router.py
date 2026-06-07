# 把飞书发来的原始消息，解析成系统内部能理解的“事件对象”。这个事件对象会被 routes.py 进一步分发到不同的处理函数。

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.agent.orchestrator import (
    AgentTextPreparation,
    get_agent_command_type,
    prepare_agent_text_event,
)
from app.services.feishu_event_guard import gate_agent_message
from app.services.feishu_event_service import (
    extract_challenge,
    extract_done_command,
    extract_event_dedup_key,
    extract_follow_up_reply,
    extract_forget_command,
    extract_bind_channel_command,
    extract_help_command,
    extract_memory_command,
    extract_meeting_command,
    extract_message_text,
    extract_remember_command,
    extract_reply_chat_id,
    extract_task_command,
    extract_tasks_command,
)
from app.services.pending_agent_action_service import detect_confirmation_message, get_active_pending_action


# 飞书事件解析后的统一上下文对象。
# routes.py 后续只需要看这个对象，不需要再直接研究飞书原始 payload。
@dataclass(frozen=True)
class FeishuEventContext:
    # 飞书第一次配置事件订阅时会发送 challenge，后端需要原样返回。
    challenge: str | None = None

    # 当前消息应该回复到哪个飞书会话。
    reply_chat_id: str | None = None

    # pending_chat_id 用来查找“等待确认”的 Agent 操作。
    # 没有飞书 chat_id 时，使用 default 作为兜底。
    pending_chat_id: str = "default"

    # 用户发送的纯文本内容。
    message_text: str = ""

    # 飞书事件去重 key，防止同一个事件被重复处理。
    dedup_key: str | None = None

    # 当前事件的命令类型，例如 done、task、meeting、agent。
    command_type: str = "agent"

    # ignored=True 表示这个事件不需要继续处理。
    ignored: bool = False
    ignored_message: str = "No supported command found."

    # 下面这些字段是固定命令解析结果。
    # 哪个字段不为空，就说明用户触发了对应命令。
    done_command: Any | None = None
    task_command: Any | None = None
    tasks_command: Any | None = None
    help_command: Any | None = None
    remember_command: Any | None = None
    memory_command: Any | None = None
    forget_command: Any | None = None
    bind_channel_command: Any | None = None
    meeting_command: Any | None = None
    follow_up_reply: Any | None = None

    # 如果不是固定命令，而是自然语言消息，这里会保存 Agent 预处理结果。
    agent_preparation: AgentTextPreparation | None = None

    @property
    def has_fixed_command(self) -> bool:
        # 只要任意固定命令字段不为空，就认为这是固定命令。
        return any(
            (
                self.done_command,
                self.task_command,
                self.tasks_command,
                self.help_command,
                self.remember_command,
                self.memory_command,
                self.forget_command,
                self.bind_channel_command,
                self.follow_up_reply,
            )
        )


# 把飞书原始 payload 解析成 FeishuEventContext。
# 这是飞书事件进入系统后的第一层“路由判断”。
def parse_feishu_event(payload: dict[str, Any], db: Session) -> FeishuEventContext:
    # 1. 处理飞书事件订阅校验。
    # 飞书配置 Request URL 时会发 challenge，后端必须直接返回。
    challenge = extract_challenge(payload)
    if challenge:
        return FeishuEventContext(challenge=challenge)

    # 2. 提取基础上下文：回复群、pending 操作所属会话、消息文本。
    reply_chat_id = extract_reply_chat_id(payload)
    pending_chat_id = reply_chat_id or "default"
    message_text = extract_message_text(payload) or ""

    # 3. 尝试按各种固定命令解析。
    # 这些 extract_xxx_command 函数只负责“看消息像不像某种命令”。
    done_command = extract_done_command(payload)
    task_command = extract_task_command(payload)
    tasks_command = extract_tasks_command(payload)
    help_command = extract_help_command(payload)
    remember_command = extract_remember_command(payload)
    memory_command = extract_memory_command(payload)
    forget_command = extract_forget_command(payload)
    bind_channel_command = extract_bind_channel_command(payload)
    meeting_command = extract_meeting_command(payload)
    follow_up_reply = extract_follow_up_reply(payload)

    agent_preparation = None

    # has_any_command=True 表示消息已经命中了固定命令，
    # 后面就不需要再交给 Agent 自然语言识别。
    has_any_command = any(
        (
            done_command,
            task_command,
            tasks_command,
            help_command,
            remember_command,
            memory_command,
            forget_command,
            bind_channel_command,
            meeting_command,
            follow_up_reply,
        )
    )

    # 4. 判断这条消息是否应该处理。
    # gate_agent_message 会过滤掉不该响应的群消息、机器人自己发的消息等。
    # 如果存在等待确认的操作，或者用户发的是“确认/取消”，也会影响放行结果。
    active_pending_action = get_active_pending_action(db, pending_chat_id)
    gate = gate_agent_message(
        payload,
        message_text,
        has_fixed_command=has_any_command,
        has_active_pending_action=active_pending_action is not None,
        is_confirmation_message=detect_confirmation_message(message_text) is not None,
    )
    if not gate.should_process:
        # 被 gate 拦截的事件直接标记 ignored，让 routes.py 返回 ignored。
        return FeishuEventContext(
            reply_chat_id=reply_chat_id,
            pending_chat_id=pending_chat_id,
            message_text=gate.message_text,
            ignored=True,
            ignored_message=gate.reason,
        )
    message_text = gate.message_text

    # 5. 如果没有命中固定命令，就准备走 Agent 自然语言流程。
    # prepare_agent_text_event 会做 pending confirm、memory 归一化等预处理。
    if not has_any_command:
        agent_preparation = prepare_agent_text_event(db, message_text, pending_chat_id)
        if agent_preparation.ignored:
            # Agent 预处理也可能判断“不需要处理”，例如空消息或无效消息。
            return FeishuEventContext(
                reply_chat_id=reply_chat_id,
                pending_chat_id=pending_chat_id,
                message_text=message_text,
                ignored=True,
                agent_preparation=agent_preparation,
            )

    # 6. 返回统一上下文。routes.py 会根据这些字段继续分发：
    # - fixed command -> feishu_command_handler.py
    # - meeting command -> 后台创建会议
    # - agent_preparation -> orchestrator.py
    return FeishuEventContext(
        reply_chat_id=reply_chat_id,
        pending_chat_id=pending_chat_id,
        message_text=message_text,
        dedup_key=extract_event_dedup_key(payload),
        command_type=_get_command_type(
            done_command=done_command,
            task_command=task_command,
            tasks_command=tasks_command,
            help_command=help_command,
            remember_command=remember_command,
            memory_command=memory_command,
            forget_command=forget_command,
            bind_channel_command=bind_channel_command,
            meeting_command=meeting_command,
            follow_up_reply=follow_up_reply,
            agent_preparation=agent_preparation,
        ),
        done_command=done_command,
        task_command=task_command,
        tasks_command=tasks_command,
        help_command=help_command,
        remember_command=remember_command,
        memory_command=memory_command,
        forget_command=forget_command,
        bind_channel_command=bind_channel_command,
        meeting_command=meeting_command,
        follow_up_reply=follow_up_reply,
        agent_preparation=agent_preparation,
    )


# 根据解析结果生成命令类型。
# 这个类型主要用于事件去重日志，帮助我们知道某条飞书事件是什么命令。
def _get_command_type(
    *,
    done_command: Any | None,
    task_command: Any | None,
    tasks_command: Any | None,
    help_command: Any | None,
    remember_command: Any | None,
    memory_command: Any | None,
    forget_command: Any | None,
    bind_channel_command: Any | None,
    meeting_command: Any | None,
    follow_up_reply: Any | None,
    agent_preparation: AgentTextPreparation | None,
) -> str:
    # 固定命令优先返回明确类型。
    if done_command:
        return "done"
    if task_command:
        return "task"
    if tasks_command:
        return "tasks"
    if help_command:
        return "help"
    if remember_command:
        return "remember"
    if memory_command:
        return "memory"
    if forget_command:
        return "forget"
    if bind_channel_command:
        return "bind_channel"
    if meeting_command:
        return "meeting"
    if follow_up_reply:
        return "follow_up_reply"

    # 都不是固定命令时，交给 Agent 预处理结果判断更细的 agent 类型。
    return get_agent_command_type(agent_preparation)
