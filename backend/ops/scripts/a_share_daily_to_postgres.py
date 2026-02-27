"""
运维脚本：使用 AkShare 获取 A 股全市场个股近 2 年日 K 线数据，并保存到 PostgreSQL。

要求满足：
1) 获取历史行情数据使用 ak.stock_zh_a_hist（period="daily"）
2) 个股基础信息需保存：6 位代码、名称、交易所（"SZ"/"SH"/"BJ"）

用法（示例）：
  pip install -r backend/requirements.txt
  export PG_HOST=127.0.0.1
  export PG_PORT=5432
  export PG_USER=postgres
  export PG_PASSWORD=your_password
  export PG_DB=horace_quant
  python backend/ops/scripts/a_share_daily_to_postgres.py

可选参数：
  --start-date YYYYMMDD   # 覆盖默认“近2年”的起始日期
  --end-date   YYYYMMDD   # 覆盖默认结束日期（默认今天）
  --adjust     qfq|hfq|""  # 复权类型（默认不复权）
  --limit      N          # 仅处理前 N 只股票（调试用）
  --sleep      SECONDS    # 每只股票请求后的休眠（默认 0s）
  --ts-rpm   N          # Tushare 每分钟调用次数限制（默认 50，设为 0 禁用限流）
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import threading
import time
import warnings
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import akshare as ak
import pandas as pd
import psycopg2
import psycopg2.extras
import tushare as ts

warnings.filterwarnings(
    'ignore',
    message=r"Series\.fillna with 'method' is deprecated and will raise in a future version\. Use obj\.ffill\(\) or obj\.bfill\(\) instead",
    category=FutureWarning,
    module='pandas'
)


class TushareRateLimiter:
    """
    令牌桶限流器，用于控制 Tushare pro_bar 调用频率。
    Tushare 免费版限制：50 次/分钟 ≈ 0.83 秒/次
    设置略保守：每 1.2 秒 1 次，留出缓冲空间。
    """

    def __init__(self, calls_per_minute: int = 50, burst: int = 10):
        self.min_interval = 60.0 / calls_per_minute  # 最小间隔（秒）
        self.burst = burst  # 突发调用次数（令牌桶容量）
        self.tokens = float(burst)  # 当前令牌数
        self.last_update = time.time()
        self._lock = threading.Lock()

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        获取一个令牌，若令牌不足则阻塞等待。
        timeout: 最长等待时间（秒），None 表示无限等待
        返回：True 表示获取成功，False 表示超时
        """
        deadline = None if timeout is None else time.time() + timeout

        while True:
            with self._lock:
                now = time.time()
                # 补充令牌
                elapsed = now - self.last_update
                self.tokens = min(self.burst, self.tokens + elapsed / self.min_interval)
                self.last_update = now

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return True

            # 令牌不足，等待
            if deadline is not None and time.time() >= deadline:
                return False

            # 计算需要等待多久才能有 1 个令牌
            with self._lock:
                tokens_needed = 1.0 - self.tokens
                wait_time = tokens_needed * self.min_interval

            sleep_time = min(wait_time, 0.5) if wait_time > 0 else 0.01
            time.sleep(sleep_time)

    def try_acquire(self) -> bool:
        """尝试立即获取一个令牌，不等待"""
        with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed / self.min_interval)
            self.last_update = now

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


# 全局限流器实例
_tushare_limiter: Optional[TushareRateLimiter] = None


def get_tushare_limiter() -> TushareRateLimiter:
    global _tushare_limiter
    if _tushare_limiter is None:
        _tushare_limiter = TushareRateLimiter(calls_per_minute=50, burst=10)
    return _tushare_limiter


@dataclass(frozen=True)
class PgConfig:
    host: str
    port: int
    user: str
    password: str
    dbname: str


def _env(name: str, default: Optional[str] = None) -> str:
    v = os.getenv(name, default)
    if v is None or v == "":
        raise RuntimeError(f"缺少环境变量 {name}")
    return v


