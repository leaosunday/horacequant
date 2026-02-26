from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional
import json

import asyncpg

from backend.app.db.database import Database


@dataclass(frozen=True)
class PickRow:
    code: str
    name: str
    exchange: str
    metrics: Optional[dict[str, Any]]


class PicksRepo:
    def __init__(self, db: Database, table_prefix: str = "stock_pick_results_"):
        self.db = db
        self.table_prefix = table_prefix

    def table_name_for_date(self, trade_date: date) -> str:
        return f"{self.table_prefix}{trade_date.strftime('%Y%m%d')}"

    async def list_picks(
        self,
        rule_name: str,
        trade_date: date,
        limit: int,
        cursor_code: str = "",
    ) -> list[PickRow]:
        table = self.table_name_for_date(trade_date)
        # 明确 schema，避免 search_path 导致的 “relation does not exist”
        t = f'public.{self.db.quote_ident(table)}'

        # cursor pagination by code
        query = f"""
        SELECT code, name, exchange, metrics
        FROM {t}
        WHERE rule_name = $1
          AND ($2 = '' OR code > $2)
        ORDER BY code
        LIMIT $3
        """
        try:
            rows = await self.db.fetch(query, rule_name, cursor_code, limit)
        except asyncpg.UndefinedTableError as e:
            raise FileNotFoundError(f"Pick result table not found: {table}") from e
        out: list[PickRow] = []
        for r in rows:
            metrics = r.get("metrics")
            # asyncpg jsonb 可能返回 dict，也可能返回 str
            if isinstance(metrics, str):
                try:
                    metrics = json.loads(metrics)
                except Exception:
                    metrics = None
            out.append(
                PickRow(
                    code=str(r["code"]).strip(),
                    name=str(r["name"]),
                    exchange=str(r["exchange"]).strip(),
                    metrics=metrics,
                )
            )
        return out

    async def count_picks(self, rule_name: str, trade_date: date) -> int:
        table = self.table_name_for_date(trade_date)
        t = f'public.{self.db.quote_ident(table)}'
        query = f"SELECT count(*) FROM {t} WHERE rule_name = $1"
        try:
            val = await self.db.fetchval(query, rule_name)
            return int(val) if val is not None else 0
        except asyncpg.UndefinedTableError:
            return 0
        except Exception:
            return 0

