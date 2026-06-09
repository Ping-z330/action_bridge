import json
import re
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class FeishuMeetingCommand:
    # /meeting 命令解析结果：会议标题和会议原文。
    title: str
    transcript: str


@dataclass(frozen=True)
class FeishuDoneCommand:
    # /done 命令解析结果：要标记完成的行动项 ID。
    action_item_id: int


@dataclass(frozen=True)
class FeishuTasksCommand:
    # /tasks 命令解析结果：列出未完成任务，默认最多展示 10 条。
    limit: int = 10


@dataclass(frozen=True)
class FeishuTaskCommand:
    # /task 命令解析结果：查看单个行动项详情。
    action_item_id: int


@dataclass(frozen=True)
class FeishuHelpCommand:
    # /help 命令没有额外参数。
    pass


@dataclass(frozen=True)
class FeishuRememberCommand:
    # /remember 命令解析结果：保存一个记忆别名。
    alias: str
    target: str
    memory_type: str = "alias"


@dataclass(frozen=True)
class FeishuForgetCommand:
    # /forget 命令解析结果：删除指定别名。
    alias: str


@dataclass(frozen=True)
class FeishuMemoryCommand:
    # /memory 命令没有额外参数，用于查看记忆列表。
    pass


@dataclass(frozen=True)
class FeishuBindChannelCommand:
    # /bind-channel 命令解析结果：把项目关键词绑定到当前群。
    project_keyword: str


@dataclass(frozen=True)
class FeishuFollowUpReply:
    # 用户对跟进提醒的自然回复，例如“#12 完成了”。
    action_item_id: int
    status: str


def extract_challenge(payload: dict[str, Any]) -> str | None:
    # 飞书 URL 校验时会发送 challenge，接口需要原样返回。
    challenge = payload.get("challenge") or payload.get("Challenge")
    if isinstance(challenge, str) and challenge:
        return challenge
    return None


def extract_event_dedup_key(payload: dict[str, Any]) -> str | None:
    # 从 payload 中提取可用于事件去重的 key。
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}

    candidates = [
        payload.get("event_id"),
        payload.get("uuid"),
        header.get("event_id"),
        message.get("message_id"),
        message.get("root_id"),
    ]

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    return None


def extract_reply_chat_id(payload: dict[str, Any]) -> str | None:
    # 从 payload 中提取回复目标 chat_id。
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    root_message = payload.get("message") if isinstance(payload.get("message"), dict) else {}

    candidates = [
        message.get("chat_id"),
        root_message.get("chat_id"),
        payload.get("chat_id"),
    ]

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    return None


def extract_meeting_command(payload: dict[str, Any]) -> FeishuMeetingCommand | None:
    # 解析 /meeting <title> 后续多行转录文本。
    text = _extract_text(payload)
    if not text:
        return None

    command_start = text.find("/meeting")
    if command_start < 0:
        return None

    command_text = text[command_start:].strip()
    lines = [line.strip() for line in command_text.splitlines() if line.strip()]
    if not lines:
        return None

    first_line = lines[0]
    title = first_line.removeprefix("/meeting").strip()
    transcript_lines = lines[1:]

    if not title and transcript_lines:
        title = transcript_lines.pop(0).strip()

    transcript = "\n".join(transcript_lines).strip()

    if not title or not transcript:
        raise ValueError("Invalid /meeting command. Expected: /meeting <title> followed by transcript.")

    return FeishuMeetingCommand(title=title, transcript=transcript)


def extract_done_command(payload: dict[str, Any]) -> FeishuDoneCommand | None:
    # 解析 /done <action_item_id>。
    text = _extract_text(payload)
    if not text:
        return None

    command_start = text.find("/done")
    if command_start < 0:
        return None

    command_text = text[command_start:].strip()
    parts = command_text.split()
    if len(parts) < 2:
        raise ValueError("Invalid /done command. Expected: /done <action_item_id>.")

    try:
        action_item_id = int(parts[1])
    except ValueError as exc:
        raise ValueError("Invalid /done command. action_item_id must be a number.") from exc

    return FeishuDoneCommand(action_item_id=action_item_id)


def extract_tasks_command(payload: dict[str, Any]) -> FeishuTasksCommand | None:
    # 解析 /tasks。
    text = _extract_text(payload)
    if not text:
        return None

    command_start = text.find("/tasks")
    if command_start < 0:
        return None

    return FeishuTasksCommand()


def extract_task_command(payload: dict[str, Any]) -> FeishuTaskCommand | None:
    # 解析 /task <action_item_id>，注意要避免误匹配 /tasks。
    text = _extract_text(payload)
    if not text:
        return None

    command_start = text.find("/task")
    if command_start < 0:
        return None

    command_text = text[command_start:].strip()
    parts = command_text.split()
    if not parts or parts[0] != "/task":
        return None

    if len(parts) < 2:
        raise ValueError("Invalid /task command. Expected: /task <action_item_id>.")

    try:
        action_item_id = int(parts[1])
    except ValueError as exc:
        raise ValueError("Invalid /task command. action_item_id must be a number.") from exc

    return FeishuTaskCommand(action_item_id=action_item_id)