def load_pg_config() -> PgConfig:
    return PgConfig(
        host=_env("HQ_PG_HOST", "127.0.0.1"),
        port=int(_env("HQ_PG_PORT", "5432")),
        # macOS/Homebrew 常见默认角色是当前系统用户名；因此默认用 getpass.getuser()
        user=_env("HQ_PG_USER", getpass.getuser()),
        # 密码允许为空（例如本地 trust / peer 认证，或你自己用 .pgpass 管理）
        password=os.getenv("HQ_PG_PASSWORD", ""),
        dbname=_env("HQ_PG_DB", "horace_quant"),
    )


def pg_connect(dbname: str, cfg: PgConfig):
    return psycopg2.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        dbname=dbname,
    )


def ensure_database(cfg: PgConfig) -> None:
    """
    创建数据库（若不存在）。
    注意：需要用户有 CREATEDB 权限；否则请手工建库再运行。
    """
    # 先连接管理库（可通过 HQ_PG_ADMIN_DB 覆盖），并带 template1 兜底
    admin_db = os.getenv("HQ_PG_ADMIN_DB", "postgres")
    last_err: Optional[Exception] = None
    for db in (admin_db, "template1"):
        try:
            conn = pg_connect(db, cfg)
            conn.set_session(autocommit=True)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (cfg.dbname,))
                    exists = cur.fetchone() is not None
                    if not exists:
                        cur.execute(f'CREATE DATABASE "{cfg.dbname}";')
                        print(f"[OK] 已创建数据库: {cfg.dbname}")
                    else:
                        print(f"[OK] 数据库已存在: {cfg.dbname}")
                return
            finally:
                conn.close()
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"无法连接管理库以检查/创建数据库（尝试了 {admin_db}, template1）：{last_err}")


def ensure_tables(conn) -> None:
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
            CREATE TABLE IF NOT EXISTS stock_daily (
              code          CHAR(6) NOT NULL,
              trade_date    DATE NOT NULL,
              open          NUMERIC(18, 4),
              high          NUMERIC(18, 4),
              low           NUMERIC(18, 4),
              close         NUMERIC(18, 4),
              volume        BIGINT,
              amount        NUMERIC(20, 2),
              amplitude     NUMERIC(10, 4),   -- 振幅(%)
              pct_change    NUMERIC(10, 4),   -- 涨跌幅(%)
              change_amount NUMERIC(18, 4),   -- 涨跌额
              turnover_rate NUMERIC(10, 4),   -- 换手率(%)
              adjust        TEXT NOT NULL DEFAULT '',
              PRIMARY KEY (code, trade_date, adjust),
              CONSTRAINT fk_stock_daily_code
                FOREIGN KEY (code) REFERENCES stock_basic(code)
                ON UPDATE CASCADE ON DELETE RESTRICT
            );
            """
        )

        # 若表已存在但缺列（历史遗留），补齐列（你已删表则不会走到这里，但保留迁移兼容）
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='stock_daily';
            """
        )
        cols = {r[0] for r in cur.fetchall()}
        add_cols = {
            "amplitude": "NUMERIC(10, 4)",
            "pct_change": "NUMERIC(10, 4)",
            "change_amount": "NUMERIC(18, 4)",
            "turnover_rate": "NUMERIC(10, 4)",
        }
        for c, t in add_cols.items():
            if c not in cols:
                cur.execute(f'ALTER TABLE stock_daily ADD COLUMN {c} {t};')

        cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_daily_trade_date ON stock_daily(trade_date);")
    conn.commit()
    print("[OK] 数据表已就绪: stock_basic, stock_daily")


def infer_exchange(code: str) -> str:
    if code.startswith("6"):
        return "SH"
    if code.startswith(("0", "3", "90")):
        return "SZ"
    if code.startswith(("92", "8", "4")):
        return "BJ"
    # 兜底：按常见规则不应该出现
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


