"""
从 PostgreSQL 读取 A 股历史日K线，按通达信选股公式（.tdx）计算并选股，结果写回 PostgreSQL。

默认适配本项目的库表：
  - stock_basic(code, name, exchange, ak_symbol, ...)
  - stock_daily(code, trade_date, open, high, low, close, volume, amount, adjust, ...)

当前实现的 TDX 公式子集（覆盖 rules/b1.tdx 所需）：
  - 基础字段：O/H/L/C(LOSE)/V(OL)/AMOUNT
  - 运算：+ - * /, 比较 <= >= < >, 逻辑 AND OR NOT, 括号
  - 函数：REF(x,n), MA(x,n), EMA(x,n), SMA(x,n,m), LLV(x,n), HHV(x,n), INBLOCK('创业板'/'科创板'/'北证A股')
  - 语句：变量赋值 := ，输出变量 : （如 “选股条件:”）

用法示例：
  conda activate horacequant
  export PG_HOST=127.0.0.1
  export PG_PORT=5432
  export PG_USER=你的pg用户名
  export PG_PASSWORD=你的pg密码  # 可为空
  export PG_DB=horace_quant
  python stock_picker_tdx.py --rule rules/b1.tdx --rule-name b1

  # 指定选股日期（默认取数据库中的最新交易日）
  python stock_picker_tdx.py --rule rules/b1.tdx --rule-name b1 --trade-date 2025-12-11
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import pandas as pd
import psycopg2
import psycopg2.extras
import psycopg2.sql


@dataclass(frozen=True)
class PgConfig:
    host: str
    port: int
    user: str
    password: str
    dbname: str


def load_pg_config() -> PgConfig:
    host = os.getenv("PG_HOST", "127.0.0.1")
    port = int(os.getenv("PG_PORT", "5432"))
    user = os.getenv("PG_USER", getpass.getuser())
    password = os.getenv("PG_PASSWORD", "")
    dbname = os.getenv("PG_DB", "horace_quant")
    return PgConfig(host=host, port=port, user=user, password=password, dbname=dbname)


def pg_connect(cfg: PgConfig):
    return psycopg2.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        dbname=cfg.dbname,
    )


def ensure_result_table(conn, table_name: str) -> None:
    """
    结果表按交易日分表：stock_pick_results_YYYYMMDD
    只写入入选结果，不存 picked 字段。
    """
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", table_name):
        raise ValueError(f"非法表名：{table_name}")

    suffix = table_name.split("_")[-1] if "_" in table_name else "x"
    idx_rule = f"idx_spr_{suffix}_rule"
    idx_code = f"idx_spr_{suffix}_code"

    with conn.cursor() as cur:
        cur.execute(
            psycopg2.sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {t} (
                  rule_name   TEXT NOT NULL,
                  trade_date  DATE NOT NULL,
                  code        CHAR(6) NOT NULL REFERENCES stock_basic(code),
                  name        TEXT NOT NULL,
                  exchange    CHAR(2) NOT NULL,
                  metrics     JSONB,
                  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  PRIMARY KEY (rule_name, code)
                );
                """
            ).format(t=psycopg2.sql.Identifier(table_name))
        )
        cur.execute(
            psycopg2.sql.SQL("CREATE INDEX IF NOT EXISTS {idx} ON {t}(rule_name);").format(
                idx=psycopg2.sql.Identifier(idx_rule),
                t=psycopg2.sql.Identifier(table_name),
            )
        )
        cur.execute(
            psycopg2.sql.SQL("CREATE INDEX IF NOT EXISTS {idx} ON {t}(code);").format(
                idx=psycopg2.sql.Identifier(idx_code),
                t=psycopg2.sql.Identifier(table_name),
            )
        )
    conn.commit()


