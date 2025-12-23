from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

import pandas as pd

from backend.app.db.database import Database


class IndicatorsRepo:
    """
    指标缓存表（按 code+trade_date+adjust 存储）。
    API 优先读取指标表；缺失时现算并回填（越用越快）。
    """

    def __init__(self, db: Database):
        self.db = db

    async def ensure_schema(self) -> None:
        # 日线指标
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_daily_indicators (
              code             CHAR(6) NOT NULL REFERENCES stock_basic(code),
              trade_date       DATE NOT NULL,
              adjust           TEXT NOT NULL DEFAULT '',
              macd_dif         DOUBLE PRECISION,
              macd_dea         DOUBLE PRECISION,
              macd_hist        DOUBLE PRECISION,
              kdj_k            DOUBLE PRECISION,
              kdj_d            DOUBLE PRECISION,
              kdj_j            DOUBLE PRECISION,
              short_trend_line DOUBLE PRECISION,
              bull_bear_line   DOUBLE PRECISION,
              updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (code, trade_date, adjust)
            );
            """
        )
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_daily_ind_trade_date ON stock_daily_indicators(trade_date);")

        # 周线指标
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_weekly_indicators (
              code             CHAR(6) NOT NULL REFERENCES stock_basic(code),
              trade_date       DATE NOT NULL,
              adjust           TEXT NOT NULL DEFAULT '',
              macd_dif         DOUBLE PRECISION,
              macd_dea         DOUBLE PRECISION,
              macd_hist        DOUBLE PRECISION,
              kdj_k            DOUBLE PRECISION,
              kdj_d            DOUBLE PRECISION,
              kdj_j            DOUBLE PRECISION,
              short_trend_line DOUBLE PRECISION,
              bull_bear_line   DOUBLE PRECISION,
              updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (code, trade_date, adjust)
            );
            """
        )
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_weekly_ind_trade_date ON stock_weekly_indicators(trade_date);")

    async def load_daily_join(self, code: str, start: date, end: date, adjust: str) -> pd.DataFrame:
        rows = await self.db.fetch(
            """
            SELECT d.trade_date, d.open, d.high, d.low, d.close, d.volume, d.amount,
                   i.macd_dif, i.macd_dea, i.macd_hist, i.kdj_k, i.kdj_d, i.kdj_j,
                   i.short_trend_line, i.bull_bear_line
            FROM stock_daily d
            LEFT JOIN stock_daily_indicators i
              ON i.code = d.code AND i.trade_date = d.trade_date AND i.adjust = d.adjust
            WHERE d.code = $1 AND d.adjust = $2 AND d.trade_date BETWEEN $3 AND $4
            ORDER BY d.trade_date;
            """,
            code,
            adjust,
            start,
            end,
        )
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume", "amount"])

    async def load_weekly_join(self, code: str, start: date, end: date, adjust: str) -> pd.DataFrame:
        rows = await self.db.fetch(
            """
            SELECT w.trade_date, w.open, w.high, w.low, w.close, w.volume, w.amount,
                   i.macd_dif, i.macd_dea, i.macd_hist, i.kdj_k, i.kdj_d, i.kdj_j,
                   i.short_trend_line, i.bull_bear_line
            FROM stock_weekly w
            LEFT JOIN stock_weekly_indicators i
              ON i.code = w.code AND i.trade_date = w.trade_date AND i.adjust = w.adjust
            WHERE w.code = $1 AND w.adjust = $2 AND w.trade_date BETWEEN $3 AND $4
            ORDER BY w.trade_date;
            """,
            code,
            adjust,
            start,
            end,
        )
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume", "amount"])

    async def upsert_daily(self, code: str, adjust: str, df: pd.DataFrame) -> None:
        if df.empty:
            return
        rows = []
        for r in df.itertuples(index=False):
            rows.append(
                (
                    code,
                    r.trade_date,
                    adjust,
                    getattr(r, "macd_dif", None),
                    getattr(r, "macd_dea", None),
                    getattr(r, "macd_hist", None),
                    getattr(r, "kdj_k", None),
                    getattr(r, "kdj_d", None),
                    getattr(r, "kdj_j", None),
                    getattr(r, "short_trend_line", None),
                    getattr(r, "bull_bear_line", None),
                )
            )

        async with self.db.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO stock_daily_indicators(
                  code, trade_date, adjust,
                  macd_dif, macd_dea, macd_hist,
                  kdj_k, kdj_d, kdj_j,
                  short_trend_line, bull_bear_line
                )
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                ON CONFLICT (code, trade_date, adjust) DO UPDATE SET
                  macd_dif = EXCLUDED.macd_dif,
                  macd_dea = EXCLUDED.macd_dea,
                  macd_hist = EXCLUDED.macd_hist,
                  kdj_k = EXCLUDED.kdj_k,
                  kdj_d = EXCLUDED.kdj_d,
                  kdj_j = EXCLUDED.kdj_j,
                  short_trend_line = EXCLUDED.short_trend_line,
                  bull_bear_line = EXCLUDED.bull_bear_line,
                  updated_at = NOW();
                """,
                rows,
            )

    async def upsert_weekly(self, code: str, adjust: str, df: pd.DataFrame) -> None:
        if df.empty:
            return
        rows = []
        for r in df.itertuples(index=False):
            rows.append(
                (
                    code,
                    r.trade_date,
                    adjust,
                    getattr(r, "macd_dif", None),
                    getattr(r, "macd_dea", None),
                    getattr(r, "macd_hist", None),
                    getattr(r, "kdj_k", None),
                    getattr(r, "kdj_d", None),
                    getattr(r, "kdj_j", None),
                    getattr(r, "short_trend_line", None),
                    getattr(r, "bull_bear_line", None),
                )
            )

        async with self.db.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO stock_weekly_indicators(
                  code, trade_date, adjust,
                  macd_dif, macd_dea, macd_hist,
                  kdj_k, kdj_d, kdj_j,
                  short_trend_line, bull_bear_line
                )
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                ON CONFLICT (code, trade_date, adjust) DO UPDATE SET
                  macd_dif = EXCLUDED.macd_dif,
                  macd_dea = EXCLUDED.macd_dea,
                  macd_hist = EXCLUDED.macd_hist,
                  kdj_k = EXCLUDED.kdj_k,
                  kdj_d = EXCLUDED.kdj_d,
                  kdj_j = EXCLUDED.kdj_j,
                  short_trend_line = EXCLUDED.short_trend_line,
                  bull_bear_line = EXCLUDED.bull_bear_line,
                  updated_at = NOW();
                """,
                rows,
            )