def get_all_a_stocks() -> pd.DataFrame:
    """
    返回列：code, name, exchange
    """
    # 优先：用 ak.stock_zh_a_spot() 拿到带交易所前缀的 symbol（与 stock_zh_a_daily 口径一致）
    # 其次：用东财 spot_em 拿代码/名称，再按代码规则推断交易所
    # 最后：stock_info_a_code_name 兜底
    try:
        df = ak.stock_zh_a_spot()
        code_col = "代码" if "代码" in df.columns else ("symbol" if "symbol" in df.columns else None)
        name_col = "名称" if "名称" in df.columns else ("name" if "name" in df.columns else None)
        if code_col and name_col:
            sym = df[code_col].astype(str).str.lower()
            # 期望形如 sh600000 / sz000001 / bj430047
            if sym.str.match(r"^(sh|sz|bj)\d{6}$").any():
                out = pd.DataFrame(
                    {
                        "code": sym.str[-6:],
                        "name": df[name_col].astype(str),
                        "exchange": sym.str[:2].str.upper(),
                    }
                )
                out = out.drop_duplicates(subset=["code"], keep="last").reset_index(drop=True)
                return out
    except Exception as e:
        print(f"[WARN] 获取 stock_zh_a_spot 失败，尝试其它来源：{e}", file=sys.stderr)

    try:
        df = ak.stock_zh_a_spot_em()
        code_col = "代码" if "代码" in df.columns else ("code" if "code" in df.columns else None)
        name_col = "名称" if "名称" in df.columns else ("name" if "name" in df.columns else None)
        if code_col and name_col:
            out = pd.DataFrame(
                {
                    "code": df[code_col].astype(str).str.zfill(6),
                    "name": df[name_col].astype(str),
                }
            )
            out["exchange"] = out["code"].apply(infer_exchange)
            out = out[out["exchange"] != "NA"].copy()
            # spot_em 偶尔会返回不完整数据；过小则视为失败，进入兜底
            if len(out) >= 1000:
                out = out.drop_duplicates(subset=["code"], keep="last").reset_index(drop=True)
                return out[["code", "name", "exchange"]]
    except Exception as e:
        print(f"[WARN] 获取 stock_zh_a_spot_em 失败，尝试兜底：{e}", file=sys.stderr)

    # 兜底：用 ak.stock_info_a_code_name 并推断交易所（可能不含 BJ，且受数据源影响）
    df = ak.stock_info_a_code_name()
    df = df.rename(columns={"code": "code", "name": "name"})
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["exchange"] = df["code"].apply(infer_exchange)
    df = df[df["exchange"] != "NA"].copy()
    return df.drop_duplicates(subset=["code"], keep="last").reset_index(drop=True)[["code", "name", "exchange"]]


def upsert_stock_basic(conn, stocks_df: pd.DataFrame) -> None:
    rows = []
    for r in stocks_df.itertuples(index=False):
        code = str(r.code).zfill(6)
        exchange = str(r.exchange).upper()
        if exchange == "NA":
            exchange = infer_exchange(code)
        ak_symbol = to_ak_symbol(code, exchange)
        rows.append((code, str(r.name), exchange, ak_symbol))

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
    print(f"[OK] stock_basic 已写入/更新 {len(rows)} 条")


