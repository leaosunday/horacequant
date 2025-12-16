from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from typing import Any, AsyncGenerator, Optional

import pandas as pd
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.db.deps import DbDep, MarketCapDep
from backend.app.repos.kline_repo import KlineRepo
from backend.app.repos.picks_repo import PicksRepo
from backend.app.services.indicators import enrich_indicators


router = APIRouter(prefix="/api", tags=["picks"])


def _to_iso_date(d: Any) -> str:
    if isinstance(d, (date, datetime)):
        return d.strftime("%Y-%m-%d")
    return str(d)


def _df_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    # 只保留前端画图常用字段
    cols = [
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "macd_dif",
        "macd_dea",
        "macd_hist",
        "kdj_k",
        "kdj_d",
        "kdj_j",
        "short_trend_line",
        "bull_bear_line",
    ]
    keep = [c for c in cols if c in df.columns]
    out = df[keep].copy()
    out["trade_date"] = out["trade_date"].apply(_to_iso_date)
    # pandas/numpy 类型转 Python 原生
    return json.loads(out.to_json(orient="records"))


@router.get("/picks/{rule_name}/{trade_date}")
async def get_picks_bundle(
    rule_name: str,
    trade_date: str,
    db: DbDep,
    market_cap: MarketCapDep,
    adjust: str = Query(default="qfq", description='复权类型，需与入库一致（默认 qfq）'),
    window_days: int = Query(default=365, ge=30, le=3650, description="回看窗口天数（默认1年）"),
    limit: int = Query(default=10, ge=1, le=50, description="每页返回股票数量（建议 5~20）"),
    cursor: str = Query(default="", description="游标（上一页最后一个 code），用于分页"),
    stream: bool = Query(default=False, description="true 则返回 NDJSON 流，前端可边拉边画"),
) -> Any:
    """
    返回：选股结果 + 每只股票的市值 + 1年日/周K + 指标（MACD/KDJ/短期趋势线/多空线）。

    性能策略：
    - cursor 分页（每页最多 50）
    - 市值查询：AkShare + 并发限流 + TTL 缓存
    - K线与指标：每只股票独立处理，可配合 stream 逐条返回
    """
    try:
        td = datetime.strptime(trade_date, "%Y%m%d").date()
    except ValueError:
        td = datetime.strptime(trade_date, "%Y-%m-%d").date()

    picks_repo = PicksRepo(db)
    kline_repo = KlineRepo(db)

    try:
        picks = await picks_repo.list_picks(rule_name=rule_name, trade_date=td, limit=limit, cursor_code=cursor)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    next_cursor = picks[-1].code if picks else ""

    start = td - timedelta(days=window_days)

    async def build_one(p):
        cap_task = asyncio.create_task(market_cap.get_market_cap(p.code))
        daily_task = asyncio.create_task(kline_repo.load_daily(p.code, start, td, adjust))
        weekly_task = asyncio.create_task(kline_repo.load_weekly(p.code, start, td, adjust))

        cap = await cap_task
        df_d = enrich_indicators(await daily_task)
        try:
            df_w = enrich_indicators(await weekly_task)
        except Exception:
            # 周K可能还未入库；不中断整个接口
            df_w = pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume", "amount"])

        return {
            "code": p.code,
            "name": p.name,
            "exchange": p.exchange,
            "trade_date": td.strftime("%Y-%m-%d"),
            "rule_name": rule_name,
            "adjust": adjust,
            "market_cap": cap,  # 元
            "metrics": p.metrics or {},
            "daily": _df_to_records(df_d),
            "weekly": _df_to_records(df_w),
        }

    if stream:
        async def gen() -> AsyncGenerator[bytes, None]:
            header = {"rule_name": rule_name, "trade_date": td.strftime("%Y-%m-%d"), "next_cursor": next_cursor}
            yield (json.dumps({"type": "meta", "data": header}, ensure_ascii=False) + "\n").encode("utf-8")
            tasks = [asyncio.create_task(build_one(p)) for p in picks]
            for coro in asyncio.as_completed(tasks):
                item = await coro
                yield (json.dumps({"type": "item", "data": item}, ensure_ascii=False) + "\n").encode("utf-8")

        return StreamingResponse(gen(), media_type="application/x-ndjson")

    # 非流式：顺序聚合，避免一次性并发过大
    items = []
    for p in picks:
        items.append(await build_one(p))

    return {
        "rule_name": rule_name,
        "trade_date": td.strftime("%Y-%m-%d"),
        "next_cursor": next_cursor,
        "items": items,
    }

