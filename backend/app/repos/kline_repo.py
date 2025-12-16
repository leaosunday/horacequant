from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from backend.app.db.database import Database


class KlineRepo:
    def __init__(self, db: Database):
        self.db = db

    async def load_daily(self, code: str, start: date, end: date, adjust: str) -> pd.DataFrame:
        rows = await self.db.fetch(
            """
            SELECT trade_date, open, high, low, close, volume, amount
            FROM stock_daily
            WHERE code = $1 AND adjust = $2 AND trade_date BETWEEN $3 AND $4
            ORDER BY trade_date;
            """,
            code,
            adjust,
            start,
            end,
        )
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume", "amount"])

    async def load_weekly(self, code: str, start: date, end: date, adjust: str) -> pd.DataFrame:
        rows = await self.db.fetch(
            """
            SELECT trade_date, open, high, low, close, volume, amount
            FROM stock_weekly
            WHERE code = $1 AND adjust = $2 AND trade_date BETWEEN $3 AND $4
            ORDER BY trade_date;
            """,
            code,
            adjust,
            start,
            end,
        )
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume", "amount"])

