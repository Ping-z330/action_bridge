from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
import re

from sqlalchemy.orm import Session, selectinload

from app.models.action_item import ActionItem
from app.models.follow_up_log import FollowUpLog
from app.models.meeting import Meeting
from app.schemas.follow_up import FollowUpRunItem, FollowUpRunResponse
from app.schemas.meeting import MeetingResponse
from app.services.feishu_service import FeishuDeliveryError, send_follow_up_summary


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


@dataclass
class FollowUpCandidate:
    # 一条待提醒候选项：记录行动项 ID 和提醒类型。
    action_item_id: int
    reminder_type: str


def run_follow_up_scan(db: Session, run_date: date | None = None) -> FollowUpRunResponse:
    # 扫描所有会议的行动项，找出今天到期/已逾期且还没提醒过的任务，并发送飞书提醒。
    effective_date = run_date or datetime.now(UTC).date()
    meetings = (
        db.query(Meeting)
        .options(selectinload(Meeting.action_items))
        .order_by(Meeting.created_at.desc())
        .all()
    )

    grouped_candidates: dict[int, list[FollowUpCandidate]] = {}
    total_candidates = 0

    for meeting in meetings:
        # 每个会议单独收集候选项，后续按会议发送一张跟进卡片。
        candidates = _collect_candidates(db, meeting.action_items, effective_date)
        if candidates:
            grouped_candidates[meeting.id] = candidates
            total_candidates += len(candidates)

    results: list[FollowUpRunItem] = []
    total_sent = 0

    for meeting in meetings:
        candidates = grouped_candidates.get(meeting.id, [])
        if not candidates:
            continue

        filtered_ids = {candidate.action_item_id for candidate in candidates}
        filtered_items = [item for item in meeting.action_items if item.id in filtered_ids]
        reminder_types = sorted({candidate.reminder_type for candidate in candidates})

        # 飞书卡片发送函数需要 MeetingResponse 结构，这里把 ORM 对象转换成响应对象。
        meeting_payload = MeetingResponse(
            id=meeting.id,
            title=meeting.title,
            raw_transcript=meeting.raw_transcript,
            summary=meeting.summary,
            decisions=[],
            created_at=meeting.created_at,
            action_items=filtered_items,
        )

        try:
            message = send_follow_up_summary(meeting_payload)
            for candidate in candidates:
                # 发送成功后记录日志，避免同一天重复提醒同一个任务。
                db.add(
                    FollowUpLog(
                        meeting_id=meeting.id,
                        action_item_id=candidate.action_item_id,
                        reminder_type=candidate.reminder_type,
                        status="sent",
                    )
                )
            status = "sent"
            total_sent += len(candidates)
        except FeishuDeliveryError as exc:
            message = str(exc)
            for candidate in candidates:
                # 发送失败也记录日志，方便后续排查。
                db.add(
                    FollowUpLog(
                        meeting_id=meeting.id,
                        action_item_id=candidate.action_item_id,
                        reminder_type=candidate.reminder_type,
                        status="failed",
                    )
                )
            status = "failed"

        results.append(
            FollowUpRunItem(
                meeting_id=meeting.id,
                meeting_title=meeting.title,
                reminder_count=len(candidates),
                reminder_types=reminder_types,
                status=status,
                message=message,
            )
        )

    db.commit()

    return FollowUpRunResponse(
        scanned_meetings=len(meetings),
        total_candidates=total_candidates,
        total_sent=total_sent,
        results=results,
    )


def record_follow_up_reply(
    db: Session,
    meeting_id: int,
    action_item_id: int,
    status: str,
) -> FollowUpLog:
    # 用户收到提醒后回复状态时，记录这次回复。
    log = FollowUpLog(
        meeting_id=meeting_id,
        action_item_id=action_item_id,
        reminder_type="reply_status_update",
        status=status,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def _collect_candidates(db: Session, action_items: list[ActionItem], run_date: date) -> list[FollowUpCandidate]:
    # 从一个会议的行动项中筛出需要提醒的候选项。
    candidates: list[FollowUpCandidate] = []

    for item in action_items:
        # 只提醒仍需推进的任务，已完成或失败之外的状态不重复提醒。
        if item.status not in {"pending", "in_progress"}:
            continue

        reminder_type = _classify_deadline(item.deadline, run_date)
        if not reminder_type:
            continue
        if _has_sent_reminder_today(db, item.id, reminder_type, run_date):
            continue

        candidates.append(FollowUpCandidate(action_item_id=item.id, reminder_type=reminder_type))

    return candidates


def _has_sent_reminder_today(db: Session, action_item_id: int, reminder_type: str, run_date: date) -> bool:
    # 判断某个任务今天是否已经发送过同类型提醒。
    start_of_day = datetime.combine(run_date, time.min, tzinfo=UTC)
    end_of_day = start_of_day + timedelta(days=1)

    existing = (
        db.query(FollowUpLog)
        .filter(FollowUpLog.action_item_id == action_item_id)
        .filter(FollowUpLog.reminder_type == reminder_type)
        .filter(FollowUpLog.status == "sent")
        .filter(FollowUpLog.sent_at >= start_of_day)
        .filter(FollowUpLog.sent_at < end_of_day)
        .first()
    )
    return existing is not None


def _classify_deadline(deadline: str, today: date) -> str | None:
    # 把截止时间文本分类成 due_today / overdue；其他情况返回 None。
    normalized = deadline.strip()
    if not normalized:
        return None

    lowered = normalized.lower()
    if lowered in {"pending confirmation", "tbd", "待确认"}:
        return None

    if "已逾期" in normalized or "overdue" in lowered:
        return "overdue"

    if any(keyword in normalized for keyword in ("今天", "今日", "今晚", "本日")):
        return "due_today"

    if any(keyword in normalized for keyword in ("昨天", "前天", "上周")):
        return "overdue"

    parsed_date = _parse_deadline_date(normalized) or _parse_relative_deadline(normalized, today)
    if not parsed_date:
        return None
    if parsed_date < today:
        return "overdue"
    if parsed_date == today:
        return "due_today"
    return None


def _parse_deadline_date(deadline: str) -> date | None:
    # 解析完整日期文本，比如 2026-06-07 或 2026年6月7日。
    iso_match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", deadline)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        return date(year, month, day)

    cn_match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日", deadline)
    if cn_match:
        year, month, day = map(int, cn_match.groups())
        return date(year, month, day)

    return None


def _parse_relative_deadline(deadline: str, today: date) -> date | None:
    # 解析相对日期，比如明天、后天、本周五、下周一。
    normalized = deadline.strip()

    if "明天" in normalized:
        return today + timedelta(days=1)
    if "后天" in normalized:
        return today + timedelta(days=2)

    next_week_match = re.search(r"下周([一二三四五六日天])", normalized)
    if next_week_match:
        return _resolve_weekday(today, WEEKDAY_MAP[next_week_match.group(1)], week_offset=1)

    this_week_match = re.search(r"本周([一二三四五六日天])", normalized)
    if this_week_match:
        return _resolve_weekday(today, WEEKDAY_MAP[this_week_match.group(1)], week_offset=0)

    plain_week_match = re.search(r"(?:周|星期)([一二三四五六日天])", normalized)
    if plain_week_match:
        return _resolve_weekday(today, WEEKDAY_MAP[plain_week_match.group(1)], week_offset=0)

    return None


def _resolve_weekday(today: date, target_weekday: int, week_offset: int) -> date:
    # 根据今天、本周/下周偏移和目标星期，算出具体日期。
    start_of_week = today - timedelta(days=today.weekday())
    return start_of_week + timedelta(days=target_weekday + 7 * week_offset)
