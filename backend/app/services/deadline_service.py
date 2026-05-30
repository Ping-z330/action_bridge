from datetime import UTC, date, datetime, timedelta
import re


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
    normalized = deadline.strip()
    base_date = (created_at or datetime.now(UTC)).date()
    parsed_date = _parse_date(normalized, base_date)
    parsed_time = _parse_time(normalized)

    return (
        parsed_date.isoformat() if parsed_date else "",
        parsed_time,
    )


def build_deadline_text(deadline_date: str, deadline_time: str, fallback: str) -> str:
    if deadline_date and deadline_time:
        return f"{deadline_date} {deadline_time}"
    if deadline_date:
        return deadline_date
    return fallback.strip()


def _parse_date(value: str, base_date: date) -> date | None:
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
    start_of_week = base_date - timedelta(days=base_date.weekday())
    return start_of_week + timedelta(days=target_weekday + 7 * week_offset)