def get_latest_trade_date(conn, adjust: str) -> date:
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(trade_date) FROM stock_daily WHERE adjust = %s;", (adjust,))
        d = cur.fetchone()[0]
        if d is None:
            cur.execute("SELECT adjust, COUNT(*) FROM stock_daily GROUP BY adjust ORDER BY COUNT(*) DESC;")
            avail = cur.fetchall()
            raise RuntimeError(f"stock_daily 中 adjust={adjust!r} 没有任何数据；可用 adjust/行数：{avail}")
        return d


def resolve_adjust(conn, requested: str) -> str:
    """
    如果 requested 为空字符串，则：
      - 优先使用库里确实存在的 adjust=''
      - 否则自动选取行数最多的 adjust（例如 'qfq'）
    """
    if requested != "":
        return requested
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM stock_daily WHERE adjust = %s;", ("",))
        n0 = cur.fetchone()[0]
        if n0 and int(n0) > 0:
            return ""
        cur.execute("SELECT adjust FROM stock_daily GROUP BY adjust ORDER BY COUNT(*) DESC LIMIT 1;")
        row = cur.fetchone()
        if not row:
            return ""
        picked = row[0]
        print(f"[INFO] 未显式指定 --adjust，自动使用数据库中行数最多的 adjust={picked!r}")
        return picked


def load_universe(conn, limit: int = 0) -> List[Tuple[str, str, str]]:
    """
    返回 [(code, name, exchange), ...]
    """
    sql = "SELECT code, name, exchange FROM stock_basic ORDER BY code;"
    if limit and limit > 0:
        sql = "SELECT code, name, exchange FROM stock_basic ORDER BY code LIMIT %s;"
        params: Tuple[Any, ...] = (limit,)
    else:
        params = ()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [(r[0].strip(), r[1], r[2].strip()) for r in rows]


