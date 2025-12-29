from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from typing import Any, AsyncGenerator, Optional

import pandas as pd
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.app.db.deps import DbDep, MarketCapDep, IndicatorsRepoDep
from backend.app.repos.picks_repo import PicksRepo
from backend.app.services.indicators import enrich_indicators
from backend.app.api.schemas import ApiResponse


router = APIRouter(prefix="/api/v1", tags=["picks"])


class KlinePoint(BaseModel):
    trade_date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    amount: float | None = None
    amplitude: float | None = None
    pct_change: float | None = None
    change_amount: float | None = None
    turnover_rate: float | None = None
    macd_dif: float | None = None
    macd_dea: float | None = None
    macd_hist: float | None = None
    kdj_k: float | None = None
    kdj_d: float | None = None
    kdj_j: float | None = None
    short_trend_line: float | None = None
    bull_bear_line: float | None = None


class PickBundleItem(BaseModel):
    code: str
    name: str
    exchange: str
    trade_date: str
    rule_name: str
    adjust: str
    market_cap: float | None = Field(default=None, description="总市值（元）")
    metrics: dict[str, Any] = Field(default_factory=dict)
    daily: list[KlinePoint] = Field(default_factory=list)
    weekly: list[KlinePoint] = Field(default_factory=list)


class PicksBundle(BaseModel):
    rule_name: str
    trade_date: str
    next_cursor: str
    items: list[PickBundleItem]


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
        "amplitude",
        "pct_change",
        "change_amount",
        "turnover_rate",
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


_INDICATOR_COLS = [
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "kdj_k",
    "kdj_d",
    "kdj_j",
    "short_trend_line",
    "bull_bear_line",
]


def _missing_indicator_trade_dates(df: pd.DataFrame) -> set:
    """
    更精确的缺失判断：逐行检查指标列。
    - indicators LEFT JOIN 结果中，如果某天指标行缺失或任一指标字段为 NULL，则该天需要回填
    返回：需要回填的 trade_date 集合
    """
    if df.empty or "trade_date" not in df.columns:
        return set()
    cols = [c for c in _INDICATOR_COLS if c in df.columns]
    if not cols:
        return set(df["trade_date"].tolist())
    mask = df[cols].isna().any(axis=1)
    return set(df.loc[mask, "trade_date"].tolist())


@router.get("/picks/{rule_name}/{trade_date}", response_model=ApiResponse[PicksBundle])
async def get_picks_bundle(
    rule_name: str,
    trade_date: str,
    request: Request,
    db: DbDep,
    market_cap: MarketCapDep,
    indicators_repo: IndicatorsRepoDep,
    adjust: str = Query(default="qfq", description='复权类型，需与入库一致（默认 qfq）'),
    window_days: int = Query(default=365, ge=30, le=3650, description="回看窗口天数（默认1年）"),
    limit: int = Query(default=10, ge=1, le=50, description="每页返回股票数量（建议 5~20）"),
    cursor: str = Query(default="", description="游标（上一页最后一个 code），用于分页"),
) -> Any:
    """
    返回：选股结果 + 每只股票的市值 + 1年日/周K + 指标（MACD/KDJ/短期趋势线/多空线）。

    性能策略：
    - cursor 分页（每页最多 50）
    - 市值查询：AkShare + 并发限流 + TTL 缓存
    - K线与指标：每只股票独立处理；如需流式返回请调用 /stream 接口
    """
    try:
        td = datetime.strptime(trade_date, "%Y%m%d").date()
    except ValueError:
        td = datetime.strptime(trade_date, "%Y-%m-%d").date()

    picks_repo = PicksRepo(db)

    try:
        picks = await picks_repo.list_picks(rule_name=rule_name, trade_date=td, limit=limit, cursor_code=cursor)
    except FileNotFoundError:
        # 该交易日还没跑出结果（或结果表未生成）：返回空列表，避免前端不停刷 404
        picks = []
    next_cursor = picks[-1].code if picks else ""

    start = td - timedelta(days=window_days)

    async def build_one(p):
        cap_task = asyncio.create_task(market_cap.get_market_cap(p.code))
        daily_task = asyncio.create_task(indicators_repo.load_daily_join(p.code, start, td, adjust))
        weekly_task = asyncio.create_task(indicators_repo.load_weekly_join(p.code, start, td, adjust))

        cap = await cap_task
        df_d0 = await daily_task
        # 精确缺失判断：只回填缺失的交易日（但计算仍需全窗口，保证递推指标正确）
        missing_dates_d = _missing_indicator_trade_dates(df_d0)
        if (not df_d0.empty) and missing_dates_d:
            base = df_d0[["trade_date", "open", "high", "low", "close", "volume", "amount"]].copy()
            df_d = enrich_indicators(base)
            await indicators_repo.upsert_daily(p.code, adjust, df_d[df_d["trade_date"].isin(missing_dates_d)].copy())
        else:
            df_d = df_d0
        try:
            df_w0 = await weekly_task
            missing_dates_w = _missing_indicator_trade_dates(df_w0)
            if (not df_w0.empty) and missing_dates_w:
                base = df_w0[["trade_date", "open", "high", "low", "close", "volume", "amount"]].copy()
                df_w = enrich_indicators(base)
                await indicators_repo.upsert_weekly(p.code, adjust, df_w[df_w["trade_date"].isin(missing_dates_w)].copy())
            else:
                df_w = df_w0
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

    # 非流式：顺序聚合，避免一次性并发过大
    items = []
    for p in picks:
        items.append(await build_one(p))

    bundle = PicksBundle(
        rule_name=rule_name,
        trade_date=td.strftime("%Y-%m-%d"),
        next_cursor=next_cursor,
        items=[PickBundleItem(**x) for x in items],
    )
    return ApiResponse[PicksBundle](request_id=getattr(request.state, "request_id", None), data=bundle)


