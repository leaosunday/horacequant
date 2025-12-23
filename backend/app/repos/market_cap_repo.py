from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from backend.app.db.database import Database


@dataclass(frozen=True)
class MarketCapRow:
    code: str
    market_cap: Optional[float]
    as_of_date: date


class MarketCapRepo:
    def __init__(self, db: Database):
        self.db = db

    async def ensure_schema(self) -> None:
        # 保存“最新总市值”（不做历史回溯）；足够满足看盘/列表展示
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_market_cap_latest (
              code        CHAR(6) PRIMARY KEY REFERENCES stock_basic(code),
              market_cap  DOUBLE PRECISION,     -- 元
              as_of_date  DATE NOT NULL,
              updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_market_cap_as_of_date ON stock_market_cap_latest(as_of_date);")

    async def get_latest(self, code: str) -> Optional[MarketCapRow]:
        row = await self.db.fetchrow(
            """
            SELECT code, market_cap, as_of_date
            FROM stock_market_cap_latest
            WHERE code = $1;
            """,
            code,
        )
        if not row:
            return None
        return MarketCapRow(
            code=str(row["code"]).strip(),
            market_cap=row.get("market_cap"),
            as_of_date=row["as_of_date"],
        )

    async def upsert_latest(self, code: str, market_cap: Optional[float], as_of_date: date) -> None:
        await self.db.execute(
            """
            INSERT INTO stock_market_cap_latest(code, market_cap, as_of_date)
            VALUES($1, $2, $3)
            ON CONFLICT (code) DO UPDATE SET
              market_cap = EXCLUDED.market_cap,
              as_of_date = EXCLUDED.as_of_date,
              updated_at = NOW();
            """,
            code,
            market_cap,
            as_of_date,
        )