def load_kline(conn, code: str, trade_date: date, adjust: str, lookback_days: int) -> pd.DataFrame:
    """
    拉取某股票到 trade_date 为止的历史K线（用于计算 MA114 等）。
    """
    start = trade_date - timedelta(days=lookback_days)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT trade_date, open, high, low, close, volume, amount
            FROM stock_daily
            WHERE code = %s AND adjust = %s AND trade_date BETWEEN %s AND %s
            ORDER BY trade_date;
            """,
            (code, adjust, start, trade_date),
        )
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["trade_date", "open", "high", "low", "close", "volume", "amount"])
    return df


# -----------------------------
# TDX 公式解释器（b1.tdx 所需子集）
# -----------------------------

Token = Tuple[str, str]  # (type, value)


_TOKEN_RE = re.compile(
    r"""
    (?P<SPACE>\s+)
  | (?P<NUMBER>\d+(?:\.\d+)?)
  | (?P<STRING>'[^']*')
  | (?P<OP><=|>=|<>|!=|==|:=|[+\-*/(),:<>])
  | (?P<IDENT>[\w\u4e00-\u9fff]+)
  """,
    re.VERBOSE | re.UNICODE,
)


def tokenize(expr: str) -> List[Token]:
    out: List[Token] = []
    i = 0
    while i < len(expr):
        m = _TOKEN_RE.match(expr, i)
        if not m:
            raise ValueError(f"无法解析公式，位置 {i}: {expr[i:i+40]!r}")
        kind = m.lastgroup
        val = m.group(kind)  # type: ignore[arg-type]
        i = m.end()
        if kind == "SPACE":
            continue
        if kind == "IDENT":
            up = val.upper()
            if up in ("AND", "OR", "NOT"):
                out.append(("KW", up))
            else:
                out.append(("IDENT", val))
        elif kind == "STRING":
            out.append(("STRING", val[1:-1]))
        elif kind == "NUMBER":
            out.append(("NUMBER", val))
        else:
            out.append(("OP", val))
    return out


Value = Union[pd.Series, float, int, bool, str]


def _as_series(v: Value, index: pd.Index) -> pd.Series:
    if isinstance(v, pd.Series):
        return v
    if isinstance(v, bool):
        return pd.Series([v] * len(index), index=index)
    if isinstance(v, (int, float)):
        return pd.Series([float(v)] * len(index), index=index)
    raise TypeError(f"无法转换为序列：{type(v)}")


def _as_bool_series(v: Value, index: pd.Index) -> pd.Series:
    s = _as_series(v, index)
    if s.dtype != bool:
        s = s.astype(bool)
    return s


class TdxContext:
    def __init__(self, df: pd.DataFrame, code: str, exchange: str, name: str):
        self.df = df
        self.code = code
        self.exchange = exchange.upper()
        self.name = name
        self.index = df.index

        # 基础字段映射（兼容 C/CLOSE/HIGH/...）
        self.base: Dict[str, pd.Series] = {
            "OPEN": df["open"],
            "O": df["open"],
            "HIGH": df["high"],
            "H": df["high"],
            "LOW": df["low"],
            "L": df["low"],
            "CLOSE": df["close"],
            "C": df["close"],
            "VOL": df["volume"] if "volume" in df.columns else pd.Series([None] * len(df), index=df.index),
            "V": df["volume"] if "volume" in df.columns else pd.Series([None] * len(df), index=df.index),
            "AMOUNT": df["amount"] if "amount" in df.columns else pd.Series([None] * len(df), index=df.index),
        }
        self.vars: Dict[str, Value] = {}

    def get_ident(self, name: str) -> Value:
        # 变量优先，其次基础字段
        if name in self.vars:
            return self.vars[name]
        up = name.upper()
        if up in self.base:
            return self.base[up]
        # 未定义变量默认报错（避免 silent bug）
        raise KeyError(f"未知标识符：{name}")

    # --- TDX 常用函数实现 ---
    def REF(self, x: Value, n: Value) -> pd.Series:
        n_int = int(float(n)) if not isinstance(n, pd.Series) else int(float(n.iloc[-1]))
        s = _as_series(x, self.index)
        return s.shift(n_int)

    def MA(self, x: Value, n: Value) -> pd.Series:
        n_int = int(float(n)) if not isinstance(n, pd.Series) else int(float(n.iloc[-1]))
        s = _as_series(x, self.index)
        return s.rolling(window=n_int, min_periods=1).mean()

    def EMA(self, x: Value, n: Value) -> pd.Series:
        n_int = int(float(n)) if not isinstance(n, pd.Series) else int(float(n.iloc[-1]))
        s = _as_series(x, self.index)
        return s.ewm(span=n_int, adjust=False).mean()

    def LLV(self, x: Value, n: Value) -> pd.Series:
        n_int = int(float(n)) if not isinstance(n, pd.Series) else int(float(n.iloc[-1]))
        s = _as_series(x, self.index)
        return s.rolling(window=n_int, min_periods=1).min()

    def HHV(self, x: Value, n: Value) -> pd.Series:
        n_int = int(float(n)) if not isinstance(n, pd.Series) else int(float(n.iloc[-1]))
        s = _as_series(x, self.index)
        return s.rolling(window=n_int, min_periods=1).max()

    def SMA(self, x: Value, n: Value, m: Value) -> pd.Series:
        """
        通达信 SMA: SMA(X,N,M) = (M*X + (N-M)*REF(SMA,1)) / N，递推算法。
        """
        n_int = int(float(n)) if not isinstance(n, pd.Series) else int(float(n.iloc[-1]))
        m_int = int(float(m)) if not isinstance(m, pd.Series) else int(float(m.iloc[-1]))
        x_s = _as_series(x, self.index).astype(float)
        out = pd.Series(index=self.index, dtype="float64")
        if len(out) == 0:
            return out
        out.iloc[0] = x_s.iloc[0]
        for i in range(1, len(out)):
            out.iloc[i] = (m_int * x_s.iloc[i] + (n_int - m_int) * out.iloc[i - 1]) / n_int
        return out

    def INBLOCK(self, block: Value) -> pd.Series:
        """
        这里用“代码前缀/交易所”近似实现板块判断（离线，无需额外数据源）。
        b1.tdx 只用到：创业板 / 科创板 / 北证A股
        """
        if not isinstance(block, str):
            raise TypeError("INBLOCK 参数必须是字符串，如 INBLOCK('创业板')")
        b = block.strip()
        code = self.code
        ex = self.exchange
        if b == "创业板":
            flag = code.startswith(("300", "301", "302"))
        elif b == "科创板":
            flag = code.startswith(("688", "689"))
        elif b in ("北证A股", "北证"):
            flag = (ex == "BJ") or code.startswith(("83", "87", "88", "92"))
        else:
            # 未覆盖的板块：默认 False
            flag = False
        return pd.Series([flag] * len(self.index), index=self.index, dtype=bool)

    def NAMELIKE(self, pattern: Value) -> pd.Series:
        """
        通达信 NAMELIKE：按股票名称做模式匹配。
        这里做一个离线实现：
          - pattern 不含 '*'：按“包含子串”判断（例如 'ST' in name）
          - pattern 含 '*'：'*' 视为通配任意长度字符，转换成正则并做 search
        """
        if not isinstance(pattern, str):
            raise TypeError("NAMELIKE 参数必须是字符串，如 NAMELIKE('ST') 或 NAMELIKE('S*ST')")
        p = pattern.strip()
        nm = (self.name or "").strip()
        if p == "":
            flag = False
        elif "*" not in p:
            flag = p in nm
        else:
            # 将 * 转成 .*
            re_pat = re.escape(p).replace("\\*", ".*")
            flag = re.search(re_pat, nm) is not None
        return pd.Series([flag] * len(self.index), index=self.index, dtype=bool)


class Parser:
    def __init__(self, tokens: List[Token], ctx: TdxContext):
        self.toks = tokens
        self.i = 0
        self.ctx = ctx

    def peek(self) -> Optional[Token]:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def eat(self, ttype: str, value: Optional[str] = None) -> Token:
        tok = self.peek()
        if tok is None:
            raise ValueError("解析失败：意外结束")
        if tok[0] != ttype:
            raise ValueError(f"解析失败：期望 {ttype}，得到 {tok}")
        if value is not None and tok[1] != value:
            raise ValueError(f"解析失败：期望 {value!r}，得到 {tok}")
        self.i += 1
        return tok

    def match(self, ttype: str, value: Optional[str] = None) -> bool:
        tok = self.peek()
        if tok is None or tok[0] != ttype:
            return False
        if value is not None and tok[1] != value:
            return False
        return True

    def parse(self) -> Value:
        return self.parse_or()

    def parse_or(self) -> Value:
        left = self.parse_and()
        while self.match("KW", "OR"):
            self.eat("KW", "OR")
            right = self.parse_and()
            left = _as_bool_series(left, self.ctx.index) | _as_bool_series(right, self.ctx.index)
        return left

    def parse_and(self) -> Value:
        left = self.parse_not()
        while self.match("KW", "AND"):
            self.eat("KW", "AND")
            right = self.parse_not()
            left = _as_bool_series(left, self.ctx.index) & _as_bool_series(right, self.ctx.index)
        return left

    def parse_not(self) -> Value:
        if self.match("KW", "NOT"):
            self.eat("KW", "NOT")
            v = self.parse_not()
            return ~_as_bool_series(v, self.ctx.index)
        return self.parse_compare()

    def parse_compare(self) -> Value:
        left = self.parse_add()
        if self.match("OP") and self.peek()[1] in ("<=", ">=", "<", ">", "==", "!=", "<>"):
            op = self.eat("OP")[1]
            right = self.parse_add()
            a = _as_series(left, self.ctx.index).astype(float)
            b = _as_series(right, self.ctx.index).astype(float)
            if op == "<=":
                return a <= b
            if op == ">=":
                return a >= b
            if op == "<":
                return a < b
            if op == ">":
                return a > b
            if op in ("!=", "<>"):
                return a != b
            if op == "==":
                return a == b
        return left

    def parse_add(self) -> Value:
        left = self.parse_mul()
        while self.match("OP") and self.peek()[1] in ("+", "-"):
            op = self.eat("OP")[1]
            right = self.parse_mul()
            a = _as_series(left, self.ctx.index).astype(float)
            b = _as_series(right, self.ctx.index).astype(float)
            left = a + b if op == "+" else a - b
        return left

    def parse_mul(self) -> Value:
        left = self.parse_unary()
        while self.match("OP") and self.peek()[1] in ("*", "/"):
            op = self.eat("OP")[1]
            right = self.parse_unary()
            a = _as_series(left, self.ctx.index).astype(float)
            b = _as_series(right, self.ctx.index).astype(float)
            left = a * b if op == "*" else a / b
        return left

    def parse_unary(self) -> Value:
        if self.match("OP", "+"):
            self.eat("OP", "+")
            return self.parse_unary()
        if self.match("OP", "-"):
            self.eat("OP", "-")
            v = self.parse_unary()
            return -_as_series(v, self.ctx.index).astype(float)
        return self.parse_primary()

    def parse_primary(self) -> Value:
        tok = self.peek()
        if tok is None:
            raise ValueError("解析失败：primary 处意外结束")
        if tok[0] == "NUMBER":
            self.eat("NUMBER")
            return float(tok[1])
        if tok[0] == "STRING":
            self.eat("STRING")
            return tok[1]
        if tok[0] == "IDENT":
            name = self.eat("IDENT")[1]
            # 函数调用
            if self.match("OP", "("):
                self.eat("OP", "(")
                args: List[Value] = []
                if not self.match("OP", ")"):
                    args.append(self.parse())
                    while self.match("OP", ","):
                        self.eat("OP", ",")
                        args.append(self.parse())
                self.eat("OP", ")")
                return self.call_func(name, args)
            return self.ctx.get_ident(name)
        if tok[0] == "OP" and tok[1] == "(":
            self.eat("OP", "(")
            v = self.parse()
            self.eat("OP", ")")
            return v
        raise ValueError(f"解析失败：未知 token {tok}")

    def call_func(self, name: str, args: List[Value]) -> Value:
        up = name.upper()
        if up == "REF":
            return self.ctx.REF(args[0], args[1])
        if up == "MA":
            return self.ctx.MA(args[0], args[1])
        if up == "EMA":
            return self.ctx.EMA(args[0], args[1])
        if up == "SMA":
            return self.ctx.SMA(args[0], args[1], args[2])
        if up == "LLV":
            return self.ctx.LLV(args[0], args[1])
        if up == "HHV":
            return self.ctx.HHV(args[0], args[1])
        if up == "INBLOCK":
            return self.ctx.INBLOCK(args[0])
        if up == "NAMELIKE":
            return self.ctx.NAMELIKE(args[0])
        raise KeyError(f"未支持的函数：{name}")


def parse_tdx_file(text: str) -> Tuple[Dict[str, str], str]:
    """
    返回：
      - statements: {var_name: expr_str}（包含 := 与 : 两种）
      - output_var: 输出变量名（优先取最后一个使用 ":" 的变量；否则取最后一条语句的变量）
    """
    # 去掉空行；保留中文变量名
    lines = [ln.rstrip() for ln in text.splitlines()]
    buf = "\n".join(lines)
    # 按分号切分语句（通达信语句以 ; 结尾）
    raw_stmts = [s.strip() for s in buf.split(";") if s.strip()]

    stmts: Dict[str, str] = {}
    output_var = ""
    last_var = ""
    for s in raw_stmts:
        # 兼容一行里多个语句被 split 后残留换行
        s = " ".join([x.strip() for x in s.splitlines() if x.strip()])
        if ":=" in s:
            var, expr = s.split(":=", 1)
            var = var.strip()
            expr = expr.strip()
            stmts[var] = expr
            last_var = var
        elif ":" in s:
            # 输出变量：NAME: expr
            var, expr = s.split(":", 1)
            var = var.strip()
            expr = expr.strip()
            stmts[var] = expr
            output_var = var
            last_var = var
        else:
            # 无法识别的语句：忽略/报错
            raise ValueError(f"无法识别的语句：{s}")

    if not output_var:
        output_var = last_var
    if not output_var:
        raise ValueError("tdx 文件中未找到输出条件")
    return stmts, output_var


def eval_tdx(stmts: Dict[str, str], output_var: str, ctx: TdxContext) -> Dict[str, Value]:
    """
    执行语句，返回 ctx.vars（包含 output_var 对应序列）。
    """
    for var, expr in stmts.items():
        tokens = tokenize(expr)
        v = Parser(tokens, ctx).parse()
        ctx.vars[var] = v
    if output_var not in ctx.vars:
        raise RuntimeError(f"输出变量不存在：{output_var}")
    return ctx.vars


# -----------------------------
# 主流程：计算 + 选股 + 入库
# -----------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--rule", type=str, default="rules/b1.tdx", help="通达信选股公式文件路径")
    p.add_argument("--rule-name", type=str, default="b1", help="规则名（写入结果表时使用）")
    p.add_argument("--trade-date", type=str, default="", help="选股日期 YYYY-MM-DD（默认数据库最新交易日）")
    p.add_argument("--adjust", type=str, default="", help='复权类型：""|qfq|hfq（需与入库时一致）')
    p.add_argument("--lookback-days", type=int, default=450, help="拉取历史窗口（天），至少需覆盖 MA114 等")
    p.add_argument("--limit", type=int, default=0, help="仅处理前 N 只股票（调试用）")
    p.add_argument(
        "--result-table-prefix",
        type=str,
        default="stock_pick_results_",
        help="结果表前缀，最终表名=前缀+YYYYMMDD（默认 stock_pick_results_）",
    )
    p.add_argument("--retention-days", type=int, default=30, help="结果分表保留天数，默认 30 天；到期自动删表")
    p.add_argument("--disable-cleanup", action="store_true", help="禁用过期结果表清理")
    return p.parse_args()


def result_table_name(prefix: str, td: date) -> str:
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", prefix):
        raise ValueError(f"非法前缀：{prefix}")
    return f"{prefix}{td.strftime('%Y%m%d')}"


def cleanup_old_result_tables(conn, prefix: str, retention_days: int) -> int:
    """
    删除超过 retention_days 的结果分表。
    规则：表名匹配 {prefix}\\d{8}，按日期后缀判断。
    """
    if retention_days <= 0:
        return 0
    cutoff = date.today() - timedelta(days=retention_days)
    pattern = re.compile(re.escape(prefix) + r"(\\d{8})$")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
              AND table_name LIKE %s;
            """,
            (prefix + "%",),
        )
        tables = [r[0] for r in cur.fetchall()]

        to_drop: List[str] = []
        for t in tables:
            m = pattern.match(t)
            if not m:
                continue
            try:
                t_date = datetime.strptime(m.group(1), "%Y%m%d").date()
            except Exception:
                continue
            if t_date < cutoff:
                to_drop.append(t)

        for t in to_drop:
            cur.execute(psycopg2.sql.SQL("DROP TABLE IF EXISTS {t};").format(t=psycopg2.sql.Identifier(t)))

    if to_drop:
        conn.commit()
    return len(to_drop)