def extract_help_command(payload: dict[str, Any]) -> FeishuHelpCommand | None:
    # 解析 /help。
    text = _extract_text(payload)
    if not text:
        return None

    command_text = text.strip()
    if command_text.split()[0] == "/help":
        return FeishuHelpCommand()

    return None


def extract_remember_command(payload: dict[str, Any]) -> FeishuRememberCommand | None:
    # 解析 /remember <alias> = <target>，也支持 /remember project <alias> = <target>。
    text = _extract_text(payload)
    if not text:
        return None

    command_text = text.strip()
    if not command_text.startswith("/remember"):
        return None

    body = command_text.removeprefix("/remember").strip()
    if "=" not in body:
        raise ValueError("Invalid /remember command. Expected: /remember <alias> = <target>.")

    raw_alias, raw_target = [part.strip() for part in body.split("=", 1)]
    memory_type = "alias"
    alias_parts = raw_alias.split(maxsplit=1)
    if len(alias_parts) == 2 and alias_parts[0] in {"project", "user", "team", "alias"}:
        memory_type = alias_parts[0]
        raw_alias = alias_parts[1].strip()

    if not raw_alias or not raw_target:
        raise ValueError("Invalid /remember command. alias and target are required.")

    return FeishuRememberCommand(alias=raw_alias, target=raw_target, memory_type=memory_type)


def extract_forget_command(payload: dict[str, Any]) -> FeishuForgetCommand | None:
    # 解析 /forget <alias>。
    text = _extract_text(payload)
    if not text:
        return None

    command_text = text.strip()
    if not command_text.startswith("/forget"):
        return None

    alias = command_text.removeprefix("/forget").strip()
    if not alias:
        raise ValueError("Invalid /forget command. Expected: /forget <alias>.")

    return FeishuForgetCommand(alias=alias)


def extract_memory_command(payload: dict[str, Any]) -> FeishuMemoryCommand | None:
    # 解析 /memory。
    text = _extract_text(payload)
    if not text:
        return None

    if text.strip().split()[0] == "/memory":
        return FeishuMemoryCommand()

    return None


def extract_bind_channel_command(payload: dict[str, Any]) -> FeishuBindChannelCommand | None:
    # 解析 /bind-channel <project_keyword>。
    text = _extract_text(payload)
    if not text:
        return None

    command_text = text.strip()
    if not command_text.startswith("/bind-channel"):
        return None

    project_keyword = command_text.removeprefix("/bind-channel").strip()
    if not project_keyword:
        raise ValueError("Invalid /bind-channel command. Expected: /bind-channel <project_keyword>.")

    return FeishuBindChannelCommand(project_keyword=project_keyword)


def extract_follow_up_reply(payload: dict[str, Any]) -> FeishuFollowUpReply | None:
    # 解析用户对跟进提醒的回复，例如“#12 完成了”“12号有风险”。
    text = _extract_text(payload)
    if not text:
        return None

    action_item_id = _extract_action_item_id(text)
    if action_item_id is None:
        return None

    target_status = _extract_reply_status(text)
    if not target_status:
        return None

    return FeishuFollowUpReply(action_item_id=action_item_id, status=target_status)


def extract_message_text(payload: dict[str, Any]) -> str | None:
    # 对外暴露的纯文本提取函数，供 Agent 自然语言流程使用。
    return _extract_text(payload)


def _extract_action_item_id(text: str) -> int | None:
    # 从文本里提取行动项 ID，支持 #12、12号任务等格式。
    patterns = (
        r"#\s*(\d+)",
        r"(?:任务|行动项)?\s*(\d+)\s*(?:号|號)\s*(?:任务|行动项)?",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


def _extract_reply_status(text: str) -> str | None:
    # 把用户回复里的口语状态映射成系统状态。
    if any(keyword in text for keyword in ("完成了", "已完成", "做完了", "搞定了", "done", "Done")):
        return "completed"
    if any(keyword in text for keyword in ("还在进行中", "进行中", "推进中", "处理中")):
        return "in_progress"
    if any(keyword in text for keyword in ("有风险", "风险", "阻塞", "blocked", "Blocked")):
        return "failed"
    if any(keyword in text for keyword in ("待处理", "未开始", "先不做", "待办")):
        return "pending"
    return None


def _extract_text(payload: dict[str, Any]) -> str | None:
    # 飞书 payload 可能把文本放在不同位置，这里统一提取。
    candidates = [
        payload.get("text"),
        payload.get("message", {}).get("text") if isinstance(payload.get("message"), dict) else None,
        payload.get("event", {}).get("message", {}).get("content")
        if isinstance(payload.get("event"), dict)
        else None,
        payload.get("message", {}).get("content") if isinstance(payload.get("message"), dict) else None,
    ]

    for candidate in candidates:
        text = _coerce_text(candidate)
        if text:
            return text

    return None


def _coerce_text(value: Any) -> str | None:
    # 把字符串、JSON 字符串或 dict content 统一转成纯文本。
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped

        return _coerce_text(parsed)

    if isinstance(value, dict):
        text = value.get("text") or value.get("content")
        return text.strip() if isinstance(text, str) and text.strip() else None

    return None
