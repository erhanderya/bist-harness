"""Technical indicators (pure, causal: value at t depends only on bars <= t) + the calculate_indicators tool."""
from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from datetime import date

from . import store
from .envelope import tool, warn


# ---------------------------------------------------------------- primitives
def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    au = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    ad = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    out = 100 - 100 / (1 + au / ad.where(ad != 0))
    out = out.where(ad != 0, np.where(au > 0, 100.0, 50.0))
    return out.where(au.notna() & ad.notna())


def macd(s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(s, fast) - ema(s, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": line - sig})


def bollinger(s: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = sma(s, n)
    sd = s.rolling(n, min_periods=n).std(ddof=0)
    up, lo = mid + k * sd, mid - k * sd
    return pd.DataFrame({"bb_mid": mid, "bb_upper": up, "bb_lower": lo,
                         "bb_pct_b": (s - lo) / (up - lo).where(up != lo), "bb_bandwidth": (up - lo) / mid})


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def kama(s: pd.Series, n: int = 10, fast: int = 2, slow: int = 30) -> pd.Series:
    change = (s - s.shift(n)).abs()
    vol = s.diff().abs().rolling(n, min_periods=n).sum()
    er = (change / vol.where(vol != 0)).fillna(0.0)
    f, sl = 2 / (fast + 1), 2 / (slow + 1)
    sc = ((er * (f - sl) + sl) ** 2).to_numpy()
    x = s.to_numpy(dtype=float)
    out = np.full(len(x), np.nan)
    start = n - 1
    if len(x) > start:
        out[start] = x[start]
        for i in range(start + 1, len(x)):
            out[i] = out[i - 1] + sc[i] * (x[i] - out[i - 1])
    return pd.Series(out, index=s.index)


def supertrend(df: pd.DataFrame, n: int = 10, mult: float = 3.0) -> pd.DataFrame:
    a = atr(df, n).to_numpy()
    h, l, c = (df[k].to_numpy(dtype=float) for k in ("high", "low", "close"))
    hl2 = (h + l) / 2
    ub, lb = hl2 + mult * a, hl2 - mult * a
    fub, flb = np.full(len(c), np.nan), np.full(len(c), np.nan)
    d, st = np.full(len(c), np.nan), np.full(len(c), np.nan)
    started = False
    for i in range(len(c)):
        if np.isnan(a[i]):
            continue
        if not started:
            fub[i], flb[i], d[i] = ub[i], lb[i], (1.0 if c[i] > hl2[i] else -1.0)
            started = True
        else:
            fub[i] = ub[i] if (ub[i] < fub[i - 1] or c[i - 1] > fub[i - 1]) else fub[i - 1]
            flb[i] = lb[i] if (lb[i] > flb[i - 1] or c[i - 1] < flb[i - 1]) else flb[i - 1]
            d[i] = 1.0 if c[i] > fub[i - 1] else (-1.0 if c[i] < flb[i - 1] else d[i - 1])
        st[i] = flb[i] if d[i] == 1 else fub[i]
    return pd.DataFrame({"st_line": st, "st_dir": d}, index=df.index)


def ichimoku(df: pd.DataFrame, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52, shift: int = 26) -> pd.DataFrame:
    def mid(n):
        return (df["high"].rolling(n, min_periods=n).max() + df["low"].rolling(n, min_periods=n).min()) / 2

    t, k = mid(tenkan), mid(kijun)
    return pd.DataFrame({
        "ich_tenkan": t, "ich_kijun": k,
        # the cloud drawn at t was computed `shift` bars ago -> using shift(+shift) is causal
        "ich_span_a": ((t + k) / 2).shift(shift), "ich_span_b": mid(senkou_b).shift(shift),
        "ich_chikou_ref": df["close"].shift(shift),  # price 26 bars ago, to be compared with today's close
    })


# ---------------------------------------------------------------- configuration + frame
class IndicatorConfig(BaseModel):
    sma_windows: list[int] = Field(default=[20, 50, 200])
    ema_windows: list[int] = Field(default=[12, 26])
    rsi_window: int = 14
    macd: tuple[int, int, int] = (12, 26, 9)
    bollinger: tuple[int, float] = (20, 2.0)
    atr_window: int = 14
    kama: tuple[int, int, int] = (10, 2, 30)
    supertrend: tuple[int, float] = (10, 3.0)
    ichimoku: tuple[int, int, int] = (9, 26, 52)


def indicator_frame(bars: pd.DataFrame, cfg: IndicatorConfig | None = None) -> pd.DataFrame:
    """All indicators over the whole history. `bars`: adjusted OHLC(V) indexed by date."""
    cfg = cfg or IndicatorConfig()
    c = bars["close"]
    parts = [bars[["open", "high", "low", "close", "volume"]]]
    for n in cfg.sma_windows:
        parts.append(sma(c, n).rename(f"sma_{n}"))
    for n in cfg.ema_windows:
        parts.append(ema(c, n).rename(f"ema_{n}"))
    parts.append(rsi(c, cfg.rsi_window).rename("rsi"))
    parts.append(macd(c, *cfg.macd))
    parts.append(bollinger(c, *cfg.bollinger))
    parts.append(atr(bars, cfg.atr_window).rename("atr"))
    parts.append(kama(c, *cfg.kama).rename("kama"))
    parts.append(supertrend(bars, *cfg.supertrend))
    parts.append(ichimoku(bars, *cfg.ichimoku))
    f = pd.concat(parts, axis=1)
    f["atr_pct"] = f["atr"] / f["close"]
    return f


def _days_since_change(s: pd.Series) -> int | None:
    s = s.dropna()
    if s.empty:
        return None
    changed = s.ne(s.shift())
    last_change = changed[changed].index[-1]
    return int(len(s.loc[last_change:]) - 1)


def snapshot(f: pd.DataFrame) -> dict:
    """Latest-bar values and categorical states (what the LLM reads)."""
    r = f.iloc[-1]
    close = r["close"]
    st: dict = {}
    for col in [c for c in f.columns if c.startswith("sma_")]:
        st[f"close_above_{col}"] = None if pd.isna(r[col]) else bool(close > r[col])
    if {"sma_50", "sma_200"} <= set(f.columns) and not pd.isna(r["sma_200"]):
        st["sma50_above_sma200"] = bool(r["sma_50"] > r["sma_200"])
    rs = r["rsi"]
    st["rsi_zone"] = None if pd.isna(rs) else ("oversold" if rs < 30 else "overbought" if rs > 70 else "neutral")
    h = f["macd_hist"]
    st["macd_hist_positive"] = None if pd.isna(r["macd_hist"]) else bool(r["macd_hist"] > 0)
    cross = (np.sign(h) != np.sign(h.shift(1))) & h.notna() & h.shift(1).notna()
    st["macd_cross_last_3_bars"] = bool(cross.tail(3).any())
    pb = r["bb_pct_b"]
    st["bollinger_zone"] = (None if pd.isna(pb) else "below_lower" if pb < 0 else "lower_half" if pb < 0.5
                            else "upper_half" if pb <= 1 else "above_upper")
    st["supertrend_direction"] = None if pd.isna(r["st_dir"]) else ("up" if r["st_dir"] == 1 else "down")
    st["supertrend_days_since_flip"] = _days_since_change(f["st_dir"])
    st["close_above_kama"] = None if pd.isna(r["kama"]) else bool(close > r["kama"])
    kslope = f["kama"].diff(5).iloc[-1]
    st["kama_slope_5d"] = None if pd.isna(kslope) else ("up" if kslope > 0 else "down" if kslope < 0 else "flat")
    if not (pd.isna(r["ich_span_a"]) or pd.isna(r["ich_span_b"])):
        top, bot = max(r["ich_span_a"], r["ich_span_b"]), min(r["ich_span_a"], r["ich_span_b"])
        st["ichimoku_price_vs_cloud"] = "above" if close > top else "below" if close < bot else "inside"
        st["ichimoku_cloud_color"] = "bullish" if r["ich_span_a"] > r["ich_span_b"] else "bearish"
    else:
        st["ichimoku_price_vs_cloud"] = st["ichimoku_cloud_color"] = None
    st["ichimoku_tenkan_above_kijun"] = None if pd.isna(r["ich_kijun"]) else bool(r["ich_tenkan"] > r["ich_kijun"])
    st["ichimoku_close_above_chikou_ref"] = None if pd.isna(r["ich_chikou_ref"]) else bool(close > r["ich_chikou_ref"])
    values = {k: r[k] for k in f.columns if k not in ("open", "high", "low", "volume")}
    return {"date": f.index[-1], "values": values, "states": st}


# ---------------------------------------------------------------- tool
class CalculateIndicatorsParams(BaseModel):
    ticker: str = Field(description="BIST ticker from the 30-stock universe, e.g. THYAO")
    as_of: date | None = Field(default=None, description="Analysis date (YYYY-MM-DD). Default: last available trading day. Nothing after it is used.")
    config: IndicatorConfig | None = Field(default=None, description="Optional indicator parameters; defaults are standard.")
    tail_rows: int = Field(default=0, ge=0, le=30, description="Also return the last N rows of close/rsi/macd_hist/bb_pct_b/st_dir (0 = snapshot only).")


@tool("calculate_indicators", CalculateIndicatorsParams,
      "SMA/EMA/RSI/MACD/Bollinger/ATR/KAMA/Supertrend/Ichimoku values and categorical states for one stock at as_of (dividend-adjusted prices).")
def calculate_indicators(p: CalculateIndicatorsParams):
    t, _ = store.resolve_ticker(p.ticker)
    as_of, w = store.resolve_as_of(p.as_of)
    bars = store.stock_bars(t, as_of)
    w += store.staleness_warnings(bars, as_of, t)
    f = indicator_frame(bars, p.config)
    snap = snapshot(f)
    if f["sma_200"].isna().iloc[-1] if "sma_200" in f else False:
        w.append(warn("SHORT_HISTORY", f"{t}: fewer than 200 bars; long-window indicators are null"))
    n_zero = store.zero_volume_days(t, as_of)
    if n_zero:
        w.append(warn("ZERO_VOLUME_DAYS", f"{t}: {n_zero} zero-volume days in history; volume-based reading is unreliable"))
    data = {"ticker": t, "bars_used": len(f), **snap}
    if p.tail_rows:
        cols = ["close", "rsi", "macd_hist", "bb_pct_b", "st_dir"]
        data["tail"] = [{"date": d, **row} for d, row in f[cols].tail(p.tail_rows).to_dict("index").items()]
    return data, w, {"as_of": as_of, "last_bar_date": bars.index.max(), "sources": ["prices_clean.parquet"], "price_basis": "adj_close-scaled OHLC"}
