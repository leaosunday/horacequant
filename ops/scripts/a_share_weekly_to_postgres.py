"""
运维脚本：使用 AkShare 获取 A 股全市场个股近 2 年周 K 线数据，并保存到 PostgreSQL。

要求满足：
- 获取历史行情数据使用 ak.stock_zh_a_hist，示例：
  ak.stock_zh_a_hist(symbol="920992", period="weekly", start_date="20231222", end_date="20251230", adjust="qfq")

依赖：
  pip install -r requirements.txt

环境变量（可覆盖）：
  PG_HOST / PG_PORT / PG_USER / PG_PASSWORD / PG_DB (默认 horace_quant)

用法（示例）：
  python ops/scripts/a_share_weekly_to_postgres.py --adjust qfq

参数：
  --start-date YYYYMMDD   # 默认：今天往前两年
  --end-date   YYYYMMDD   # 默认：今天
  --adjust     ""|qfq|hfq # 默认：qfq
  --limit      N          # 仅处理前 N 只股票（调试用）
  --sleep      SECONDS    # 每只股票请求后休眠（默认 0.2s，防限流）
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import akshare as ak
import pandas as pd
import psycopg2
import psycopg2.extras


@dataclass(frozen=True)
class PgConfig:
    host: str
    port: int
    user: str
    password: str
    dbname: str


def load_pg_config() -> PgConfig:
    return PgConfig(
        host=os.getenv("PG_HOST", "127.0.0.1"),
        port=int(os.getenv("PG_PORT", "5432")),
        user=os.getenv("PG_USER", getpass.getuser()),
        password=os.getenv("PG_PASSWORD", ""),
        dbname=os.getenv("PG_DB", "horace_quant"),
    )


def pg_connect(dbname: str, cfg: PgConfig):
    return psycopg2.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        dbname=dbname,
    )


def ensure_tables(conn) -> None:
    """
    依赖已有 stock_basic；若没有则创建（与日K脚本一致的结构）。
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_basic (
              code        CHAR(6) PRIMARY KEY,
              name        TEXT NOT NULL,
              exchange    CHAR(2) NOT NULL, -- "SZ" / "SH" / "BJ"
              ak_symbol   TEXT NOT NULL,     -- "sz000001" / "sh600000" / "bj430047"
              updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_weekly (
              code          CHAR(6) NOT NULL REFERENCES stock_basic(code),
              trade_date    DATE NOT NULL,
              open          NUMERIC(18, 4),
              high          NUMERIC(18, 4),
              low           NUMERIC(18, 4),
              close         NUMERIC(18, 4),
              volume        BIGINT,
              amount        NUMERIC(20, 2),
              amplitude     NUMERIC(10, 4),
              pct_change    NUMERIC(10, 4),
              change_amount NUMERIC(18, 4),
              turnover_rate NUMERIC(10, 4),
              adjust        TEXT NOT NULL DEFAULT '',
              PRIMARY KEY (code, trade_date, adjust)
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_weekly_trade_date ON stock_weekly(trade_date);")
    conn.commit()


def infer_exchange(code: str) -> str:
    if code.startswith("6"):
        return "SH"
    if code.startswith(("0", "3", "90")):
        return "SZ"
    if code.startswith(("92", "8", "4")):
        return "BJ"
    return "NA"


def to_ak_symbol(code: str, exchange: str) -> str:
    ex = exchange.upper()
    if ex == "SH":
        return f"sh{code}"
    if ex == "SZ":
        return f"sz{code}"
    if ex == "BJ":
        return f"bj{code}"
    raise ValueError(f"无法生成 ak symbol: code={code}, exchange={exchange}")


def load_universe(conn) -> pd.DataFrame:
    """
    优先使用 stock_basic（稳定、无需外网）。
    如果 stock_basic 为空，则用 ak.stock_info_a_code_name 拉取并写回 stock_basic（名称+推断交易所）。
    """
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM stock_basic;")
        n = int(cur.fetchone()[0])

    if n > 0:
        with conn.cursor() as cur:
            cur.execute("SELECT code, name, exchange FROM stock_basic ORDER BY code;")
            rows = cur.fetchall()
        return pd.DataFrame(rows, columns=["code", "name", "exchange"])

    # 兜底：在线拉取（可能受网络限制）
    df = ak.stock_info_a_code_name().copy()
    df.columns = ["code", "name"]
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["exchange"] = df["code"].apply(infer_exchange)
    df = df[df["exchange"] != "NA"].copy()

    rows = []
    for r in df.itertuples(index=False):
        code = str(r.code).zfill(6)
        ex = str(r.exchange).upper()
        rows.append((code, str(r.name), ex, to_ak_symbol(code, ex)))

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO stock_basic(code, name, exchange, ak_symbol)
            VALUES %s
            ON CONFLICT (code) DO UPDATE SET
              name = EXCLUDED.name,
              exchange = EXCLUDED.exchange,
              ak_symbol = EXCLUDED.ak_symbol,
              updated_at = NOW();
            """,
            rows,
            page_size=2000,
        )
    conn.commit()

    return df[["code", "name", "exchange"]].reset_index(drop=True)


def _normalize_weekly_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    ak.stock_zh_a_hist(period='weekly') 常见返回列：
      日期/开盘/收盘/最高/最低/成交量/成交额/振幅/涨跌幅/涨跌额/换手率
    统一到：trade_date/open/high/low/close/volume/amount/amplitude/pct_change/change_amount/turnover_rate
    """
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
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
            ]
        )

    d = df.copy()

    mapping = {
        "日期": "trade_date",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
        "成交额": "amount",
        "振幅": "amplitude",
        "涨跌幅": "pct_change",
        "涨跌额": "change_amount",
        "换手率": "turnover_rate",
    }
    for k, v in mapping.items():
        if k in d.columns:
            d = d.rename(columns={k: v})

    keep = [c for c in mapping.values() if c in d.columns]
    d = d[keep].copy()

    d["trade_date"] = pd.to_datetime(d["trade_date"]).dt.date

    for c in ["open", "high", "low", "close", "amount", "amplitude", "pct_change", "change_amount", "turnover_rate"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    if "volume" in d.columns:
        d["volume"] = pd.to_numeric(d["volume"], errors="coerce").astype("Int64")

    return d


def fetch_weekly(symbol: str, start_date: str, end_date: str, adjust: str, retries: int = 3) -> pd.DataFrame:
    last_err: Optional[Exception] = None
    for i in range(retries):
        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="weekly",
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
            )
            return _normalize_weekly_df(df)
        except Exception as e:
            last_err = e
            time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"拉取失败 {symbol} weekly: {last_err}")


