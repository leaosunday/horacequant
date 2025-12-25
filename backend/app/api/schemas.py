from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """
    稳定的 API 响应包裹：
    - code=0 表示成功；非 0 表示失败（通常与 HTTP status_code 一致）
    - request_id 由中间件注入，便于前后端联调与排障
    """

    code: int = Field(default=0)
    message: str = Field(default="ok")
    request_id: Optional[str] = Field(default=None)
    data: T


class ApiError(BaseModel):
    code: int
    message: str
    request_id: Optional[str] = None
    details: Optional[Any] = None