def _normalize_daily_df(df: pd.DataFrame, source: str = "akshare") -> pd.DataFrame:
    """
    统一不同数据源的返回格式。
    AkShare (stock_zh_a_hist) -> trade_date, open, high, low, close, volume, amount, ...
    Tushare (pro_bar) -> trade_date, open, high, low, close, volume, amount, ...
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

    if source == "tushare":
        # Tushare 列名映射
        # ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
        mapping = {
            "trade_date": "trade_date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "vol": "volume",
            "amount": "amount",
            "pct_chg": "pct_change",
            "change": "change_amount",
        }
        for k, v in mapping.items():
            if k in d.columns:
                d = d.rename(columns={k: v})

        # Tushare 转换：vol(手) -> 股, amount(千元) -> 元
        if "volume" in d.columns:
            d["volume"] = d["volume"] * 100
        if "amount" in d.columns:
            d["amount"] = d["amount"] * 1000

        # Tushare trade_date 是 YYYYMMDD 字符串
        d["trade_date"] = pd.to_datetime(d["trade_date"]).dt.date
    else:
        # AkShare 列名映射
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
            "date": "trade_date",
        }
        for k, v in mapping.items():
            if k in d.columns:
                d = d.rename(columns={k: v})
        d["trade_date"] = pd.to_datetime(d["trade_date"]).dt.date

    keep = [
        c
        for c in [
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
        if c in d.columns
    ]
    d = d[keep].copy()

    for c in ["open", "high", "low", "close", "amount", "amplitude", "pct_change", "change_amount", "turnover_rate"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    if "volume" in d.columns:
        d["volume"] = pd.to_numeric(d["volume"], errors="coerce").round().astype("Int64")

    return d


def fetch_daily(code: str, exchange: str, start_date: str, end_date: str, adjust: str,
                retries: int = 3) -> pd.DataFrame:
    # 优先使用 Tushare
    ts_code = f"{code}.{exchange}"
    # Tushare adjust: None -> None, qfq -> qfq, hfq -> hfq
    ts_adj = adjust if adjust in ["qfq", "hfq"] else None

    limiter = get_tushare_limiter()
    last_err: Optional[Exception] = None

    for i in range(retries):
        try:
            # 限流：获取令牌（最多等待 60 秒）
            if not limiter.acquire(timeout=60.0):
                raise RuntimeError("Tushare 限流等待超时")

            # 使用 tushare.pro_bar
            df = ts.pro_bar(ts_code=ts_code, asset='E', freq='D', start_date=start_date, end_date=end_date, adj=ts_adj)
            if df is not None and not df.empty:
                return _normalize_daily_df(df, source="tushare")

            # 如果 Tushare 返回空，可能是该股票在 Tushare 没权限或没数据，尝试 AkShare 兜底
            # AkShare 不限流
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date,
                                    adjust=adjust)
            return _normalize_daily_df(df, source="akshare")
        except Exception as e:
            last_err = e
            # 简单退避
            time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"拉取失败 {code}({exchange}) daily: {last_err}")


def upsert_stock_daily(conn, code: str, daily_df: pd.DataFrame, adjust: str) -> int:
    if daily_df is None or daily_df.empty:
        return 0

    rows = []
    for r in daily_df.itertuples(index=False):
        # 某些字段可能不存在，使用 getattr 兜底
        rows.append(
            (
                code,
                getattr(r, "trade_date", None),
                getattr(r, "open", None),
                getattr(r, "high", None),
                getattr(r, "low", None),
                getattr(r, "close", None),
                int(getattr(r, "volume")) if getattr(r, "volume", None) is not None and pd.notna(
                    getattr(r, "volume")) else None,
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
            INSERT INTO stock_daily(
              code, trade_date, open, high, low, close, volume, amount,
              amplitude, pct_change, change_amount, turnover_rate, adjust
            )
            VALUES %s
            ON CONFLICT (code, trade_date, adjust) DO UPDATE SET
              open = EXCLUDED.open,
              high = EXCLUDED.high,
              low  = EXCLUDED.low,
              close= EXCLUDED.close,
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
    p.add_argument("--adjust", type=str, default="", help='复权类型：""|qfq|hfq（默认不复权）')
    p.add_argument("--limit", type=int, default=0, help="仅处理前 N 只股票（调试用，0 表示全部）")
    p.add_argument("--sleep", type=float, default=0.0, help="每只股票拉取后的休眠秒数")
    p.add_argument("--ts-rpm", type=int, default=50, help="Tushare 每分钟调用次数限制（默认 50，0 表示禁用限流）")
    p.add_argument("--disable-proxy", action="store_true",
                   help="临时禁用 HTTP(S)_PROXY 等代理环境变量（某些网络会导致东财等源不可用）")
    p.add_argument(
        "--allow-small-universe",
        action="store_true",
        help="允许股票列表数量过少时继续（默认会认为网络/代理异常并报错；A股正常应>1000）",
    )
    return p.parse_args()


def maybe_disable_proxy(disable: bool) -> None:
    if not disable:
        return
    for k in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
    ):
        os.environ.pop(k, None)
    os.environ["NO_PROXY"] = "*"
    print("[INFO] 已按 --disable-proxy 禁用代理环境变量")


def main() -> int:
    args = parse_args()
    cfg = load_pg_config()

    maybe_disable_proxy(args.disable_proxy)

    # 初始化 Tushare 限流器
    if args.ts_rpm > 0:
        global _tushare_limiter
        _tushare_limiter = TushareRateLimiter(calls_per_minute=args.ts_rpm, burst=min(10, args.ts_rpm))
        print(f"[INFO] Tushare 限流已启用：{args.ts_rpm} 次/分钟")

    # 初始化 Tushare
    ts_token = os.getenv("HQ_TUSHARE_TOKEN") or os.getenv("TUSHARE_TOKEN")
    if ts_token:
        ts.set_token(ts_token)
        print("[INFO] 已初始化 Tushare token")
    else:
        print("[WARN] 未找到 Tushare token，将仅使用 AkShare")

    today = date.today()
    default_start = today - timedelta(days=365 * 2)
    start_date = args.start_date or yyyymmdd(default_start)
    end_date = args.end_date or yyyymmdd(today)
    adjust = args.adjust if args.adjust is not None else ""

    print(f"[INFO] 日期范围: {start_date} ~ {end_date}；adjust={repr(adjust)}")

    ensure_database(cfg)
    conn = pg_connect(cfg.dbname, cfg)
    try:
        ensure_tables(conn)

        stocks = get_all_a_stocks()
        if (not args.allow_small_universe) and len(stocks) < 1000:
            raise RuntimeError(
                f"获取到的股票列表数量过少（{len(stocks)}），疑似网络/代理限制导致未取到全市场。"
                "可尝试：加参数 --disable-proxy（清理代理环境变量），或检查网络/证书/防火墙限制，"
                "或使用 --allow-small-universe 强制继续（不推荐，会导致仅入库少量股票）。"
            )
        if args.limit and args.limit > 0:
            stocks = stocks.head(args.limit).copy()
        print(f"[INFO] 股票数量: {len(stocks)}")

        upsert_stock_basic(conn, stocks)

        ok, fail, total_rows = 0, 0, 0
        for idx, r in enumerate(stocks.itertuples(index=False), start=1):
            code = str(r.code).zfill(6)
            exchange = str(r.exchange).upper()
            name = str(r.name)

            try:
                df_daily = fetch_daily(code=code, exchange=exchange, start_date=start_date, end_date=end_date,
                                       adjust=adjust)
                n = upsert_stock_daily(conn, code=code, daily_df=df_daily, adjust=adjust)
                total_rows += n
                ok += 1
                if idx % 50 == 0 or idx == len(stocks):
                    print(f"[PROGRESS] {idx}/{len(stocks)} OK={ok} FAIL={fail} 累计写入行数={total_rows}")
            except Exception as e:
                fail += 1
                print(f"[ERROR] {idx}/{len(stocks)} {code} {name} {exchange} 拉取/写入失败: {e}", file=sys.stderr)

            if args.sleep and args.sleep > 0:
                time.sleep(args.sleep)

        print(f"[DONE] 完成：OK={ok} FAIL={fail} 写入行数={total_rows}")
        return 0 if fail == 0 else 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
