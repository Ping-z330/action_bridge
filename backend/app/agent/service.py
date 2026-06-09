import re

from app.agent.llm_intent_service import detect_llm_intent
from app.agent.schemas import AgentIntent, AgentResponse
from app.agent.tools import filter_tasks, summarize_project_progress
from app.schemas.task_result import ActionItemListItem


# 这些关键词用来判断用户是不是在问“任务/行动项/进度”相关问题。
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

# 这些触发词用来判断用户是不是想新建一个任务。
CREATE_TASK_TRIGGERS = (
    "加一个任务",
    "加个任务",
    "创建任务",
    "新增任务",
    "新增行动项",
    "添加任务",
    "安排一个任务",
)

# 识别中文日期/时间的正则表达式，比如“今天”“明天下午”“2026-06-07”等。
DEADLINE_PATTERN = (
    r"(?:今天|今日|明天|后天|本周[一二三四五六日天]|下周[一二三四五六日天]|"
    r"周[一二三四五六日天]|星期[一二三四五六日天]|"
    r"\d{4}-\d{1,2}-\d{1,2}|\d{4}年\d{1,2}月\d{1,2}日)"
    r"(?:\s*(?:上午|中午|下午|晚上|今晚|下班前|晚些时候|"
    r"\d{1,2}(?::|：|点)\d{0,2}))?(?:前|之前)?"
)


