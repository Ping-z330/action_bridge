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
    return now.hour == hour and now.minute == minute and last_run_date != now.date()


class AutoFollowUpScheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._last_run_date: date | None = None

    async def start(self) -> None:
        if not AUTO_FOLLOW_UP_ENABLED or self._task is not None:
            return
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Auto follow-up scheduler started for %02d:%02d.",
            AUTO_FOLLOW_UP_HOUR,
            AUTO_FOLLOW_UP_MINUTE,
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run_loop(self) -> None:
        while True:
            now = datetime.now()
            if should_run_auto_follow_up(now, self._last_run_date, AUTO_FOLLOW_UP_HOUR, AUTO_FOLLOW_UP_MINUTE):
                db = SessionLocal()
                try:
                    result = run_follow_up_scan(db, run_date=now.date())
                    self._last_run_date = now.date()
                    logger.info(
                        "Auto follow-up finished: scanned=%s candidates=%s sent=%s",
                        result.scanned_meetings,
                        result.total_candidates,
                        result.total_sent,
                    )
                except Exception:
                    logger.exception("Auto follow-up run failed.")
                finally:
                    db.close()

            await asyncio.sleep(AUTO_FOLLOW_UP_POLL_SECONDS)
