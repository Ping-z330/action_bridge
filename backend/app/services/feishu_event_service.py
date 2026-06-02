import json
import re
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class FeishuMeetingCommand:
    title: str
    transcript: str


@dataclass(frozen=True)
class FeishuDoneCommand:
    action_item_id: int


@dataclass(frozen=True)
class FeishuTasksCommand:
    limit: int = 10


@dataclass(frozen=True)
class FeishuTaskCommand:
    action_item_id: int


@dataclass(frozen=True)
class FeishuHelpCommand:
    pass


@dataclass(frozen=True)
class FeishuRememberCommand:
    alias: str
    target: str
    memory_type: str = "alias"


@dataclass(frozen=True)
class FeishuForgetCommand:
    alias: str


@dataclass(frozen=True)
class FeishuMemoryCommand:
    pass


@dataclass(frozen=True)
class FeishuFollowUpReply:
    action_item_id: int
    status: str


def extract_challenge(payload: dict[str, Any]) -> str | None:
    challenge = payload.get("challenge") or payload.get("Challenge")
    if isinstance(challenge, str) and challenge:
        return challenge
    return None


def extract_event_dedup_key(payload: dict[str, Any]) -> str | None:
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
    text = _extract_text(payload)
    if not text:
        return None

    command_start = text.find("/tasks")
    if command_start < 0:
        return None

    return FeishuTasksCommand()


def extract_task_command(payload: dict[str, Any]) -> FeishuTaskCommand | None:
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
    text = _extract_text(payload)
    if not text:
        return None

    command_text = text.strip()
    if command_text.split()[0] == "/help":
        return FeishuHelpCommand()

    return None


def extract_remember_command(payload: dict[str, Any]) -> FeishuRememberCommand | None:
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
    text = _extract_text(payload)
    if not text:
        return None

    if text.strip().split()[0] == "/memory":
        return FeishuMemoryCommand()

    return None


def extract_follow_up_reply(payload: dict[str, Any]) -> FeishuFollowUpReply | None:
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
    return _extract_text(payload)


def _extract_action_item_id(text: str) -> int | None:
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
