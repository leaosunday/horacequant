from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    给每个请求附加 request_id，方便排障与追踪。
    """

    header_name = "X-Request-Id"

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get(self.header_name) or str(uuid.uuid4())
        request.state.request_id = rid

        start = time.time()
        resp: Response = await call_next(request)
        elapsed_ms = int((time.time() - start) * 1000)

        resp.headers[self.header_name] = rid
        resp.headers["X-Response-Time-Ms"] = str(elapsed_ms)
        return resp

