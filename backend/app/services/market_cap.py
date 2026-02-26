from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Optional

import anyio
import akshare as ak

from backend.app.core.logging import get_logger
from backend.app.repos.market_cap_repo import MarketCapRepo


logger = get_logger(__name__)


def _parse_market_cap(value: str) -> Optional[float]:
    """
    ak.stock_individual_info_em 返回的“总市值”通常是字符串，可能带单位：
      - 123.45亿 / 1.23万亿 / 1234567890
    统一转换为“元”（float）。
    """
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "none", "--"):
        return None

    m = re.match(r"^([0-9.]+)\s*(万亿|亿|万)?$", s)
    if not m:
        # 兜底：只取数字
        try:
            return float(re.sub(r"[^0-9.]", "", s))
        except Exception:
            return None

    num = float(m.group(1))
    unit = m.group(2)
    if unit == "万亿":
        return num * 1e12
    if unit == "亿":
        return num * 1e8
    if unit == "万":
        return num * 1e4
    return num


@dataclass
class MarketCapService:
    """
    通过 ak.stock_individual_info_em 获取总市值。
    - 内存缓存（TTL）
    - 并发限流（避免被数据源限流）
    - 运行在线程池中（避免阻塞 event loop）
    """

    repo: MarketCapRepo
    # 用于兜底逻辑获取交易所前缀
    db: Database
    # 内存缓存 TTL（秒）：同一进程内短时间重复请求更快
    ttl_seconds: int = 600
    # DB 缓存有效期（天）：总市值日级更新足够（可按需调整）
    db_max_age_days: int = 1
    max_concurrency: int = 8

    def __post_init__(self):
        self._cache: dict[str, tuple[float, Optional[float]]] = {}
        self._sem = anyio.Semaphore(self.max_concurrency)

    async def _get_exchange(self, code: str) -> Optional[str]:
        """获取股票的交易所前缀 (SH/SZ/BJ)"""
        try:
            row = await self.db.fetchrow("SELECT exchange FROM stock_basic WHERE code = $1", code)
            return str(row["exchange"]).strip().upper() if row else None
        except Exception:
            return None

    async def get_market_cap(self, code: str) -> Optional[float]:
        now = time.time()
        cached = self._cache.get(code)
        if cached and (now - cached[0] <= self.ttl_seconds):
            return cached[1]

        # 优先读 DB 缓存
        try:
            row = await self.repo.get_latest(code)
            if row is not None:
                age_days = (date.today() - row.as_of_date).days
                if age_days <= self.db_max_age_days:
                    self._cache[code] = (time.time(), row.market_cap)
                    return row.market_cap
        except Exception:
            logger.exception("Failed to read market cap cache from DB, code=%s", code)

        exchange = await self._get_exchange(code)

        async with self._sem:
            # double check
            cached = self._cache.get(code)
            if cached and (now - cached[0] <= self.ttl_seconds):
                return cached[1]

            def _fetch_sync() -> Optional[float]:
                # 1. 尝试 stock_individual_info_em
                try:
                    df = ak.stock_individual_info_em(symbol=code)
                    if df is not None and not df.empty:
                        # 常见列：item/value
                        for c1, c2 in (("item", "value"), ("项目", "值")):
                            if c1 in df.columns and c2 in df.columns:
                                hit = df[df[c1] == "总市值"]
                                if not hit.empty:
                                    val = _parse_market_cap(hit[c2].iloc[0])
                                    if val:
                                        return val
                except Exception as e:
                    logger.warning("stock_individual_info_em failed for %s: %s", code, e)

                # 2. 兜底：尝试 stock_zh_scale_comparison_em
                if exchange:
                    try:
                        symbol_with_prefix = f"{exchange}{code}"
                        df_scale = ak.stock_zh_scale_comparison_em(symbol=symbol_with_prefix)
                        if df_scale is not None and not df_scale.empty:
                            if "总市值" in df_scale.columns:
                                val = df_scale["总市值"].iloc[0]
                                if val and float(val) > 0:
                                    return float(val)
                    except Exception as e:
                        logger.warning("stock_zh_scale_comparison_em fallback failed for %s: %s", code, e)

                return None

            try:
                cap = await anyio.to_thread.run_sync(_fetch_sync)
            except Exception:
                logger.exception("Failed to fetch market cap for code=%s", code)
                cap = None

            # 写回 DB（即使 cap=None 也记一条，避免频繁打外部源）
            try:
                await self.repo.upsert_latest(code=code, market_cap=cap, as_of_date=date.today())
            except Exception:
                logger.exception("Failed to upsert market cap cache to DB, code=%s", code)

            self._cache[code] = (time.time(), cap)
            return cap