def upsert_stock_weekly(conn, code: str, weekly_df: pd.DataFrame, adjust: str) -> int:
    if weekly_df is None or weekly_df.empty:
        return 0

    rows = []
    for r in weekly_df.itertuples(index=False):
        rows.append(
            (
                code,
                getattr(r, "trade_date", None),
                getattr(r, "open", None),
                getattr(r, "high", None),
                getattr(r, "low", None),
                getattr(r, "close", None),
                int(getattr(r, "volume")) if getattr(r, "volume", None) is not None and pd.notna(getattr(r, "volume")) else None,
                getattr(r, "amount", None),
                getattr(r, "amplitude", None),
                getattr(r, "pct_change", None),
                getattr(r, "change_amount", None),
                getattr(r, "turnover_rate", None),
                adjust if adjust is not None else "",
            )
        )

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO stock_weekly(
              code, trade_date, open, high, low, close, volume, amount,
              amplitude, pct_change, change_amount, turnover_rate, adjust
            )
            VALUES %s
            ON CONFLICT (code, trade_date, adjust) DO UPDATE SET
              open = EXCLUDED.open,
              high = EXCLUDED.high,
              low = EXCLUDED.low,
              close = EXCLUDED.close,
              volume = EXCLUDED.volume,
              amount = EXCLUDED.amount,
              amplitude = EXCLUDED.amplitude,
              pct_change = EXCLUDED.pct_change,
              change_amount = EXCLUDED.change_amount,
              turnover_rate = EXCLUDED.turnover_rate;
            """,
            rows,
            page_size=2000,
        )
    conn.commit()
    return len(rows)


def yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--start-date", type=str, default=None, help="YYYYMMDD，默认：今天往前两年")
    p.add_argument("--end-date", type=str, default=None, help="YYYYMMDD，默认：今天")
    p.add_argument("--adjust", type=str, default="qfq", help='复权类型：""|qfq|hfq（默认 qfq）')
    p.add_argument("--limit", type=int, default=0, help="仅处理前 N 只股票（调试用，0 表示全部）")
    p.add_argument("--sleep", type=float, default=0.2, help="每只股票拉取后的休眠秒数")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_pg_config()

    today = date.today()
    default_start = today - timedelta(days=365 * 2)
    start_date = args.start_date or yyyymmdd(default_start)
    end_date = args.end_date or yyyymmdd(today)
    adjust = args.adjust if args.adjust is not None else "qfq"

    conn = pg_connect(cfg.dbname, cfg)
    try:
        ensure_tables(conn)
        universe = load_universe(conn)
        if args.limit and args.limit > 0:
            universe = universe.head(args.limit).copy()
        print(f"[INFO] 日期范围: {start_date} ~ {end_date}；adjust={repr(adjust)}；股票数={len(universe)}")

        ok, fail, total_rows = 0, 0, 0
        for idx, r in enumerate(universe.itertuples(index=False), start=1):
            code = str(r.code).zfill(6)
            name = str(r.name)
            try:
                df_w = fetch_weekly(symbol=code, start_date=start_date, end_date=end_date, adjust=adjust)
                n = upsert_stock_weekly(conn, code=code, weekly_df=df_w, adjust=adjust)
                total_rows += n
                ok += 1
                if idx % 100 == 0 or idx == len(universe):
                    print(f"[PROGRESS] {idx}/{len(universe)} OK={ok} FAIL={fail} 累计写入行数={total_rows}")
            except Exception as e:
                fail += 1
                print(f"[ERROR] {idx}/{len(universe)} {code} {name} weekly 拉取/写入失败: {e}", file=sys.stderr)

            if args.sleep and args.sleep > 0:
                time.sleep(args.sleep)

        print(f"[DONE] 完成：OK={ok} FAIL={fail} 写入行数={total_rows}")
        return 0 if fail == 0 else 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

