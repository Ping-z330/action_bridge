import asyncio
import logging
from contextlib import suppress
from datetime import date, datetime

from app.core.config import (
    AUTO_FOLLOW_UP_ENABLED,
    AUTO_FOLLOW_UP_HOUR,
    AUTO_FOLLOW_UP_MINUTE,
    AUTO_FOLLOW_UP_POLL_SECONDS,
)
from app.db.session import SessionLocal
from app.services.follow_up_service import run_follow_up_scan

logger = logging.getLogger(__name__)


def should_run_auto_follow_up(now: datetime, last_run_date: date | None, hour: int, minute: int) -> bool:
    # 判断当前时间是否到了自动跟进时间，并且今天还没跑过。
    return now.hour == hour and now.minute == minute and last_run_date != now.date()


class AutoFollowUpScheduler:
    # 后台自动跟进调度器：按配置时间每天触发一次 run_follow_up_scan。
    def __init__(self) -> None:
        # _task 保存 asyncio 后台任务；_last_run_date 防止同一天重复执行。
        self._task: asyncio.Task | None = None
        self._last_run_date: date | None = None

    async def start(self) -> None:
        # 配置未开启或已经启动时，直接返回。
        if not AUTO_FOLLOW_UP_ENABLED or self._task is not None:
            return
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Auto follow-up scheduler started for %02d:%02d.",
            AUTO_FOLLOW_UP_HOUR,
            AUTO_FOLLOW_UP_MINUTE,
        )

    async def stop(self) -> None:
        # 应用关闭时取消后台任务。
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run_loop(self) -> None:
        # 常驻循环：定期检查是否到了自动分析时间。
        while True:
            now = datetime.now()
            if should_run_auto_follow_up(now, self._last_run_date, AUTO_FOLLOW_UP_HOUR, AUTO_FOLLOW_UP_MINUTE):
                db = SessionLocal()
                try:
                    # 1. 传统跟进提醒（未完成任务 → 飞书卡片）
                    result = run_follow_up_scan(db, run_date=now.date())

                    # 2. A2A 中央 Agent 分析：处理待处理 mRNA + 风险评估
                    from app.agent.central_agent import process_central_agent_messages, register_central_agent
                    from app.agent.tool_registry import DEFAULT_TOOL_REGISTRY
                    from app.agent.tool_adapters import ANALYZE_RISK
                    from app.services.meeting_service import list_action_items

                    # 注册并处理中央 Agent 消息
                    register_central_agent(1)  # project_id=1 for MVP
                    central_response = process_central_agent_messages(db, 1)

                    # 3. 每日风险分析
                    items = list_action_items(db)
                    risk_report = DEFAULT_TOOL_REGISTRY.execute(ANALYZE_RISK, db=db, project_id=1, items=items)

                    self._last_run_date = now.date()
                    logger.info(
                        "Auto follow-up: scanned=%s sent=%s | risk_score=%s overdue=%s",
                        result.scanned_meetings,
                        result.total_sent,
                        risk_report.risk_score,
                        risk_report.overdue_count,
                    )
                except Exception:
                    logger.exception("Auto follow-up run failed.")
                finally:
                    db.close()

            await asyncio.sleep(AUTO_FOLLOW_UP_POLL_SECONDS)
