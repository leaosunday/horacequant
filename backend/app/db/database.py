from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import asyncpg

from backend.app.core.logging import get_logger


logger = get_logger(__name__)


_SAFE_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    dbname: str
    min_pool_size: int = 1
    max_pool_size: int = 10
    ssl: Optional[str] = None  # e.g. "require"
    command_timeout: float = 30.0

    def dsn(self) -> str:
        # asyncpg 支持 postgresql:// DSN
        pwd = self.password.replace("@", "%40") if self.password else ""
        auth = f"{self.user}:{pwd}@" if (self.user or pwd) else ""
        return f"postgresql://{auth}{self.host}:{self.port}/{self.dbname}"


class Database:
    """
    轻量级数据库访问层：
    - asyncpg 连接池
    - 统一的 fetch/execute API
    - 只允许参数化查询（防注入）
    """

    def __init__(self, cfg: DbConfig):
        self.cfg = cfg
        self._pool: Optional[asyncpg.pool.Pool] = None

    @property
    def pool(self) -> asyncpg.pool.Pool:
        if self._pool is None:
            raise RuntimeError("Database pool is not initialized (call connect() first).")
        return self._pool

    async def connect(self) -> None:
        if self._pool is not None:
            return
        logger.info(
            "Creating Postgres pool host=%s port=%s db=%s min=%s max=%s",
            self.cfg.host,
            self.cfg.port,
            self.cfg.dbname,
            self.cfg.min_pool_size,
            self.cfg.max_pool_size,
        )
        ssl_ctx = self.cfg.ssl if self.cfg.ssl else None
        self._pool = await asyncpg.create_pool(
            dsn=self.cfg.dsn(),
            min_size=self.cfg.min_pool_size,
            max_size=self.cfg.max_pool_size,
            command_timeout=self.cfg.command_timeout,
            ssl=ssl_ctx,
        )

    async def close(self) -> None:
        if self._pool is None:
            return
        logger.info("Closing Postgres pool db=%s", self.cfg.dbname)
        await self._pool.close()
        self._pool = None

    async def healthcheck(self) -> bool:
        try:
            v = await self.fetchval("SELECT 1;")
            return v == 1
        except Exception:
            logger.exception("DB healthcheck failed")
            return False

    async def fetchval(self, query: str, *args: Any) -> Any:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> Optional[Mapping[str, Any]]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row is not None else None

    async def fetch(self, query: str, *args: Any) -> list[Mapping[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(r) for r in rows]

    async def execute(self, query: str, *args: Any) -> str:
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    # ---- helpers for safe dynamic identifiers (e.g. partition tables) ----
    @staticmethod
    def quote_ident(name: str) -> str:
        """
        仅允许 [a-zA-Z0-9_] 的标识符，防止 SQL 注入。
        返回双引号包裹的标识符，避免大小写/关键字问题。
        """
        if not _SAFE_IDENT_RE.fullmatch(name):
            raise ValueError(f"Unsafe identifier: {name!r}")
        return f'"{name}"'

