import json
from dataclasses import dataclass
from typing import Any

_PROCESSED_EVENT_IDS: set[str] = set()
_MAX_PROCESSED_EVENT_IDS = 512


@dataclass(frozen=True)
class FeishuMeetingCommand:
    title: str
    transcript: str


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


def mark_event_processing(dedup_key: str | None) -> bool:
    """Return False when the event was already seen in this process."""
    if not dedup_key:
        return True

    if dedup_key in _PROCESSED_EVENT_IDS:
        return False

    if len(_PROCESSED_EVENT_IDS) >= _MAX_PROCESSED_EVENT_IDS:
        _PROCESSED_EVENT_IDS.clear()

    _PROCESSED_EVENT_IDS.add(dedup_key)
    return True


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
