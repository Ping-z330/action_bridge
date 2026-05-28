from dataclasses import dataclass
import json
from typing import Any

from app.core.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    PARSER_PROVIDER,
)

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - covered through runtime fallback
    OpenAI = None  # type: ignore[assignment]

@dataclass
class ParsedActionItem:
    title: str
    owner_name: str
    deadline: str
    status: str = "pending"


@dataclass
class ParsedMeeting:
    summary: str
    decisions: list[str]
    action_items: list[ParsedActionItem]


def parse_transcript(title: str, transcript: str) -> ParsedMeeting:
    provider = PARSER_PROVIDER.lower()

    if provider == "deepseek" and _should_use_deepseek():
        parsed = _parse_with_deepseek(title, transcript)
        if parsed:
            return parsed

    if provider == "openai" and _should_use_openai():
        parsed = _parse_with_openai(title, transcript)
        if parsed:
            return parsed

    return _parse_with_rules(title, transcript)


def _should_use_deepseek() -> bool:
    return PARSER_PROVIDER.lower() == "deepseek" and bool(DEEPSEEK_API_KEY) and OpenAI is not None


def _should_use_openai() -> bool:
    return PARSER_PROVIDER.lower() == "openai" and bool(OPENAI_API_KEY) and OpenAI is not None


def _parse_with_deepseek(title: str, transcript: str) -> ParsedMeeting | None:
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    json_example = {
        "summary": "一句话总结会议重点",
        "decisions": ["结论1", "结论2"],
        "action_items": [
            {
                "title": "行动项标题",
                "owner_name": "负责人",
                "deadline": "截止时间，没有则写 Pending confirmation",
                "status": "pending",
            }
        ],
    }

    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Please extract structured meeting results and return json only. "
                        "Use this exact JSON shape as a guide: "
                        f"{json.dumps(json_example, ensure_ascii=False)}. "
                        "Keep the summary concise. "
                        "Only include explicit decisions. "
                        "If owner or deadline is missing, use 'Pending confirmation'."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Meeting title: {title}\nTranscript:\n{transcript}",
                },
            ],
            response_format={"type": "json_object"},
        )
    except Exception:
        return None

    content = response.choices[0].message.content if response.choices else None
    if not content:
        return None

    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None

    return _parsed_meeting_from_payload(payload)


def _parse_with_openai(title: str, transcript: str) -> ParsedMeeting | None:
    client = OpenAI(api_key=OPENAI_API_KEY)
    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "decisions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "action_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "owner_name": {"type": "string"},
                        "deadline": {"type": "string"},
                        "status": {"type": "string"},
                    },
                    "required": ["title", "owner_name", "deadline", "status"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["summary", "decisions", "action_items"],
        "additionalProperties": False,
    }

    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You extract structured meeting results. "
                        "Return JSON only. Keep the summary concise. "
                        "List explicit decisions only. "
                        "For missing owners or deadlines, use 'Pending confirmation'."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Meeting title: {title}\nTranscript:\n{transcript}",
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "meeting_parse_result",
                    "schema": schema,
                    "strict": True,
                }
            },
        )
    except Exception:
        return None

    output_text = getattr(response, "output_text", None)
    if not output_text:
        return None

    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        return None

    return _parsed_meeting_from_payload(payload)


def _parse_with_rules(title: str, transcript: str) -> ParsedMeeting:
    lines = [line.strip("- ").strip() for line in transcript.splitlines() if line.strip()]
    summary = lines[0] if lines else f"Transcript received for {title}."

    decisions = [line for line in lines if any(keyword in line.lower() for keyword in ("decide", "decision", "confirm"))]
    if not decisions and lines:
        decisions = [lines[min(1, len(lines) - 1)]]

    action_items: list[ParsedActionItem] = []
    for line in lines:
        lowered = line.lower()
        if any(keyword in lowered for keyword in ("todo", "follow up", "follow-up", "action", "next step")):
            action_items.append(
                ParsedActionItem(
                    title=line,
                    owner_name="Pending confirmation",
                    deadline="Pending confirmation",
                )
            )

    if not action_items and lines:
        fallback = lines[-1]
        action_items.append(
            ParsedActionItem(
                title=fallback,
                owner_name="Pending confirmation",
                deadline="Pending confirmation",
            )
        )

    return ParsedMeeting(summary=summary, decisions=decisions, action_items=action_items)


def _parsed_meeting_from_payload(payload: dict[str, Any]) -> ParsedMeeting:
    action_items = [
        ParsedActionItem(
            title=item.get("title", "").strip() or "Action item needs review",
            owner_name=item.get("owner_name", "").strip() or "Pending confirmation",
            deadline=item.get("deadline", "").strip() or "Pending confirmation",
            status=item.get("status", "").strip() or "pending",
        )
        for item in payload.get("action_items", [])
    ]

    if not action_items:
        action_items.append(
            ParsedActionItem(
                title="Action item needs review",
                owner_name="Pending confirmation",
                deadline="Pending confirmation",
                status="pending",
            )
        )

    decisions = [item.strip() for item in payload.get("decisions", []) if item.strip()]
    if not decisions:
        decisions = ["Decision needs review"]

    summary = str(payload.get("summary", "")).strip() or "Summary needs review"

    return ParsedMeeting(summary=summary, decisions=decisions, action_items=action_items)
