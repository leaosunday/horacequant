from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.app.core.logging import get_logger
from backend.app.db.database import Database
from backend.app.jobs.daily_pipeline import run_daily_16_pipeline


logger = get_logger(__name__)


def start_scheduler(db: Database) -> AsyncIOScheduler:
    tz = ZoneInfo("Asia/Shanghai")
    scheduler = AsyncIOScheduler(timezone=tz)

    async def job_runner():
        # 16:00 触发时按上海时区的“当天”运行
        now = datetime.now(tz).date()
        try:
            await run_daily_16_pipeline(db=db, target_date=now, adjust="qfq")
        except Exception:
            logger.exception("Daily 16:00 pipeline failed, date=%s", now)

    scheduler.add_job(
        job_runner,
        CronTrigger(hour=16, minute=0),
        id="daily_16_pipeline",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 30,
    )
    scheduler.start()
    logger.info("Scheduler started: daily_16_pipeline at 16:00 Asia/Shanghai")
    return scheduler

