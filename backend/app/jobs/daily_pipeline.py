from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import akshare as ak
import pandas as pd

from backend.app.core.logging import get_logger
from backend.app.core.config import settings
from backend.app.db.database import Database


logger = get_logger(__name__)


def project_root() -> Path:
    here = Path(__file__).resolve()
    for p in [here.parent] + list(here.parents):
        if (p / ".git").exists():
            return p
    # fallback
    return Path.cwd()


def backend_root() -> Path:
    return project_root() / "backend"


async def run_cmd(args: list[str], cwd: Optional[Path] = None, env: Optional[dict[str, str]] = None) -> None:
    """
    运行外部脚本（用于复用现有 ops 脚本/选股逻辑），并记录 stdout/stderr。
    """
    cwd = cwd or project_root()
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_b, err_b = await proc.communicate()
    out = out_b.decode("utf-8", errors="replace")
    err = err_b.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        logger.error("Command failed rc=%s args=%s\nstdout=%s\nstderr=%s", proc.returncode, args, out[-4000:], err[-4000:])
        raise RuntimeError(f"Command failed: {args} rc={proc.returncode}")
    if out.strip():
        logger.info("Command ok args=%s stdout_tail=%s", args, out.strip()[-1000:])
    if err.strip():
        logger.warning("Command ok args=%s stderr_tail=%s", args, err.strip()[-1000:])


def is_trade_day_cn(d: date) -> bool:
    """
    使用新浪交易日历判断（需要联网）。
    """
    try:
        df = ak.tool_trade_date_hist_sina()
        if df is None or df.empty or "trade_date" not in df.columns:
            logger.warning("Trade calendar empty/unexpected, assume trade day. date=%s", d)
            return True
        # 部分环境下 trade_date 可能是 object/str，不能直接用 .dt
        dt = pd.to_datetime(df["trade_date"], errors="coerce")
        cal = set(dt.dropna().dt.date.tolist())
        return d in cal
    except Exception:
        # 日历拉取失败时，为避免“误跳过交易日”，默认按交易日处理（后续拉数为空也不会入库）
        logger.exception("Trade calendar fetch failed, assume trade day. date=%s", d)
        return True


async def try_acquire_advisory_lock(db: Database, lock_key: int) -> bool:
    v = await db.fetchval("SELECT pg_try_advisory_lock($1);", lock_key)
    return bool(v)


async def release_advisory_lock(db: Database, lock_key: int) -> None:
    await db.fetchval("SELECT pg_advisory_unlock($1);", lock_key)


async def run_daily_pipeline(db: Database, target_date: date, adjust: str = "qfq") -> None:
    """
    每日定时流水线（触发时间由 scheduler 配置决定）：
    1) 拉取并保存当日日K（全市场）
    2) 拉取并保存周K（更新当周；若不是新一周，删除前一天周K后再写入）
    3) 运行策略选股并保存（目前 b1）
    """
    # 用 advisory lock 防止重复执行（多实例/重复启动）
    # lock_key 只是“锁的名字”（数值形式），需要全局稳定且尽量避免与其它任务冲突。
    # 这里改为可配置：HQ_SCHEDULER_LOCK_KEY
    lock_key = int(getattr(settings, "scheduler_lock_key", 42424242))
    locked = await try_acquire_advisory_lock(db, lock_key)
    if not locked:
        logger.warning("Daily pipeline already running, skip. date=%s", target_date)
        return

    try:
        if not is_trade_day_cn(target_date):
            logger.info("Not a trade day, skip pipeline. date=%s", target_date)
            return

        root = project_root()
        broot = backend_root()
        py = sys.executable
        env = os.environ.copy()

        # 1) 日K：拉取最近两天（含当天），用于自动对齐可能遗漏的数据
        try:
            daily_script = broot / "ops" / "scripts" / "a_share_daily_to_postgres.py"
            start_daily = (target_date - timedelta(days=1)).strftime("%Y%m%d")
            await run_cmd(
                [
                    py,
                    str(daily_script),
                    "--start-date",
                    start_daily,
                    "--end-date",
                    target_date.strftime("%Y%m%d"),
                    "--adjust",
                    adjust,
                ],
                cwd=root,
                env=env,
            )
            logger.info("Stage 1/3: Daily K-line sync success (last 2 days). date=%s", target_date)
        except Exception as e:
            logger.error("Stage 1/3: Daily K-line sync failed. date=%s err=%s", target_date, e)

        # 2) 周K：只需要覆盖近 30 天以包含当周
        try:
            weekly_script = broot / "ops" / "scripts" / "a_share_weekly_to_postgres.py"
            start_weekly = (target_date - timedelta(days=30)).strftime("%Y%m%d")
            await run_cmd(
                [
                    py,
                    str(weekly_script),
                    "--start-date",
                    start_weekly,
                    "--end-date",
                    target_date.strftime("%Y%m%d"),
                    "--adjust",
                    adjust,
                ],
                cwd=root,
                env=env,
            )
            logger.info("Stage 2/3: Weekly K-line sync success. date=%s", target_date)
        except Exception as e:
            logger.error("Stage 2/3: Weekly K-line sync failed. date=%s err=%s", target_date, e)

        # 3) 选股：遍历策略列表
        picker_script = broot / "ops" / "scripts" / "stock_picker_tdx.py"
        strategies = list(getattr(settings, "strategies", ["b1"])) or ["b1"]
        for strat in strategies:
            try:
                rule_path = broot / "rules" / f"{strat}.tdx"
                if not rule_path.exists():
                    logger.warning("Strategy rule file not found, skip. strategy=%s path=%s", strat, rule_path)
                    continue
                await run_cmd(
                    [
                        py,
                        str(picker_script),
                        "--rule",
                        str(rule_path),
                        "--rule-name",
                        strat,
                        "--trade-date",
                        target_date.strftime("%Y-%m-%d"),
                    ],
                    cwd=root,
                    env=env,
                )
                logger.info("Stage 3/3: Stock picking success. strategy=%s date=%s", strat, target_date)
            except Exception as e:
                logger.error("Stage 3/3: Stock picking failed. strategy=%s date=%s err=%s", strat, target_date, e)

        logger.info("Daily pipeline completed. date=%s adjust=%s", target_date, adjust)
    finally:
        await release_advisory_lock(db, lock_key)

