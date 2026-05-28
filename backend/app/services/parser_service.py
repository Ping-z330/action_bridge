from dataclasses import dataclass
import json
import re
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


GENERIC_SUMMARIES = {
    "summary needs review",
    "meeting discussed related decisions",
    "meeting discussed project decisions",
    "meeting discussed beta version decisions",
}

GENERIC_DECISIONS = {
    "decision needs review",
    "project decision",
    "beta version related decision",
}

GENERIC_ACTION_TITLES = {
    "action item needs review",
    "follow up required",
}

ACTION_PREFIXES = ("Action:", "Next step:", "Todo:", "Follow up:", "Follow-up:")
ACTION_VERBS = (
    "更新",
    "确认",
    "补充",
    "完成",
    "跟进",
    "同步",
    "排查",
    "修复",
    "处理",
    "安排",
    "准备",
    "推进",
    "整理",
    "输出",
    "联调",
    "上线",
    "发布",
    "评审",
    "测试",
    "检查",
    "提供",
    "撰写",
    "设计",
    "实现",
)
PENDING_CONFIRMATION = "Pending confirmation"
DEFAULT_STATUS = "pending"

LEADING_OWNER_PATTERN = re.compile(
    r"^(?P<owner>"
    r"[A-Z][A-Z0-9_-]{1,20}"
    r"|"
    r"[\u4e00-\u9fff]{1,12}?(?:同学|经理|老师|负责人|总监|主管|组长|团队|小组|部门|前端|后端|测试|产品|设计|运营|开发)"
    r")(?P<rest>.*)$"
)
LEADING_TIME_PATTERN = re.compile(
    r"^(今天|明天|后天|本周|下周|今晚|今日|明日|周[一二三四五六日天]|"
    r"[上下]午|中午|晚上|早上|明早|当天|本月底前|月底前|本周内|本周五前|"
    r"\d+[点天日周月号分]|[一二三四五六七八九十]+点)"
)


@dataclass
class ParsedActionItem:
    title: str
    owner_name: str
    deadline: str
    status: str = DEFAULT_STATUS


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
            return _merge_with_rule_fallback(parsed, title, transcript)

    if provider == "openai" and _should_use_openai():
        parsed = _parse_with_openai(title, transcript)
        if parsed:
            return _merge_with_rule_fallback(parsed, title, transcript)

    return _parse_with_rules(title, transcript)


def _has_real_value(value: str | None) -> bool:
    return bool(value) and not value.startswith("replace_with_")


def _should_use_deepseek() -> bool:
    return PARSER_PROVIDER.lower() == "deepseek" and _has_real_value(DEEPSEEK_API_KEY) and OpenAI is not None


def _should_use_openai() -> bool:
    return PARSER_PROVIDER.lower() == "openai" and _has_real_value(OPENAI_API_KEY) and OpenAI is not None


def _parse_with_deepseek(title: str, transcript: str) -> ParsedMeeting | None:
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    json_example = {
        "summary": "本次会议确认了上线延期和相关分工安排。",
        "decisions": [
            "Beta 版本延期到周五上线。",
            "周三前完成落地页最终文案确认。",
        ],
        "action_items": [
            {
                "title": "更新落地页文案和按钮状态。",
                "owner_name": "前端同学",
                "deadline": "周三",
                "status": "pending",
            },
            {
                "title": "确认客户通知文案并同步销售团队。",
                "owner_name": "产品经理",
                "deadline": "明天下午前",
                "status": "pending",
            },
        ],
    }

    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract structured meeting results and must return JSON only. "
                        "Do not summarize away concrete tasks. "
                        "Every explicit action, next step, owner assignment, or follow-up in the transcript must appear in action_items. "
                        "If the transcript contains multiple actions, return multiple action_items. "
                        "Decisions must stay specific and should be close to the original wording. "
                        "Separate task content from owner_name whenever the transcript clearly starts with an owner or role. "
                        "Do not repeat the owner inside title when owner_name is already known. "
                        "Do not use vague phrases like 'project decision' or 'follow up required'. "
                        f"If owner or deadline is missing, use '{PENDING_CONFIRMATION}'. "
                        "Use this exact JSON shape as a guide: "
                        f"{json.dumps(json_example, ensure_ascii=False)}"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Meeting title: {title}\n"
                        "Please extract:\n"
                        "1. One concise summary sentence.\n"
                        "2. A list of explicit decisions.\n"
                        "3. A list of all explicit action items.\n\n"
                        f"Transcript:\n{transcript}"
                    ),
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
            "decisions": {"type": "array", "items": {"type": "string"}},
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
                        "Return JSON only. "
                        "Keep the summary concise. "
                        "List explicit decisions only. "
                        "Every explicit task or next step must appear in action_items. "
                        "If the task text clearly starts with an owner or role, move that value to owner_name instead of repeating it in title. "
                        f"If owner or deadline is missing, use '{PENDING_CONFIRMATION}'."
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
                _build_action_item(
                    title=line,
                    owner_name=PENDING_CONFIRMATION,
                    deadline=PENDING_CONFIRMATION,
                )
            )

    if not action_items and lines:
        action_items.append(
            _build_action_item(
                title=lines[-1],
                owner_name=PENDING_CONFIRMATION,
                deadline=PENDING_CONFIRMATION,
            )
        )

    return ParsedMeeting(summary=summary, decisions=decisions, action_items=action_items)


