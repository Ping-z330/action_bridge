import re

from app.agent.schemas import AgentIntent
from app.schemas.task_result import ActionItemListItem


MIN_REFERENCE_SCORE = 2


def resolve_task_reference_intent(
    intent: AgentIntent | None,
    message: str,
    action_items: list[ActionItemListItem],
    recent_task_ids: list[int] | None = None,
) -> AgentIntent | None:
    if not intent or intent.name != "clarify_task_reference":
        return intent

    target_intent = _target_intent_from_filters(intent.filters)
    if not target_intent:
        return intent

    reference_note = ""
    matched_item, reference_note = _find_contextual_task_reference(message, action_items, recent_task_ids or [])
    if not matched_item:
        matched_item = _find_unique_task_reference(message, action_items)
        if matched_item:
            reference_note = "根据任务标题或会议标题匹配到该任务"
    if not matched_item:
        return intent

    filters = {
        "action_item_id": str(matched_item.id),
    }
    if reference_note:
        filters["reference_note"] = reference_note
    if target_intent == "update_task_owner":
        filters["owner_name"] = intent.filters["owner_name"]
    elif target_intent == "update_task_deadline":
        filters["deadline"] = intent.filters["deadline"]
    elif target_intent == "update_task_status":
        filters["status"] = intent.filters["status"]
    else:
        return intent

    return AgentIntent(name=target_intent, filters=filters)


def _find_contextual_task_reference(
    message: str,
    action_items: list[ActionItemListItem],
    recent_task_ids: list[int],
) -> tuple[ActionItemListItem | None, str]:
    if not recent_task_ids:
        return None, ""

    index = _extract_context_index(message)
    if index is None or index < 0 or index >= len(recent_task_ids):
        return None, ""

    target_id = recent_task_ids[index]
    item = next((item for item in action_items if item.id == target_id), None)
    if not item:
        return None, ""
    return item, f"根据刚才任务列表中的第 {index + 1} 个任务解析"


def _extract_context_index(message: str) -> int | None:
    normalized = message.strip().lower()
    if any(keyword in normalized for keyword in ("刚才那个", "刚刚那个", "上一个", "这个任务", "那个任务")):
        return 0

    digit_match = re.search(r"第\s*(\d+)\s*个", normalized)
    if digit_match:
        return int(digit_match.group(1)) - 1

    chinese_indexes = {
        "第一个": 0,
        "第二个": 1,
        "第三个": 2,
        "第四个": 3,
        "第五个": 4,
        "第六个": 5,
        "第七个": 6,
        "第八个": 7,
        "第九个": 8,
        "第十个": 9,
    }
    for keyword, index in chinese_indexes.items():
        if keyword in normalized:
            return index
    return None


def _target_intent_from_filters(filters: dict[str, str]) -> str | None:
    if filters.get("target_intent"):
        return filters["target_intent"]
    if filters.get("owner_name"):
        return "update_task_owner"
    if filters.get("deadline"):
        return "update_task_deadline"
    if filters.get("status"):
        return "update_task_status"
    return None


def _find_unique_task_reference(message: str, action_items: list[ActionItemListItem]) -> ActionItemListItem | None:
    scored_items = [
        (item, _score_task_reference(message, item))
        for item in action_items
    ]
    scored_items = [(item, score) for item, score in scored_items if score >= MIN_REFERENCE_SCORE]
    if not scored_items:
        return None

    best_score = max(score for _item, score in scored_items)
    best_items = [item for item, score in scored_items if score == best_score]
    return best_items[0] if len(best_items) == 1 else None


def _score_task_reference(message: str, item: ActionItemListItem) -> int:
    normalized_message = _normalize_reference_text(message)
    title_score = _longest_common_substring_length(normalized_message, _normalize_reference_text(item.title))
    meeting_score = _longest_common_substring_length(
        normalized_message,
        _normalize_reference_text(item.meeting_title),
    )
    return max(title_score, meeting_score)


def _normalize_reference_text(value: str) -> str:
    ignored_words = (
        "把",
        "那个",
        "这个",
        "任务",
        "行动项",
        "事项",
        "交给",
        "转给",
        "改成",
        "改为",
        "负责人",
        "负责",
        "推进",
        "一下",
        "完成",
        "进行中",
        "有风险",
    )
    normalized = value.lower()
    for word in ignored_words:
        normalized = normalized.replace(word, "")
    return "".join(char for char in normalized if not char.isspace())


def _longest_common_substring_length(left: str, right: str) -> int:
    if not left or not right:
        return 0

    previous = [0] * (len(right) + 1)
    best = 0
    for left_char in left:
        current = [0]
        for index, right_char in enumerate(right, start=1):
            if left_char == right_char:
                score = previous[index - 1] + 1
                best = max(best, score)
                current.append(score)
            else:
                current.append(0)
        previous = current
    return best
