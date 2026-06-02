from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.agent.orchestrator import (
    AgentTextPreparation,
    get_agent_command_type,
    prepare_agent_text_event,
)
from app.services.feishu_event_service import (
    extract_challenge,
    extract_done_command,
    extract_event_dedup_key,
    extract_follow_up_reply,
    extract_forget_command,
    extract_help_command,
    extract_memory_command,
    extract_meeting_command,
    extract_message_text,
    extract_remember_command,
    extract_reply_chat_id,
    extract_task_command,
    extract_tasks_command,
)


@dataclass(frozen=True)
class FeishuEventContext:
    challenge: str | None = None
    reply_chat_id: str | None = None
    pending_chat_id: str = "default"
    message_text: str = ""
    dedup_key: str | None = None
    command_type: str = "agent"
    ignored: bool = False
    ignored_message: str = "No supported command found."
    done_command: Any | None = None
    task_command: Any | None = None
    tasks_command: Any | None = None
    help_command: Any | None = None
    remember_command: Any | None = None
    memory_command: Any | None = None
    forget_command: Any | None = None
    meeting_command: Any | None = None
    follow_up_reply: Any | None = None
    agent_preparation: AgentTextPreparation | None = None

    @property
    def has_fixed_command(self) -> bool:
        return any(
            (
                self.done_command,
                self.task_command,
                self.tasks_command,
                self.help_command,
                self.remember_command,
                self.memory_command,
                self.forget_command,
                self.follow_up_reply,
            )
        )


def parse_feishu_event(payload: dict[str, Any], db: Session) -> FeishuEventContext:
    challenge = extract_challenge(payload)
    if challenge:
        return FeishuEventContext(challenge=challenge)

    reply_chat_id = extract_reply_chat_id(payload)
    pending_chat_id = reply_chat_id or "default"
    message_text = extract_message_text(payload) or ""

    done_command = extract_done_command(payload)
    task_command = extract_task_command(payload)
    tasks_command = extract_tasks_command(payload)
    help_command = extract_help_command(payload)
    remember_command = extract_remember_command(payload)
    memory_command = extract_memory_command(payload)
    forget_command = extract_forget_command(payload)
    meeting_command = extract_meeting_command(payload)
    follow_up_reply = extract_follow_up_reply(payload)

    agent_preparation = None
    has_any_command = any(
        (
            done_command,
            task_command,
            tasks_command,
            help_command,
            remember_command,
            memory_command,
            forget_command,
            meeting_command,
            follow_up_reply,
        )
    )
    if not has_any_command:
        agent_preparation = prepare_agent_text_event(db, message_text, pending_chat_id)
        if agent_preparation.ignored:
            return FeishuEventContext(
                reply_chat_id=reply_chat_id,
                pending_chat_id=pending_chat_id,
                message_text=message_text,
                ignored=True,
                agent_preparation=agent_preparation,
            )

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
        meeting_command=meeting_command,
        follow_up_reply=follow_up_reply,
        agent_preparation=agent_preparation,
    )


def _get_command_type(
    *,
    done_command: Any | None,
    task_command: Any | None,
    tasks_command: Any | None,
    help_command: Any | None,
    remember_command: Any | None,
    memory_command: Any | None,
    forget_command: Any | None,
    meeting_command: Any | None,
    follow_up_reply: Any | None,
    agent_preparation: AgentTextPreparation | None,
) -> str:
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
    if meeting_command:
        return "meeting"
    if follow_up_reply:
        return "follow_up_reply"
    return get_agent_command_type(agent_preparation)
