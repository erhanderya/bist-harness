"""detect_reversal_events (with 1/3/5/10-day reversal strength) and find_support_resistance.

No look-ahead: an event on day t uses only bars <= t; forward returns of an event are reported only for horizons whose
end date is <= as_of (otherwise null and excluded from the summary).
"""
from __future__ import annotations

from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from . import store
from .envelope import tool, warn
from .indicators import indicator_frame

HORIZONS = (1, 3, 5, 10)
EVENT_TYPES = {  # name -> (direction, description)
    "rsi_oversold_exit": ("bullish", "RSI crossed back above 30"),
    "bollinger_lower_reclaim": ("bullish", "close back above the lower Bollinger band"),
    "supertrend_flip_up": ("bullish", "Supertrend flipped to up"),
    "kama_cross_up": ("bullish", "close crossed above KAMA"),
    "macd_cross_up": ("bullish", "MACD histogram turned positive"),
    "ichimoku_tk_cross_up": ("bullish", "Tenkan crossed above Kijun"),
    "ichimoku_cloud_breakout_up": ("bullish", "close broke above the Ichimoku cloud"),
    "rsi_overbought_exit": ("bearish", "RSI crossed back below 70"),
    "bollinger_upper_rejection": ("bearish", "close back below the upper Bollinger band"),
    "supertrend_flip_down": ("bearish", "Supertrend flipped to down"),
    "kama_cross_down": ("bearish", "close crossed below KAMA"),
    "macd_cross_down": ("bearish", "MACD histogram turned negative"),
    "ichimoku_tk_cross_down": ("bearish", "Tenkan crossed below Kijun"),
    "ichimoku_cloud_breakdown": ("bearish", "close broke below the Ichimoku cloud"),
}


def event_flags(f: pd.DataFrame) -> pd.DataFrame:
    c, p = f["close"], f["close"].shift(1)
    cloud_top = f[["ich_span_a", "ich_span_b"]].max(axis=1, skipna=False)
    cloud_bot = f[["ich_span_a", "ich_span_b"]].min(axis=1, skipna=False)
    sh = lambda s: s.shift(1)
    e = pd.DataFrame(index=f.index)
    e["rsi_oversold_exit"] = (sh(f["rsi"]) < 30) & (f["rsi"] >= 30)
    e["bollinger_lower_reclaim"] = (p < sh(f["bb_lower"])) & (c >= f["bb_lower"])
    e["supertrend_flip_up"] = (sh(f["st_dir"]) == -1) & (f["st_dir"] == 1)
    e["kama_cross_up"] = (p <= sh(f["kama"])) & (c > f["kama"])
    e["macd_cross_up"] = (sh(f["macd_hist"]) <= 0) & (f["macd_hist"] > 0)
    e["ichimoku_tk_cross_up"] = (sh(f["ich_tenkan"]) <= sh(f["ich_kijun"])) & (f["ich_tenkan"] > f["ich_kijun"])
    e["ichimoku_cloud_breakout_up"] = (sh(c) <= sh(cloud_top)) & (c > cloud_top)
    e["rsi_overbought_exit"] = (sh(f["rsi"]) > 70) & (f["rsi"] <= 70)
    e["bollinger_upper_rejection"] = (p > sh(f["bb_upper"])) & (c <= f["bb_upper"])
    e["supertrend_flip_down"] = (sh(f["st_dir"]) == 1) & (f["st_dir"] == -1)
    e["kama_cross_down"] = (p >= sh(f["kama"])) & (c < f["kama"])
    e["macd_cross_down"] = (sh(f["macd_hist"]) >= 0) & (f["macd_hist"] < 0)
    e["ichimoku_tk_cross_down"] = (sh(f["ich_tenkan"]) >= sh(f["ich_kijun"])) & (f["ich_tenkan"] < f["ich_kijun"])
    e["ichimoku_cloud_breakdown"] = (sh(c) >= sh(cloud_bot)) & (c < cloud_bot)
    return e.fillna(False).astype(bool)


def apply_cooldown(flag: pd.Series, bars: int) -> pd.Series:
    """Keep an event only if the same type did not fire in the previous `bars` bars."""
    out, last = np.zeros(len(flag), bool), -10**9
    for i, v in enumerate(flag.to_numpy()):
        if v and i - last > bars:
            out[i], last = True, i
    return pd.Series(out, index=flag.index)


