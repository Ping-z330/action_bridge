import re

from app.agent.schemas import AgentIntent
from app.schemas.task_result import ActionItemListItem


# 标题/会议标题相似度至少达到这个分数，才认为可能匹配到某个任务。
MIN_REFERENCE_SCORE = 2


def resolve_task_reference_intent(
    intent: AgentIntent | None,
    message: str,
    action_items: list[ActionItemListItem],
    recent_task_ids: list[int] | None = None,
) -> AgentIntent | None:
    # 入口函数：把“用户想改任务但没说编号”的意图，尝试补全成具体的任务修改意图。
    if not intent or intent.name != "clarify_task_reference":
        return intent

    # 先从原始 filters 判断用户到底想修改什么：负责人、截止时间，还是状态。
    target_intent = _target_intent_from_filters(intent.filters)
    if not target_intent:
        return intent

    reference_note = ""
    # 优先使用最近一次任务列表的上下文，比如“第二个任务改成已完成”。
    matched_item, reference_note = _find_contextual_task_reference(message, action_items, recent_task_ids or [])
    if not matched_item:
        # 如果没有上下文编号，再尝试根据消息和任务标题/会议标题的相似度来唯一匹配。
        matched_item = _find_unique_task_reference(message, action_items)
        if matched_item:
            reference_note = "根据任务标题或会议标题匹配到该任务"
    if not matched_item:
        return intent

    # 找到具体任务后，把缺失的 action_item_id 补进 filters。
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
    # 根据最近展示给用户的任务列表，解析“刚才那个”“第 2 个”等上下文引用。
    if not recent_task_ids:
        return None, ""

    # index 是从 0 开始的列表下标；用户说“第 1 个”会转成 0。
    index = _extract_context_index(message)
    if index is None or index < 0 or index >= len(recent_task_ids):
        return None, ""

    # recent_task_ids 只保存编号，这里再回到 action_items 中找到完整任务对象。
    target_id = recent_task_ids[index]
    item = next((item for item in action_items if item.id == target_id), None)
    if not item:
        return None, ""
    return item, f"根据刚才任务列表中的第 {index + 1} 个任务解析"


def _extract_context_index(message: str) -> int | None:
    # 从用户消息里提取“最近任务列表里的第几个任务”。
    normalized = message.strip().lower()
    # “刚才那个/这个任务”默认指最近列表里的第一个任务。
    if any(keyword in normalized for keyword in ("刚才那个", "刚刚那个", "上一个", "这个任务", "那个任务")):
        return 0

    # 支持阿拉伯数字写法，比如“第 2 个”。
    digit_match = re.search(r"第\s*(\d+)\s*个", normalized)
    if digit_match:
        return int(digit_match.group(1)) - 1

    # 支持中文数字写法，比如“第二个”。
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
    # 根据已有字段反推出真正要执行的修改意图。
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
    # 给每个任务打相似度分，只在最高分任务唯一时才自动选中，避免误改任务。
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
    # 同时比较用户消息与任务标题、会议标题，取更高的相似度。
    normalized_message = _normalize_reference_text(message)
    title_score = _longest_common_substring_length(normalized_message, _normalize_reference_text(item.title))
    meeting_score = _longest_common_substring_length(
        normalized_message,
        _normalize_reference_text(item.meeting_title),
    )
    return max(title_score, meeting_score)


def _normalize_reference_text(value: str) -> str:
    # 去掉常见的操作词和空格，只保留更能代表任务主题的文字。
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
    # 计算最长公共连续子串长度，用来粗略衡量两段文字有多像。
    if not left or not right:
        return 0

    # 动态规划：previous/current 分别代表上一行和当前行，避免创建完整二维表。
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