def build_metrics_en(vars_: Dict[str, Value]) -> Dict[str, Optional[float]]:
    """
    metrics 字段使用英文 key，避免中文。
    """
    mapping = {
        "J": "j",
        "短期趋势线": "short_trend_line",
        "知行多空线": "bull_bear_line",
        "振幅": "amplitude_pct",
        "涨跌幅": "change_pct",
    }
    out: Dict[str, Optional[float]] = {}
    for k_cn, k_en in mapping.items():
        if k_cn not in vars_:
            continue
        vv = vars_[k_cn]
        if isinstance(vv, pd.Series):
            v_last = vv.iloc[-1]
            out[k_en] = None if pd.isna(v_last) else float(v_last)
    return out


def main() -> int:
    args = parse_args()
    cfg = load_pg_config()

    rule_path = os.path.join(os.getcwd(), args.rule) if not os.path.isabs(args.rule) else args.rule
    if not os.path.exists(rule_path):
        raise SystemExit(f"规则文件不存在：{rule_path}")
    with open(rule_path, "r", encoding="utf-8") as f:
        tdx_text = f.read()

    stmts, output_var = parse_tdx_file(tdx_text)
    print(f"[INFO] 规则: {args.rule_name}；输出变量: {output_var}；语句数: {len(stmts)}")

    conn = pg_connect(cfg)
    try:
        adjust = resolve_adjust(conn, args.adjust)
        if args.trade_date:
            td = datetime.strptime(args.trade_date, "%Y-%m-%d").date()
        else:
            td = get_latest_trade_date(conn, adjust=adjust)
        print(f"[INFO] 选股交易日: {td}；adjust={repr(adjust)}")

        table_name = result_table_name(args.result_table_prefix, td)
        ensure_result_table(conn, table_name)
        if not args.disable_cleanup:
            dropped = cleanup_old_result_tables(conn, args.result_table_prefix, args.retention_days)
            if dropped:
                print(f"[INFO] 已清理过期结果表 {dropped} 张（保留 {args.retention_days} 天）")

        universe = load_universe(conn, limit=args.limit)
        if not universe:
            raise RuntimeError("stock_basic 为空（请先运行入库脚本）")
        print(f"[INFO] 股票数量: {len(universe)}")

        # 只写入入选股票
        results: List[Tuple[str, date, str, str, str, Any]] = []
        ok, fail, picked_n = 0, 0, 0

        for idx, (code, name, exchange) in enumerate(universe, start=1):
            try:
                df = load_kline(conn, code=code, trade_date=td, adjust=adjust, lookback_days=args.lookback_days)
                if df.empty or df["trade_date"].iloc[-1] != td:
                    # 无数据或缺当天数据：跳过（不计入 fail）
                    continue
                df = df.reset_index(drop=True)
                df.index = pd.RangeIndex(len(df))

                ctx = TdxContext(df=df, code=code, exchange=exchange, name=name)
                vars_ = eval_tdx(stmts, output_var, ctx)

                cond = vars_[output_var]
                cond_s = _as_bool_series(cond, ctx.index)
                picked = bool(cond_s.iloc[-1])

                if picked:
                    picked_n += 1
                    metrics = build_metrics_en(vars_)
                    metrics_jsonb = psycopg2.extras.Json(metrics, dumps=lambda o: json.dumps(o, ensure_ascii=False))
                    results.append((args.rule_name, td, code, name, exchange, metrics_jsonb))
                ok += 1
            except Exception as e:
                fail += 1
                print(f"[WARN] {idx}/{len(universe)} {code} {name} 计算失败：{e}", file=sys.stderr)

            if idx % 200 == 0:
                print(f"[PROGRESS] {idx}/{len(universe)} OK={ok} FAIL={fail} PICKED={picked_n}")

        # 批量写入结果表
        if results:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    psycopg2.sql.SQL(
                        """
                        INSERT INTO {t}(rule_name, trade_date, code, name, exchange, metrics)
                        VALUES %s
                        ON CONFLICT (rule_name, code) DO UPDATE SET
                          trade_date = EXCLUDED.trade_date,
                          name = EXCLUDED.name,
                          exchange = EXCLUDED.exchange,
                          metrics = EXCLUDED.metrics,
                          created_at = NOW();
                        """
                    ).format(t=psycopg2.sql.Identifier(table_name)),
                    results,
                    page_size=2000,
                )
            conn.commit()

        print(f"[DONE] 交易日={td} 规则={args.rule_name} 入选={picked_n} 写入表={table_name} 行数={len(results)} 失败={fail}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

