from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.app.api.routes import router as api_router
from backend.app.api.schemas import ApiError
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
    configure_logging(
        settings.log_level,
        to_file=settings.log_to_file,
        log_dir=settings.log_dir,
        retention_days=settings.log_retention_days,
    )

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

        # 必须先执行 ind_repo.ensure_schema()，因为它负责创建 stock_basic 等基础表
        # 否则 mc_repo.ensure_schema() 会因为外键引用不存在而报错
        ind_repo = IndicatorsRepo(db)
        await ind_repo.ensure_schema()
        app.state.indicators_repo = ind_repo

        # 初始化并确保缓存表存在
        mc_repo = MarketCapRepo(db)
        await mc_repo.ensure_schema()
        app.state.market_cap = MarketCapService(repo=mc_repo)

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

    # 前端联调：CORS
    if getattr(settings, "cors_enabled", False):
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(getattr(settings, "cors_allow_origins", [])),
            allow_credentials=bool(getattr(settings, "cors_allow_credentials", False)),
            allow_methods=list(getattr(settings, "cors_allow_methods", ["*"])),
            allow_headers=list(getattr(settings, "cors_allow_headers", ["*"])),
        )

    # 安全：Host 头限制（线上请显式配置 HQ_ALLOWED_HOSTS）
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        rid = getattr(request.state, "request_id", None)
        # 统一错误格式；message 尽量稳定，不暴露内部细节
        msg = exc.detail if isinstance(exc.detail, str) else "http_error"
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiError(code=exc.status_code, message=msg, request_id=rid).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=422,
            content=ApiError(code=422, message="validation_error", request_id=rid, details=exc.errors()).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # 避免把异常细节直接暴露给客户端；细节留在日志里
        rid = getattr(request.state, "request_id", None)
        logger.exception("Unhandled exception. request_id=%s path=%s", rid, request.url.path)
        return JSONResponse(
            status_code=500,
            content=ApiError(code=500, message="internal_server_error", request_id=rid).model_dump(),
        )

    app.include_router(api_router)
    return app


app = create_app()

