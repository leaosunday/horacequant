from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.app.api.routes import router as api_router
from backend.app.core.config import settings
from backend.app.core.logging import configure_logging, get_logger
from backend.app.core.middleware import RequestIdMiddleware
from backend.app.db.database import Database, DbConfig
from backend.app.services.market_cap import MarketCapService
from backend.app.repos.market_cap_repo import MarketCapRepo
from backend.app.repos.indicators_repo import IndicatorsRepo
from backend.app.jobs.scheduler import start_scheduler


logger = get_logger(__name__)


def create_app() -> FastAPI:
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 初始化 DB 连接池
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
        app.state.db = db
        # 初始化并确保缓存表存在
        mc_repo = MarketCapRepo(db)
        await mc_repo.ensure_schema()
        app.state.market_cap = MarketCapService(repo=mc_repo)

        ind_repo = IndicatorsRepo(db)
        await ind_repo.ensure_schema()
        app.state.indicators_repo = ind_repo

        # 启动定时任务（生产环境建议单独跑 worker；这里先内置，便于开发/测试）
        app.state.scheduler = start_scheduler(db)

        try:
            yield
        finally:
            sch = getattr(app.state, "scheduler", None)
            if sch is not None:
                sch.shutdown(wait=False)
            await db.close()

    app = FastAPI(
        title=settings.app_name,
        docs_url="/docs" if settings.env != "prod" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.env != "prod" else None,
        lifespan=lifespan,
    )

    # 安全：Host 头限制（线上请显式配置 HQ_ALLOWED_HOSTS）
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # 避免把异常细节直接暴露给客户端；细节留在日志里
        rid = getattr(request.state, "request_id", None)
        logger.exception("Unhandled exception. request_id=%s path=%s", rid, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "internal_server_error", "request_id": rid},
        )

    app.include_router(api_router)
    return app


app = create_app()