def handle_agent_message(message: str, action_items: list[ActionItemListItem]) -> AgentResponse:
    # 这是一个较简单的 Agent 入口：先识别意图，再根据意图直接返回响应。
    intent = detect_intent_with_fallback(message)
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

    if intent.name == "update_task_owner":
        return AgentResponse(
            handled=True,
            intent=intent,
            message=f"准备修改任务 {intent.filters['action_item_id']} 的负责人。",
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
    # 规则版意图识别入口：按优先级从“帮助、新建、修改、查询、总结”等方向逐个判断。
    normalized = message.strip()
    if not normalized:
        return None

    # 帮助类问题最简单，优先直接识别。
    if _is_help_message(normalized):
        return AgentIntent(name="help")

    # 新建任务通常包含明确触发词，比如“新增任务”“加一个任务”。
    create_task_intent = _detect_create_task_intent(normalized)
    if create_task_intent:
        return create_task_intent

    # 修改截止时间、负责人、状态都属于“修改任务”，这里依次判断。
    deadline_update_intent = _detect_deadline_update_intent(normalized)
    if deadline_update_intent:
        return deadline_update_intent

    owner_update_intent = _detect_owner_update_intent(normalized)
    if owner_update_intent:
        return owner_update_intent

    update_intent = _detect_status_update_intent(normalized)
    if update_intent:
        return update_intent

    # 查询任务是最常见的读取类操作，比如“今天到期的任务有哪些”。
    query_intent = _detect_query_tasks_intent(normalized)
    if query_intent:
        return query_intent

    # 如果用户像是在修改任务，但没说清任务编号，就返回“需要补充编号”的意图。
    clarification_intent = _detect_task_reference_clarification_intent(normalized)
    if clarification_intent:
        return clarification_intent

    # 项目进度总结比普通查询更聚合，所以单独识别。
    progress_intent = _detect_progress_summary_intent(normalized)
    if progress_intent:
        return progress_intent

    filters: dict[str, str] = {}
    lowered = normalized.lower()

    # 下面这一段是兜底的查询条件提取：从一句话里抽取状态、负责人、关键词等过滤条件。
    if any(keyword in normalized for keyword in ("今天", "今日", "本日")) and _has_task_query_context(normalized):
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


def _detect_query_tasks_intent(message: str) -> AgentIntent | None:
    # 识别“查询任务”类问题，并把用户说的条件转成 filters。
    filters: dict[str, str] = {}
    has_query_word = any(keyword in message for keyword in TASK_QUERY_KEYWORDS) or any(
        keyword in message for keyword in ("查询", "查看", "看看", "有哪些", "列出", "显示")
    )
    has_task_word = any(keyword in message for keyword in ("任务", "行动项", "事项"))

    if any(keyword in message for keyword in ("已完成", "已经完成", "完成的任务", "做完的任务")):
        filters["status"] = "completed"

    if "进行中" in message:
        filters["status"] = "in_progress"

    if "待处理" in message:
        filters["status"] = "pending"

    if any(keyword in message for keyword in ("有风险", "风险")):
        filters["status"] = "failed"

    if any(keyword in message for keyword in ("今天", "今日", "本日")):
        filters["due_status"] = "due_today"
        if filters.get("status") != "completed":
            filters["open_only"] = "true"

    if any(keyword in message for keyword in ("逾期", "过期", "超期")):
        filters["due_status"] = "overdue"
        if filters.get("status") != "completed":
            filters["open_only"] = "true"

    if any(keyword in message for keyword in ("未完成", "没完成", "还没做", "待办")):
        filters["open_only"] = "true"

    if filters and (has_query_word or has_task_word):
        return AgentIntent(name="query_tasks", filters=filters)

    return None


def _has_task_query_context(message: str) -> bool:
    # 防止只出现“今天”这种词就误判为任务查询，必须同时有任务语境。
    return any(keyword in message for keyword in TASK_QUERY_KEYWORDS) or any(
        keyword in message
        for keyword in ("查询", "查看", "看看", "有哪些", "列出", "显示", "任务", "行动项", "事项", "到期")
    )


def detect_intent_with_fallback(message: str) -> AgentIntent | None:
    # 先跑规则识别；规则不够可靠时，再交给大模型做兜底理解。
    rule_intent = detect_intent(message)
    if rule_intent and _should_use_rule_before_llm(message, rule_intent):
        return rule_intent

    llm_intent = detect_llm_intent(message)
    if llm_intent:
        return llm_intent

    return rule_intent


def _should_use_rule_before_llm(message: str, rule_intent: AgentIntent) -> bool:
    # 判断某个规则识别结果是否足够确定；如果不确定，就让 LLM 再判断一次。
    if rule_intent.name in {"help", "create_task", "create_task_missing_info"}:
        return True

    if rule_intent.name in {"update_task_deadline", "update_task_owner", "update_task_status"}:
        return True

    if rule_intent.name == "clarify_task_reference":
        return False

    if rule_intent.name == "summarize_project":
        return True

    if rule_intent.name == "query_tasks":
        if _looks_like_task_mutation(message):
            return False
        return rule_intent.filters != {"open_only": "true"}

    return False


def _detect_create_task_intent(message: str) -> AgentIntent | None:
    # 新建任务需要识别标题、负责人、截止时间；缺字段时返回 missing_info。
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
    # 修改截止时间必须先找到任务编号，否则不知道要改哪一个任务。
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





def _detect_owner_update_intent(message: str) -> AgentIntent | None:
    # 修改负责人同样需要任务编号，然后从句子里提取新的负责人名字。
    action_item_id = _extract_action_item_id(message)
    if action_item_id is None:
        return None

    conversational_owner = _extract_conversational_owner(message)
    if conversational_owner:
        return AgentIntent(
            name="update_task_owner",
            filters={
                "action_item_id": str(action_item_id),
                "owner_name": conversational_owner,
            },
        )

    patterns = (
        r"(?:\u8d1f\u8d23\u4eba)?\s*(?:\u6539\u6210|\u6539\u4e3a|\u6362\u6210|\u8f6c\u7ed9|\u4ea4\u7ed9|\u5206\u914d\u7ed9|\u8bbe\u7f6e\u4e3a)\s*(?P<owner>.{1,20}?)(?:\u8d1f\u8d23)?$",
        r"\u8d1f\u8d23\u4eba\s*(?:\u6539\u6210|\u6539\u4e3a|\u6362\u6210|\u8bbe\u7f6e\u4e3a)\s*(?P<owner>.{1,20})$",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            owner_name = _clean_task_field(match.group("owner"))
            if owner_name and not _is_filter_phrase(owner_name):
                return AgentIntent(
                    name="update_task_owner",
                    filters={
                        "action_item_id": str(action_item_id),
                        "owner_name": owner_name,
                    },
                )

    return None


def _extract_conversational_owner(message: str) -> str | None:
    # 支持更口语化的负责人表达，比如“3号任务，张三来跟”。
    patterns = (
        r"(?:\uff0c|,|\u3002|\s)(?P<owner>.{1,20}?)(?:\u6765\u8ddf|\u6765\u8d1f\u8d23|\u8d1f\u8d23\u8ddf\u8fdb)$",
        r"(?P<owner>.{1,20}?)(?:\u6765\u8ddf|\u6765\u8d1f\u8d23|\u8d1f\u8d23\u8ddf\u8fdb)$",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            owner_name = _clean_task_field(match.group("owner"))
            owner_name = _clean_conversational_owner_name(owner_name)
            if owner_name and not _is_filter_phrase(owner_name):
                return owner_name
    return None

def _clean_conversational_owner_name(owner_name: str) -> str:
    # 清理口语句子里多余的标点和编号，只保留负责人姓名。
    for separator in ("，", ",", "。", "；", ";"):
        if separator in owner_name:
            owner_name = owner_name.rsplit(separator, 1)[-1]
    owner_name = re.sub(r"^\s*\d+\s*(?:号)?\s*", "", owner_name)
    return _clean_task_field(owner_name)


def _strip_create_task_prefix(message: str) -> str:
    # 去掉“帮我新增任务：”这类前缀，留下真正的任务描述正文。
    normalized = message.strip()
    pattern = (
        r"^(?:帮我|请|麻烦)?(?:加一个任务|加个任务|创建任务|新增任务|新增行动项|"
        r"添加任务|安排一个任务)\s*[：:，,]?\s*"
    )
    return re.sub(pattern, "", normalized).strip()


def _parse_create_task_body(body: str) -> dict[str, str]:
    # 从新建任务正文里解析负责人、截止时间、任务标题。
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
    # 清理字段前后的标点、空格和“由/请/给”等连接词。
    token = value.strip(" ，。！？：:；;、")
    token = re.sub(r"^(由|让|请|给)\s*", "", token)
    return token.strip()


def _clean_task_title(value: str) -> str:
    # 清理任务标题里常见的动词前缀，让标题更干净。
    token = _clean_task_field(value)
    token = re.sub(r"^(完成|负责完成|去完成)\s*", "", token)
    return token.strip()


def _is_help_message(message: str) -> bool:
    # 判断用户是否在询问帮助或使用说明。
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
    # 识别“总结某个项目进度/风险”的请求。
    if not any(keyword in message for keyword in ("进度", "总结", "完成情况", "风险", "怎么样")):
        return None

    keyword = _extract_progress_keyword(message)
    if not keyword or _is_filter_phrase(keyword):
        return None

    return AgentIntent(name="summarize_project", filters={"keyword": keyword})


def _extract_progress_keyword(message: str) -> str | None:
    # 从“XX 项目进度怎么样”里提取 XX，作为项目关键词。
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
    # 识别“把某个任务改成完成/进行中/有风险/待处理”的请求。
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


def _detect_task_reference_clarification_intent(message: str) -> AgentIntent | None:
    # 用户想改任务但没给编号时，用这个意图提醒他补充任务编号。
    if _extract_action_item_id(message) is not None:
        return None
    if not _looks_like_task_mutation(message):
        return None

    return AgentIntent(
        name="clarify_task_reference",
        filters={
            "missing_fields": "任务编号",
            "raw_text": message,
        },
    )


def _looks_like_task_mutation(message: str) -> bool:
    # 粗略判断一句话是不是“修改任务”的语气。
    mutation_patterns = (
        r"改成",
        r"改为",
        r"修改",
        r"调整",
        r"换成",
        r"换给",
        r"转给",
        r"交给",
        r"负责人\s*(?:改|换|转|设)",
        r"延期",
        r"截止",
        r"完成",
        r"推进",
        r"进行中",
        r"有风险",
        r"标记",
        r"done",
        r"blocked",
    )
    task_reference_keywords = ("任务", "行动项", "事项", "这个", "那个", "#")
    return any(re.search(pattern, message, re.IGNORECASE) for pattern in mutation_patterns) and any(
        keyword in message for keyword in task_reference_keywords
    )





def _extract_action_item_id(message: str) -> int | None:
    # 支持从“3号任务”“#3”“任务 3”等表达里提取任务编号。
    patterns = (
        r"^\s*(\d+)\s*(?:\u53f7|\u9879)?",
        r"(?:\u628a|\u5c06)?\s*#\s*(\d+)",
        r"(?:\u628a|\u5c06)?\s*(\d+)\s*(?:\u53f7|\u9879)?\s*(?:\u4efb\u52a1|\u884c\u52a8\u9879|\u4e8b\u9879)",
        r"(?:\u4efb\u52a1|\u884c\u52a8\u9879|\u4e8b\u9879)\s*(?:#)?\s*(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return int(match.group(1))
    return None

def _extract_target_status(message: str) -> str | None:
    # 把中文口语状态映射成系统内部使用的状态值。
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
    # 从查询句里提取负责人，比如“张三负责的任务”。
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
    # 从查询句里提取项目或主题关键词。
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
    # 清理查询关键词前后的引号、括号、标点和常见前缀。
    token = value.strip(" ，。！？：:「」『』【】[]()（）")
    prefixes = ("帮我看看", "帮我查", "查询", "查看", "看一下", "看看", "请问", "目前", "当前")
    for prefix in prefixes:
        if token.startswith(prefix):
            token = token[len(prefix) :].strip()
    return token


def _build_query_message(items: list[ActionItemListItem], filters: dict[str, str]) -> str:
    # 根据查询结果和过滤条件，生成给用户看的查询回复。
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
    # 根据状态修改意图，生成确认类回复。
    status_label = {
        "pending": "待处理",
        "in_progress": "进行中",
        "completed": "已完成",
        "failed": "有风险",
    }.get(filters.get("status", ""), filters.get("status", ""))
    return f"准备将任务 {filters.get('action_item_id')} 更新为：{status_label}。"


def _build_progress_message(total_count: int, keyword: str) -> str:
    # 根据项目总结结果数量，生成给用户看的进度总结回复。
    if total_count == 0:
        return f"没有找到与 {keyword} 相关的任务。"
    return f"已生成 {keyword} 的项目进度总结。"


def _is_filter_phrase(value: str) -> bool:
    # 判断某个词是不是过滤条件本身，避免把“今天”“逾期”误当成项目名或人名。
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
