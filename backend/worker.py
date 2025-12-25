from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    # 兼容 `python backend/worker.py`（此时 sys.path[0] 是 backend/ 目录，不包含项目根）
    sys.path.insert(0, str(_ROOT))

from backend.app.core.config import settings
from backend.app.core.logging import configure_logging, get_logger
from backend.app.db.database import Database, DbConfig
from backend.app.jobs.scheduler import start_scheduler
from backend.app.repos.indicators_repo import IndicatorsRepo
from backend.app.repos.market_cap_repo import MarketCapRepo
from backend.app.services.market_cap import MarketCapService


logger = get_logger(__name__)


@asynccontextmanager
async def app_context():
    configure_logging(
        settings.log_level,
        to_file=settings.log_to_file,
        log_dir=settings.log_dir,
        retention_days=settings.log_retention_days,
    )
    db = Database(
        DbConfig(
            host=settings.pg_host,
            port=settings.pg_port,
            user=settings.pg_user,
            password=settings.pg_password,
            dbname=settings.pg_db,
            min_pool_size=settings.pg_pool_min,
            max_pool_size=settings.pg_pool_max,
            ssl=settings.pg_ssl or None,
            command_timeout=settings.pg_command_timeout,
        )
    )
    await db.connect()
    mc_repo = MarketCapRepo(db)
    await mc_repo.ensure_schema()
    _ = MarketCapService(repo=mc_repo)  # 确保导入可用（worker 里不直接用）
    ind_repo = IndicatorsRepo(db)
    await ind_repo.ensure_schema()
    try:
        yield db
    finally:
        await db.close()


async def main() -> None:
    async with app_context() as db:
        scheduler = start_scheduler(db)
        logger.info("Worker running. db=%s", settings.pg_db)
        # 永久运行
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            # 允许优雅退出（例如 Ctrl+C / SIGTERM）
            logger.info("Worker cancelled, shutting down.")
            return


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # 避免打印冗长堆栈
        pass

