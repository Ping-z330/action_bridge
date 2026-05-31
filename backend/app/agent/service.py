import re

from app.agent.schemas import AgentIntent, AgentResponse
from app.agent.tools import filter_tasks, summarize_project_progress
from app.schemas.task_result import ActionItemListItem


TASK_QUERY_KEYWORDS = (
    "任务",
    "行动项",
    "进度",
    "到期",
    "逾期",
    "未完成",
    "进行中",
    "待处理",
    "有风险",
    "负责",
)


def handle_agent_message(message: str, action_items: list[ActionItemListItem]) -> AgentResponse:
    intent = detect_intent(message)
    if not intent:
        return AgentResponse(handled=False, message="No supported agent intent found.")

    if intent.name == "update_task_status":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=_build_update_message(intent.filters),
        )

    if intent.name == "summarize_project":
        keyword = intent.filters["keyword"]
        summary = summarize_project_progress(action_items, keyword)
        return AgentResponse(
            handled=True,
            intent=intent,
            items=summary.items,
            progress_summary=summary,
            message=_build_progress_message(summary.total_count, keyword),
        )

    if intent.name == "query_tasks":
        items = filter_tasks(action_items, intent.filters)
        return AgentResponse(
            handled=True,
            intent=intent,
            items=items,
            message=_build_query_message(items, intent.filters),
        )

    return AgentResponse(handled=False, message="Unsupported agent intent.")


def detect_intent(message: str) -> AgentIntent | None:
    normalized = message.strip()
    if not normalized:
        return None

    update_intent = _detect_status_update_intent(normalized)
    if update_intent:
        return update_intent

    progress_intent = _detect_progress_summary_intent(normalized)
    if progress_intent:
        return progress_intent

    filters: dict[str, str] = {}
    lowered = normalized.lower()

    if any(keyword in normalized for keyword in ("今天", "今日", "本日")):
        filters["due_status"] = "due_today"
        filters["open_only"] = "true"

    if any(keyword in normalized for keyword in ("逾期", "过期", "超期")):
        filters["due_status"] = "overdue"
        filters["open_only"] = "true"

    if "进行中" in normalized:
        filters["status"] = "in_progress"

    if "待处理" in normalized:
        filters["status"] = "pending"

    if any(keyword in normalized for keyword in ("有风险", "风险")):
        filters["status"] = "failed"

    if any(keyword in normalized for keyword in ("未完成", "没完成", "还没做", "待办")):
        filters["open_only"] = "true"

    owner = _extract_owner(normalized)
    if owner:
        filters["owner"] = owner
        filters.setdefault("open_only", "true")

    keyword = _extract_keyword(normalized)
    if keyword:
        filters["keyword"] = keyword
        filters.setdefault("open_only", "true")

    if filters:
        return AgentIntent(name="query_tasks", filters=filters)

    if any(keyword in normalized for keyword in TASK_QUERY_KEYWORDS) or "task" in lowered:
        return AgentIntent(name="query_tasks", filters={"open_only": "true"})

    return None


def _detect_progress_summary_intent(message: str) -> AgentIntent | None:
    if not any(keyword in message for keyword in ("进度", "总结", "完成情况", "风险", "怎么样")):
        return None

    keyword = _extract_progress_keyword(message)
    if not keyword or _is_filter_phrase(keyword):
        return None

    return AgentIntent(name="summarize_project", filters={"keyword": keyword})