@router.get("/picks/{rule_name}/{trade_date}/stream")
async def get_picks_bundle_stream(
    rule_name: str,
    trade_date: str,
    request: Request,
    db: DbDep,
    market_cap: MarketCapDep,
    indicators_repo: IndicatorsRepoDep,
    adjust: str = Query(default="qfq", description='复权类型，需与入库一致（默认 qfq ）'),
    window_days: int = Query(default=365, ge=30, le=3650, description="回看窗口天数（默认1年）"),
    limit: int = Query(default=10, ge=1, le=50, description="每页返回股票数量（建议 5~20）"),
    cursor: str = Query(default="", description="游标（上一页最后一个 code），用于分页"),
) -> StreamingResponse:
    """
    NDJSON 流式接口：
    - 第一条为 meta：包含 request_id / next_cursor 等
    - 后续多条为 item：每只股票一条（可边拉边画）
    """
    try:
        td = datetime.strptime(trade_date, "%Y%m%d").date()
    except ValueError:
        td = datetime.strptime(trade_date, "%Y-%m-%d").date()

    picks_repo = PicksRepo(db)
    try:
        picks = await picks_repo.list_picks(rule_name=rule_name, trade_date=td, limit=limit, cursor_code=cursor)
    except FileNotFoundError:
        picks = []
    next_cursor = picks[-1].code if picks else ""

    start = td - timedelta(days=window_days)

    async def build_one(p):
        cap_task = asyncio.create_task(market_cap.get_market_cap(p.code))
        daily_task = asyncio.create_task(indicators_repo.load_daily_join(p.code, start, td, adjust))
        weekly_task = asyncio.create_task(indicators_repo.load_weekly_join(p.code, start, td, adjust))

        cap = await cap_task
        df_d0 = await daily_task
        missing_dates_d = _missing_indicator_trade_dates(df_d0)
        if (not df_d0.empty) and missing_dates_d:
            base = df_d0[["trade_date", "open", "high", "low", "close", "volume", "amount"]].copy()
            df_d = enrich_indicators(base)
            await indicators_repo.upsert_daily(p.code, adjust, df_d[df_d["trade_date"].isin(missing_dates_d)].copy())
        else:
            df_d = df_d0
        try:
            df_w0 = await weekly_task
            missing_dates_w = _missing_indicator_trade_dates(df_w0)
            if (not df_w0.empty) and missing_dates_w:
                base = df_w0[["trade_date", "open", "high", "low", "close", "volume", "amount"]].copy()
                df_w = enrich_indicators(base)
                await indicators_repo.upsert_weekly(p.code, adjust, df_w[df_w["trade_date"].isin(missing_dates_w)].copy())
            else:
                df_w = df_w0
        except Exception:
            df_w = pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume", "amount"])

        return {
            "code": p.code,
            "name": p.name,
            "exchange": p.exchange,
            "trade_date": td.strftime("%Y-%m-%d"),
            "rule_name": rule_name,
            "adjust": adjust,
            "market_cap": cap,
            "metrics": p.metrics or {},
            "daily": _df_to_records(df_d),
            "weekly": _df_to_records(df_w),
        }

    async def gen() -> AsyncGenerator[bytes, None]:
        header = {
            "rule_name": rule_name,
            "trade_date": td.strftime("%Y-%m-%d"),
            "next_cursor": next_cursor,
            "request_id": getattr(request.state, "request_id", None),
        }
        yield (json.dumps({"type": "meta", "data": header}, ensure_ascii=False) + "\n").encode("utf-8")
        tasks = [asyncio.create_task(build_one(p)) for p in picks]
        for coro in asyncio.as_completed(tasks):
            item = await coro
            yield (json.dumps({"type": "item", "data": item}, ensure_ascii=False) + "\n").encode("utf-8")

    return StreamingResponse(gen(), media_type="application/x-ndjson")