def forward_returns(close: pd.Series, bench: pd.Series) -> pd.DataFrame:
    """fwd_{h}: stock close-to-close return from the event close; ex_{h}: minus XU100 over the same days. NaN if incomplete."""
    out = pd.DataFrame(index=close.index)
    bench = bench.reindex(close.index).ffill()
    for h in HORIZONS:
        out[f"fwd_{h}"] = close.shift(-h) / close - 1
        out[f"ex_{h}"] = out[f"fwd_{h}"] - (bench.shift(-h) / bench - 1)
    return out


class DetectReversalParams(BaseModel):
    ticker: str = Field(description="BIST ticker, e.g. THYAO")
    as_of: date | None = Field(default=None, description="Analysis date; nothing after it is used.")
    direction: Literal["bullish", "bearish", "both"] = Field(default="bullish", description="Which kind of reversal events to detect.")
    event_types: list[str] | None = Field(default=None, description=f"Subset of event types; default all for the direction. Valid: {', '.join(EVENT_TYPES)}")
    lookback_days: int = Field(default=1260, ge=60, le=3000, description="Trading days of history used for the strength statistics (~5 years default).")
    recent_days: int = Field(default=10, ge=1, le=60, description="Events within this many trading days of as_of are listed as 'recent'.")
    cooldown_days: int = Field(default=5, ge=0, le=30, description="Same-type events within this many bars of a previous one are dropped.")


@tool("detect_reversal_events", DetectReversalParams,
      "Timestamped technical reversal events (RSI/Bollinger/Supertrend/KAMA/MACD/Ichimoku) with 1/3/5/10-day forward return strength vs. history, completed horizons only.")
def detect_reversal_events(p: DetectReversalParams):
    t, _ = store.resolve_ticker(p.ticker)
    as_of, w = store.resolve_as_of(p.as_of)
    bars = store.stock_bars(t, as_of)
    w += store.staleness_warnings(bars, as_of, t)
    types = [k for k, (d, _) in EVENT_TYPES.items() if p.direction == "both" or d == p.direction]
    if p.event_types:
        bad = [x for x in p.event_types if x not in EVENT_TYPES]
        if bad:
            from .envelope import ToolError
            raise ToolError("UNKNOWN_EVENT_TYPE", f"Unknown event types {bad}. Valid: {', '.join(EVENT_TYPES)}")
        types = [x for x in p.event_types]
    f = indicator_frame(bars)
    flags = event_flags(f)[types].apply(lambda s: apply_cooldown(s, p.cooldown_days))
    bench = store.index_bars(as_of)["close"]
    fwd = forward_returns(f["close"], bench)
    lb = f.index[-p.lookback_days:] if len(f) > p.lookback_days else f.index
    summary = {}
    for ty in types:
        idx = flags.index[flags[ty]].intersection(lb)
        row = {"direction": EVENT_TYPES[ty][0], "description": EVENT_TYPES[ty][1], "count": int(len(idx))}
        for h in HORIZONS:
            r = fwd.loc[idx, f"fwd_{h}"].dropna()
            x = fwd.loc[idx, f"ex_{h}"].dropna()
            row[f"h{h}"] = {"n": int(len(r)), "mean": r.mean() if len(r) else None, "median": r.median() if len(r) else None,
                            "hit_rate": float((r > 0).mean()) if len(r) else None, "mean_excess_vs_xu100": x.mean() if len(x) else None}
        summary[ty] = row
    recent_idx = f.index[-p.recent_days:]
    recent = []
    for ty in types:
        for d in flags.index[flags[ty]].intersection(recent_idx):
            recent.append({"date": d, "type": ty, "direction": EVENT_TYPES[ty][0], "close": f.loc[d, "close"],
                           "fwd_returns": {f"{h}d": fwd.loc[d, f"fwd_{h}"] for h in HORIZONS}})
    recent.sort(key=lambda x: x["date"])
    if len(f) < 60:
        w.append(warn("SHORT_HISTORY", f"{t}: only {len(f)} bars; statistics are unreliable"))
    low_n = [k for k, v in summary.items() if 0 < v["count"] < 5]
    if low_n:
        w.append(warn("SMALL_SAMPLE", f"Fewer than 5 historical occurrences for: {', '.join(low_n)}; statistics are anecdotal"))
    data = {"ticker": t, "lookback_bars": int(len(lb)), "entry_convention": "forward returns measured from the event-day close (signal known at close); a tradable backtest must enter at the next open",
            "recent_events": recent, "history_summary": summary}
    return data, w, {"as_of": as_of, "last_bar_date": bars.index.max(), "sources": ["prices_clean.parquet", "index_clean.parquet"]}