def _parsed_meeting_from_payload(payload: dict[str, Any]) -> ParsedMeeting:
    action_items = [
        _build_action_item(
            title=item.get("title", "").strip() or "Action item needs review",
            owner_name=item.get("owner_name", "").strip() or PENDING_CONFIRMATION,
            deadline=item.get("deadline", "").strip() or PENDING_CONFIRMATION,
            status=item.get("status", "").strip() or DEFAULT_STATUS,
        )
        for item in payload.get("action_items", [])
    ]

    if not action_items:
        action_items.append(
            _build_action_item(
                title="Action item needs review",
                owner_name=PENDING_CONFIRMATION,
                deadline=PENDING_CONFIRMATION,
                status=DEFAULT_STATUS,
            )
        )

    decisions = [item.strip() for item in payload.get("decisions", []) if item.strip()]
    if not decisions:
        decisions = ["Decision needs review"]

    summary = str(payload.get("summary", "")).strip() or "Summary needs review"

    return ParsedMeeting(summary=summary, decisions=decisions, action_items=action_items)


def _build_action_item(
    title: str,
    owner_name: str,
    deadline: str,
    status: str = DEFAULT_STATUS,
) -> ParsedActionItem:
    cleaned_title = _strip_action_prefix(title)
    cleaned_owner = owner_name.strip() or PENDING_CONFIRMATION

    if cleaned_owner == PENDING_CONFIRMATION:
        inferred_owner, inferred_title = _infer_owner_from_title(cleaned_title)
        if inferred_owner:
            cleaned_owner = inferred_owner
            cleaned_title = inferred_title
    else:
        cleaned_title = _remove_owner_prefix(cleaned_title, cleaned_owner)

    return ParsedActionItem(
        title=cleaned_title or title.strip() or "Action item needs review",
        owner_name=cleaned_owner,
        deadline=deadline.strip() or PENDING_CONFIRMATION,
        status=status.strip() or DEFAULT_STATUS,
    )


def _strip_action_prefix(title: str) -> str:
    normalized = title.strip()
    for prefix in ACTION_PREFIXES:
        if normalized.lower().startswith(prefix.lower()):
            return normalized[len(prefix) :].strip()
    return normalized


def _remove_owner_prefix(title: str, owner_name: str) -> str:
    normalized = title.strip()
    if owner_name and normalized.startswith(owner_name):
        return normalized[len(owner_name) :].lstrip("：:，, ")
    return normalized


def _infer_owner_from_title(title: str) -> tuple[str | None, str]:
    normalized = title.strip()
    if not normalized or normalized.startswith("请"):
        return None, normalized

    match = LEADING_OWNER_PATTERN.match(normalized)
    if not match:
        return None, normalized

    owner = match.group("owner").strip()
    remainder = match.group("rest").lstrip("：:，, ").strip()
    if not remainder or not _looks_like_action_clause(remainder):
        return None, normalized

    return owner, remainder


def _looks_like_action_clause(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False

    candidate = normalized
    for _ in range(3):
        time_match = LEADING_TIME_PATTERN.match(candidate)
        if not time_match:
            break
        candidate = candidate[time_match.end() :].lstrip("，,、 ").strip()

    return any((index := candidate.find(verb)) != -1 and index <= 2 for verb in ACTION_VERBS)


def _merge_with_rule_fallback(parsed: ParsedMeeting, title: str, transcript: str) -> ParsedMeeting:
    rule_based = _parse_with_rules(title, transcript)

    summary = parsed.summary
    if _is_generic_summary(summary):
        summary = rule_based.summary

    decisions = parsed.decisions
    if _are_generic_decisions(decisions):
        decisions = rule_based.decisions

    action_items = parsed.action_items
    if _are_generic_action_items(action_items):
        action_items = rule_based.action_items

    return ParsedMeeting(summary=summary, decisions=decisions, action_items=action_items)


def _is_generic_summary(summary: str) -> bool:
    normalized = summary.strip().lower()
    return not normalized or normalized in GENERIC_SUMMARIES


def _are_generic_decisions(decisions: list[str]) -> bool:
    if not decisions:
        return True
    return all(item.strip().lower() in GENERIC_DECISIONS for item in decisions)


def _are_generic_action_items(action_items: list[ParsedActionItem]) -> bool:
    if not action_items:
        return True
    return all(item.title.strip().lower() in GENERIC_ACTION_TITLES for item in action_items)
