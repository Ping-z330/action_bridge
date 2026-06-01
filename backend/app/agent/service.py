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

CREATE_TASK_TRIGGERS = (
    "加一个任务",
    "加个任务",
    "创建任务",
    "新增任务",
    "新增行动项",
    "添加任务",
    "安排一个任务",
)

DEADLINE_PATTERN = (
    r"(?:今天|今日|明天|后天|本周[一二三四五六日天]|下周[一二三四五六日天]|"
    r"周[一二三四五六日天]|星期[一二三四五六日天]|"
    r"\d{4}-\d{1,2}-\d{1,2}|\d{4}年\d{1,2}月\d{1,2}日)"
    r"(?:\s*(?:上午|中午|下午|晚上|今晚|下班前|晚些时候|"
    r"\d{1,2}(?::|：|点)\d{0,2}))?(?:前|之前)?"
)


def handle_agent_message(message: str, action_items: list[ActionItemListItem]) -> AgentResponse:
    intent = detect_intent(message)
    if not intent:
        return AgentResponse(handled=False, message="No supported agent intent found.")

    if intent.name == "help":
        return AgentResponse(
            handled=True,
            intent=intent,
            message="已发送 ActionBridge 使用帮助。",
        )

    if intent.name == "create_task":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"准备创建任务：{intent.filters['title']}。",
        )

    if intent.name == "create_task_missing_info":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"任务信息不完整，还需要补充：{intent.filters['missing_fields']}。",
        )

    if intent.name == "update_task_deadline":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"准备修改任务 {intent.filters['action_item_id']} 的截止时间。",
        )

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

    if _is_help_message(normalized):
        return AgentIntent(name="help")

    create_task_intent = _detect_create_task_intent(normalized)
    if create_task_intent:
        return create_task_intent

    deadline_update_intent = _detect_deadline_update_intent(normalized)
    if deadline_update_intent:
        return deadline_update_intent

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


def _detect_create_task_intent(message: str) -> AgentIntent | None:
    if not any(trigger in message for trigger in CREATE_TASK_TRIGGERS):
        return None

    body = _strip_create_task_prefix(message)
    parsed = _parse_create_task_body(body)
    missing = [
        label
        for label, key in (("任务目标", "title"), ("负责人", "owner_name"), ("截止时间", "deadline"))
        if not parsed.get(key)
    ]

    if missing:
        filters = {key: value for key, value in parsed.items() if value}
        filters["missing_fields"] = "、".join(missing)
        filters["raw_text"] = body
        return AgentIntent(name="create_task_missing_info", filters=filters)

    return AgentIntent(name="create_task", filters=parsed)


def _detect_deadline_update_intent(message: str) -> AgentIntent | None:
    action_item_id = _extract_action_item_id(message)
    if action_item_id is None:
        return None

    patterns = (
        rf"(?:截止时间|截止日期)?\s*(?:延期到|延到|改到|改成|调整到|设置为)\s*(?P<deadline>{DEADLINE_PATTERN})",
        rf"(?:延期|延后)\s*(?:到|至)?\s*(?P<deadline>{DEADLINE_PATTERN})",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            deadline = _clean_task_field(match.group("deadline"))
            if deadline:
                return AgentIntent(
                    name="update_task_deadline",
                    filters={
                        "action_item_id": str(action_item_id),
                        "deadline": deadline,
                    },
                )

    return None


def _strip_create_task_prefix(message: str) -> str:
    normalized = message.strip()
    pattern = (
        r"^(?:帮我|请|麻烦)?(?:加一个任务|加个任务|创建任务|新增任务|新增行动项|"
        r"添加任务|安排一个任务)\s*[：:，,]?\s*"
    )
    return re.sub(pattern, "", normalized).strip()


def _parse_create_task_body(body: str) -> dict[str, str]:
    normalized = body.strip(" ，。！？：:；;")
    if not normalized:
        return {}

    patterns = (
        rf"^(?P<owner>.{{1,20}}?)\s*(?P<deadline>{DEADLINE_PATTERN})\s*(?P<title>.+)$",
        rf"^(?P<owner>.{{1,20}}?)\s*(?:在|于)?(?P<deadline>{DEADLINE_PATTERN})\s*(?:前)?\s*(?P<title>.+)$",
    )

    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            owner = _clean_task_field(match.group("owner"))
            deadline = _clean_task_field(match.group("deadline"))
            title = _clean_task_title(match.group("title"))
            return {
                "title": title,
                "owner_name": owner,
                "deadline": deadline,
            }

    parsed: dict[str, str] = {}
    deadline_match = re.search(DEADLINE_PATTERN, normalized)
    if deadline_match:
        parsed["deadline"] = _clean_task_field(deadline_match.group(0))
        before_deadline = normalized[: deadline_match.start()]
        after_deadline = normalized[deadline_match.end() :]
        parsed["owner_name"] = _clean_task_field(before_deadline)
        parsed["title"] = _clean_task_title(after_deadline)
    else:
        parsed["title"] = _clean_task_title(normalized)

    return {key: value for key, value in parsed.items() if value}


def _clean_task_field(value: str) -> str:
    token = value.strip(" ，。！？：:；;、")
    token = re.sub(r"^(由|让|请|给)\s*", "", token)
    return token.strip()


def _clean_task_title(value: str) -> str:
    token = _clean_task_field(value)
    token = re.sub(r"^(完成|负责完成|去完成)\s*", "", token)
    return token.strip()


def _is_help_message(message: str) -> bool:
    normalized = message.strip().lower()
    return normalized in {
        "help",
        "/help",
        "帮助",
        "使用帮助",
        "你能做什么",
        "怎么使用",
        "如何使用",
        "功能说明",
    }


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