def _extract_progress_keyword(message: str) -> str | None:
    patterns = (
        r"(.{2,24})(?:项目)?(?:现在|当前|目前)?(?:进度|完成情况)(?:怎么样|如何)?",
        r"(?:总结|汇总|分析)(?:一下)?(.{2,24})(?:项目)?",
        r"(.{2,24})(?:项目)?(?:有哪些|有什么)?风险",
        r"(.{2,24})(?:项目)?怎么样",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            keyword = _clean_query_token(match.group(1))
            if keyword:
                return keyword
    return None


def _detect_status_update_intent(message: str) -> AgentIntent | None:
    action_item_id = _extract_action_item_id(message)
    if action_item_id is None:
        return None

    target_status = _extract_target_status(message)
    if not target_status:
        return None

    return AgentIntent(
        name="update_task_status",
        filters={
            "action_item_id": str(action_item_id),
            "status": target_status,
        },
    )


def _extract_action_item_id(message: str) -> int | None:
    patterns = (
        r"(?:#|任务|行动项)?\s*(\d+)\s*(?:号|號)?\s*(?:任务|行动项)?",
        r"(?:任务|行动项)\s*(?:#)?\s*(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return int(match.group(1))
    return None


def _extract_target_status(message: str) -> str | None:
    if any(keyword in message for keyword in ("已完成", "完成", "做完", "搞定", "done", "Done")):
        return "completed"
    if any(keyword in message for keyword in ("进行中", "处理中", "开始做", "推进中")):
        return "in_progress"
    if any(keyword in message for keyword in ("有风险", "风险", "阻塞", "blocked", "Blocked")):
        return "failed"
    if any(keyword in message for keyword in ("待处理", "未开始", "待办", "重新打开")):
        return "pending"
    return None


def _extract_owner(message: str) -> str | None:
    patterns = (
        r"(.{1,12})负责(?:的)?(?:任务|行动项|事项)",
        r"(.{1,12})(?:还有|有|的)(?:哪些|什么)?(?:未完成|待处理|进行中)?(?:任务|行动项)",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            owner = _clean_query_token(match.group(1))
            if owner and not _is_filter_phrase(owner):
                return owner
    return None


def _extract_keyword(message: str) -> str | None:
    patterns = (
        r"(.{2,20})(?:项目)?(?:相关|有关)的?(?:任务|行动项|进度)",
        r"(.{2,20})(?:项目)?(?:进度|还有哪些|还有什么)",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            keyword = _clean_query_token(match.group(1))
            if keyword and not _is_filter_phrase(keyword):
                return keyword
    return None


def _clean_query_token(value: str) -> str:
    token = value.strip(" ，。！？：:「」『』【】[]()（）")
    prefixes = ("帮我看看", "帮我查", "查询", "查看", "看一下", "看看", "请问", "目前", "当前")
    for prefix in prefixes:
        if token.startswith(prefix):
            token = token[len(prefix) :].strip()
    return token


def _build_query_message(items: list[ActionItemListItem], filters: dict[str, str]) -> str:
    if not items:
        return "没有找到符合条件的任务。"

    if filters.get("due_status") == "due_today":
        return f"找到 {len(items)} 个今天到期的任务。"
    if filters.get("due_status") == "overdue":
        return f"找到 {len(items)} 个逾期任务。"
    if filters.get("owner"):
        return f"找到 {len(items)} 个由 {filters['owner']} 负责的任务。"
    if filters.get("keyword"):
        return f"找到 {len(items)} 个与 {filters['keyword']} 相关的任务。"
    return f"找到 {len(items)} 个符合条件的任务。"


def _build_update_message(filters: dict[str, str]) -> str:
    status_label = {
        "pending": "待处理",
        "in_progress": "进行中",
        "completed": "已完成",
        "failed": "有风险",
    }.get(filters.get("status", ""), filters.get("status", ""))
    return f"准备将任务 {filters.get('action_item_id')} 更新为：{status_label}。"


def _build_progress_message(total_count: int, keyword: str) -> str:
    if total_count == 0:
        return f"没有找到与 {keyword} 相关的任务。"
    return f"已生成 {keyword} 的项目进度总结。"


def _is_filter_phrase(value: str) -> bool:
    return any(
        keyword in value
        for keyword in (
            "今天",
            "今日",
            "本日",
            "到期",
            "逾期",
            "过期",
            "超期",
            "未完成",
            "没完成",
            "待处理",
            "进行中",
            "有风险",
            "风险",
        )
    )
