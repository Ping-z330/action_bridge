from datetime import UTC, date, datetime, timedelta
import re


# 到期状态对应的中文展示文案。
DUE_STATUS_LABELS = {
    "due_today": "今日到期",
    "overdue": "已逾期",
    "upcoming": "未到期",
    "unknown": "待确认",
    "completed": "已完成",
}

# 中文星期到 Python weekday 数字的映射：周一是 0，周日是 6。
WEEKDAY_MAP = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}

# 这些值表示截止时间未知，不参与今天到期/逾期判断。
UNKNOWN_DEADLINES = {"", "pending confirmation", "tbd", "待确认", "待定", "暂无", "无"}


def get_due_status(deadline: str, created_at: datetime | None = None, today: date | None = None) -> str:
    # 根据原始 deadline 文本判断到期状态。
    # 适合处理“今天”“明天”“下周五”“2026-06-07”等自然语言日期。
    normalized = deadline.strip()
    effective_today = today or datetime.now(UTC).date()

    if normalized.lower() in UNKNOWN_DEADLINES:
        return "unknown"

    lowered = normalized.lower()
    if "已逾期" in normalized or "overdue" in lowered:
        return "overdue"

    parsed_date = _parse_deadline_date(normalized, created_at, effective_today)
    if not parsed_date:
        return "unknown"
    # 解析出具体日期后，再和今天比较。
    if parsed_date < effective_today:
        return "overdue"
    if parsed_date == effective_today:
        return "due_today"
    return "upcoming"


def get_due_status_from_date(deadline_date: str, status: str, today: date | None = None) -> str:
    # 根据已经规范化的 deadline_date 判断到期状态。
    # 如果任务已完成，直接返回 completed，不再判断是否逾期。
    if status == "completed":
        return "completed"
    if not deadline_date:
        return "unknown"

    effective_today = today or datetime.now(UTC).date()
    try:
        parsed_date = date.fromisoformat(deadline_date)
    except ValueError:
        return "unknown"

    if parsed_date < effective_today:
        return "overdue"
    if parsed_date == effective_today:
        return "due_today"
    return "upcoming"


def get_due_status_label(due_status: str) -> str:
    # 把系统内部状态转成前端可展示的中文文案。
    return DUE_STATUS_LABELS.get(due_status, due_status)


def _parse_deadline_date(deadline: str, created_at: datetime | None, today: date) -> date | None:
    # 从原始截止时间文本里解析出具体日期。
    iso_match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", deadline)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        return date(year, month, day)

    cn_date_match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", deadline)
    if cn_date_match:
        year, month, day = map(int, cn_date_match.groups())
        return date(year, month, day)

    if any(keyword in deadline for keyword in ("今天", "今日", "今晚", "本日")):
        return today
    if any(keyword in deadline for keyword in ("昨天", "前天", "上周")):
        return today - timedelta(days=1)
    if "明天" in deadline:
        return today + timedelta(days=1)
    if "后天" in deadline:
        return today + timedelta(days=2)

    base_date = created_at.date() if created_at else today
    # “本周/下周/周几”的解析要基于创建时间或今天来推算。
    next_week_match = re.search(r"下周([一二三四五六日天])", deadline)
    if next_week_match:
        return _resolve_weekday(base_date, WEEKDAY_MAP[next_week_match.group(1)], week_offset=1)

    this_week_match = re.search(r"本周([一二三四五六日天])", deadline)
    if this_week_match:
        return _resolve_weekday(base_date, WEEKDAY_MAP[this_week_match.group(1)], week_offset=0)

    plain_week_match = re.search(r"(?:周|星期)([一二三四五六日天])", deadline)
    if plain_week_match:
        return _resolve_weekday(base_date, WEEKDAY_MAP[plain_week_match.group(1)], week_offset=0)

    return None


def _resolve_weekday(base_date: date, target_weekday: int, week_offset: int) -> date:
    # 根据基准日期、本周/下周偏移和目标星期，算出具体日期。
    start_of_week = base_date - timedelta(days=base_date.weekday())
    return start_of_week + timedelta(days=target_weekday + 7 * week_offset)
