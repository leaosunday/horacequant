from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.app.api.routes import router as api_router
from backend.app.core.config import settings
from backend.app.core.logging import configure_logging, get_logger
from backend.app.core.middleware import RequestIdMiddleware


logger = get_logger(__name__)


def create_app() -> FastAPI:
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        docs_url="/docs" if settings.env != "prod" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.env != "prod" else None,
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

