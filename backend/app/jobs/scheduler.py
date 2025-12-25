from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.db.database import Database
from backend.app.jobs.daily_pipeline import run_daily_pipeline


logger = get_logger(__name__)


def start_scheduler(db: Database) -> AsyncIOScheduler:
    if not getattr(settings, "scheduler_enabled", True):
        tz = ZoneInfo(getattr(settings, "scheduler_timezone", "Asia/Shanghai"))
        scheduler = AsyncIOScheduler(timezone=tz)
        logger.info("Scheduler disabled by config")
        return scheduler

    tz = ZoneInfo(getattr(settings, "scheduler_timezone", "Asia/Shanghai"))
    scheduler = AsyncIOScheduler(timezone=tz)

    async def job_runner():
        # 触发时按配置时区的“当天”运行
        now = datetime.now(tz).date()
        try:
            await run_daily_pipeline(db=db, target_date=now, adjust="qfq")
        except Exception:
            logger.exception("Daily pipeline failed, date=%s", now)

    job = scheduler.add_job(
        job_runner,
        CronTrigger(hour=getattr(settings, "scheduler_hour", 16), minute=getattr(settings, "scheduler_minute", 0)),
        id="daily_pipeline",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=getattr(settings, "scheduler_misfire_grace_seconds", 60 * 30),
    )
    scheduler.start()
    logger.info(
        "Scheduler started: daily_pipeline at %02d:%02d %s next_run=%s",
        getattr(settings, "scheduler_hour", 16),
        getattr(settings, "scheduler_minute", 0),
        getattr(settings, "scheduler_timezone", "Asia/Shanghai"),
        job.next_run_time,
    )

    # 可选：启动即跑一次，用于验证/补数据
    if getattr(settings, "scheduler_run_on_start", False):
        scheduler.add_job(
            job_runner,
            DateTrigger(run_date=datetime.now(tz)),
            id="daily_pipeline_run_on_start",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info("Scheduler run-on-start enabled: will run daily pipeline immediately")
    return scheduler

