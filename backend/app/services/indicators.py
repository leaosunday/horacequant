from __future__ import annotations

import numpy as np
import pandas as pd


def sma_tdx(x: pd.Series, n: int, m: int) -> pd.Series:
    """
    通达信 SMA(X,N,M) 递推：
      SMA = (M*X + (N-M)*REF(SMA,1)) / N
    """
    x = x.astype(float)
    out = pd.Series(index=x.index, dtype="float64")
    if len(x) == 0:
        return out
    out.iloc[0] = x.iloc[0]
    for i in range(1, len(x)):
        out.iloc[i] = (m * x.iloc[i] + (n - m) * out.iloc[i - 1]) / n
    return out


def kdj(df: pd.DataFrame, n: int = 9, k_n: int = 3, d_n: int = 3) -> pd.DataFrame:
    low_n = df["low"].rolling(window=n, min_periods=1).min()
    high_n = df["high"].rolling(window=n, min_periods=1).max()
    denom = (high_n - low_n).replace(0, np.nan)
    rsv = (df["close"] - low_n) / denom * 100.0
    rsv = rsv.fillna(0.0)

    k = sma_tdx(rsv, k_n, 1)
    d = sma_tdx(k, d_n, 1)
    j = 3 * k - 2 * d
    return pd.DataFrame({"kdj_k": k, "kdj_d": d, "kdj_j": j})


def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = 2 * (dif - dea)
    return pd.DataFrame({"macd_dif": dif, "macd_dea": dea, "macd_hist": hist})


def short_trend_line(df: pd.DataFrame, n: int = 10) -> pd.Series:
    return df["close"].ewm(span=n, adjust=False).mean().ewm(span=n, adjust=False).mean()


def bull_bear_line(df: pd.DataFrame, periods: tuple[int, int, int, int] = (14, 28, 57, 114)) -> pd.Series:
    ma = [df["close"].rolling(window=p, min_periods=1).mean() for p in periods]
    return sum(ma) / float(len(ma))


def enrich_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    输入 df 需要包含：
      trade_date/open/high/low/close/volume/amount
    输出：在原 df 上附加 macd/kdj/短期趋势线/知行多空线
    """
    if df.empty:
        return df
    out = df.copy()
    out = out.sort_values("trade_date").reset_index(drop=True)

    # asyncpg/psycopg2 可能返回 Decimal，统一转为 float，避免计算报错
    for c in ("open", "high", "low", "close", "amount"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    if "volume" in out.columns:
        # volume 用整数，但缺失时允许 NaN
        out["volume"] = pd.to_numeric(out["volume"], errors="coerce")

    out["short_trend_line"] = short_trend_line(out)
    out["bull_bear_line"] = bull_bear_line(out)

    out = pd.concat([out, macd(out), kdj(out)], axis=1)
    return out