# ------------------------------------------------------------------ support / resistance
def pivots(df: pd.DataFrame, k: int) -> pd.DataFrame:
    """Confirmed fractal pivots: a high/low that is the extreme of the surrounding 2k+1 bars. Needs k later bars, so the
    most recent k bars can never be a pivot (no look-ahead)."""
    hi, lo = df["high"].to_numpy(), df["low"].to_numpy()
    rows = []
    for i in range(k, len(df) - k):
        if hi[i] == hi[i - k:i + k + 1].max():
            rows.append((df.index[i], hi[i], "high"))
        if lo[i] == lo[i - k:i + k + 1].min():
            rows.append((df.index[i], lo[i], "low"))
    return pd.DataFrame(rows, columns=["date", "price", "kind"])


def cluster_levels(pv: pd.DataFrame, tol: float) -> list[dict]:
    levels: list[dict] = []
    for r in pv.sort_values("price").itertuples():
        if levels and r.price <= levels[-1]["_min"] * (1 + tol):
            L = levels[-1]
            L["prices"].append(r.price)
            L["dates"].append(r.date)
        else:
            levels.append({"_min": r.price, "prices": [r.price], "dates": [r.date]})
    return [{"level": float(np.mean(L["prices"])), "touches": len(L["prices"]), "last_touch": max(L["dates"]),
             "first_touch": min(L["dates"])} for L in levels]


class FindSRParams(BaseModel):
    ticker: str = Field(description="BIST ticker, e.g. THYAO")
    as_of: date | None = Field(default=None, description="Analysis date; nothing after it is used.")
    lookback_days: int = Field(default=500, ge=60, le=2000, description="Trading days of history scanned for pivots.")
    tolerance_pct: float = Field(default=1.5, gt=0, le=10, description="Pivots within this percent of each other form one level.")
    pivot_window: int = Field(default=5, ge=2, le=15, description="Bars on each side that confirm a pivot.")
    max_levels: int = Field(default=3, ge=1, le=8, description="Supports and resistances returned (nearest to price).")
    min_touches: int = Field(default=2, ge=1, le=10, description="Minimum pivots for a level.")


@tool("find_support_resistance", FindSRParams,
      "Support/resistance levels from confirmed pivots: price zone, touch count, strength, distance from last close.")
def find_support_resistance(p: FindSRParams):
    t, _ = store.resolve_ticker(p.ticker)
    as_of, w = store.resolve_as_of(p.as_of)
    bars = store.stock_bars(t, as_of)
    w += store.staleness_warnings(bars, as_of, t)
    df = bars.tail(p.lookback_days)
    close = float(df["close"].iloc[-1])
    levels = [L for L in cluster_levels(pivots(df, p.pivot_window), p.tolerance_pct / 100) if L["touches"] >= p.min_touches]
    for L in levels:
        L["strength"] = "strong" if L["touches"] >= 5 else "moderate" if L["touches"] >= 3 else "weak"
        L["distance_pct"] = L["level"] / close - 1
        L["zone"] = [L["level"] * (1 - p.tolerance_pct / 200), L["level"] * (1 + p.tolerance_pct / 200)]
    sup = sorted([L for L in levels if L["level"] < close], key=lambda L: -L["level"])[:p.max_levels]
    res = sorted([L for L in levels if L["level"] >= close], key=lambda L: L["level"])[:p.max_levels]
    if not levels:
        w.append(warn("NO_LEVELS", f"{t}: no level with >= {p.min_touches} touches in the lookback window"))
    data = {"ticker": t, "last_close": close, "supports": sup, "resistances": res, "bars_scanned": len(df)}
    return data, w, {"as_of": as_of, "last_bar_date": bars.index.max(), "sources": ["prices_clean.parquet"]}
