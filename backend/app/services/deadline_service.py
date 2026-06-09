from datetime import UTC, date, datetime, timedelta
import re


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


def normalize_deadline(deadline: str, created_at: datetime | None = None) -> tuple[str, str]:
    # 把用户输入的自然语言截止时间拆成规范化日期和时间。
    # 返回值形如 ("2026-06-07", "18:00")，解析不出来的部分返回空字符串。
    normalized = deadline.strip()
    base_date = (created_at or datetime.now(UTC)).date()
    parsed_date = _parse_date(normalized, base_date)
    parsed_time = _parse_time(normalized)

    return (
        parsed_date.isoformat() if parsed_date else "",
        parsed_time,
    )


def build_deadline_text(deadline_date: str, deadline_time: str, fallback: str) -> str:
    # 把规范化日期/时间重新拼成展示文本；没有规范化结果时使用原始 fallback。
    if deadline_date and deadline_time:
        return f"{deadline_date} {deadline_time}"
    if deadline_date:
        return deadline_date
    return fallback.strip()


def _parse_date(value: str, base_date: date) -> date | None:
    # 从文本里解析日期，支持 ISO 日期、中文日期、今天/明天/周几等表达。
    iso_match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        return date(year, month, day)

    cn_date_match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", value)
    if cn_date_match:
        year, month, day = map(int, cn_date_match.groups())
        return date(year, month, day)

    if any(keyword in value for keyword in ("今天", "今日", "今晚", "本日")):
        return base_date
    if "明天" in value:
        return base_date + timedelta(days=1)
    if "后天" in value:
        return base_date + timedelta(days=2)
    if any(keyword in value for keyword in ("昨天", "前天")):
        return base_date - timedelta(days=1)

    next_week_match = re.search(r"下周([一二三四五六日天])", value)
    if next_week_match:
        return _resolve_weekday(base_date, WEEKDAY_MAP[next_week_match.group(1)], week_offset=1)

    this_week_match = re.search(r"本周([一二三四五六日天])", value)
    if this_week_match:
        return _resolve_weekday(base_date, WEEKDAY_MAP[this_week_match.group(1)], week_offset=0)

    plain_week_match = re.search(r"(?:周|星期)([一二三四五六日天])", value)
    if plain_week_match:
        return _resolve_weekday(base_date, WEEKDAY_MAP[plain_week_match.group(1)], week_offset=0)

    return None


def _parse_time(value: str) -> str:
    # 从文本里解析时间；如果只说了“下午/晚上”，给一个默认时间。
    time_match = re.search(r"(\d{1,2})[:：点](\d{1,2})?", value)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        if "下午" in value and hour < 12:
            hour += 12
        return f"{hour:02d}:{minute:02d}"

    if any(keyword in value for keyword in ("上午", "中午")):
        return "12:00"
    if any(keyword in value for keyword in ("下午", "下班前", "下班", "晚些时候")):
        return "18:00"
    if any(keyword in value for keyword in ("晚上", "今晚")):
        return "21:00"

    return "18:00" if value.strip() else ""


def _resolve_weekday(base_date: date, target_weekday: int, week_offset: int) -> date:
    # 根据基准日期、本周/下周偏移和目标星期，算出具体日期。
    start_of_week = base_date - timedelta(days=base_date.weekday())
    return start_of_week + timedelta(days=target_weekday + 7 * week_offset)
