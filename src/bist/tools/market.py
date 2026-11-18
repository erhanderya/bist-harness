"""get_stock_history / get_index_history: compact, as_of-safe price windows with summary statistics."""
from __future__ import annotations

from datetime import date

import pandas as pd
from pydantic import BaseModel, Field

from . import store
from .envelope import ToolError, tool, warn

INDEX_NAMES = {"XU100": "XU100.IS", "BIST100": "XU100.IS"}


def _window(bars: pd.DataFrame, start, end, as_of: pd.Timestamp) -> pd.DataFrame:
    hi = min(pd.Timestamp(end), as_of) if end else as_of
    w = bars[bars.index <= hi]
    if start:
        w = w[w.index >= pd.Timestamp(start)]
    return w


def _summary(w: pd.DataFrame) -> dict:
    c = w["adj_close"]
    return {
        "n_rows": len(w), "first_date": w.index.min(), "last_date": w.index.max(),
        "last_close": w["close"].iloc[-1], "period_return": (c.iloc[-1] / c.iloc[0] - 1) if len(c) > 1 else None,
        "high": w["high"].max(), "low": w["low"].min(),
        "avg_volume": w.loc[~w["volume_missing"], "volume"].mean() if w["volume_missing"].ne(True).any() else None,
        "zero_volume_days": int(w["volume_missing"].sum()),
    }


def _rows(w: pd.DataFrame, max_rows: int) -> list[dict]:
    cols = ["open", "high", "low", "close", "adj_close", "volume"]
    return [{"date": d, **r} for d, r in w[cols].tail(max_rows).to_dict("index").items()]


class GetStockHistoryParams(BaseModel):
    ticker: str = Field(description="BIST ticker from the 30-stock universe, e.g. THYAO")
    start: date | None = Field(default=None, description="First date (YYYY-MM-DD). Default: 60 trading days before end.")
    end: date | None = Field(default=None, description="Last date. Default and maximum: as_of.")
    as_of: date | None = Field(default=None, description="Analysis date; nothing after it is returned. Default: last trading day.")
    max_rows: int = Field(default=30, ge=1, le=120, description="Most recent rows to return (summary covers the whole window).")


@tool("get_stock_history", GetStockHistoryParams,
      "Daily OHLCV (split-corrected, raw + adj_close) for one stock, last max_rows rows plus window summary and data-quality metadata.")
def get_stock_history(p: GetStockHistoryParams):
    t, _ = store.resolve_ticker(p.ticker)
    as_of, w = store.resolve_as_of(p.as_of)
    bars = store.stock_bars(t, as_of, adjusted=False)
    w += store.staleness_warnings(bars, as_of, t)
    start = p.start or (bars.index[-60] if len(bars) > 60 else bars.index[0])
    if p.end and pd.Timestamp(p.end) < pd.Timestamp(start):
        raise ToolError("INVALID_RANGE", f"end {p.end} is before start {start}")
    win = _window(bars, start, p.end, as_of)
    if win.empty:
        raise ToolError("NO_DATA", f"{t}: no bars between {pd.Timestamp(start).date()} and {(p.end or as_of.date())}")
    if win["volume_missing"].any():
        w.append(warn("ZERO_VOLUME_DAYS", f"{t}: {int(win['volume_missing'].sum())} zero-volume days in the window"))
    big = win["ret_1d"].abs() > 0.25
    if big.any():
        w.append(warn("EXTREME_MOVE", f"{t}: {int(big.sum())} daily moves above 25% in the window (possible unadjusted corporate action): "
                      + ", ".join(str(d.date()) for d in win.index[big][:3])))
    data = {"ticker": t, "summary": _summary(win), "rows": _rows(win, p.max_rows)}
    return data, w, {"as_of": as_of, "last_bar_date": bars.index.max(), "sources": ["prices_clean.parquet (Yahoo, split-corrected)"]}


class GetIndexHistoryParams(BaseModel):
    index: str = Field(default="XU100", description="Benchmark index. Only XU100 (BIST 100) is available.")
    start: date | None = Field(default=None, description="First date (YYYY-MM-DD). Default: 60 trading days before end.")
    end: date | None = Field(default=None, description="Last date. Default and maximum: as_of.")
    as_of: date | None = Field(default=None, description="Analysis date; nothing after it is returned.")
    max_rows: int = Field(default=30, ge=1, le=120, description="Most recent rows to return.")


@tool("get_index_history", GetIndexHistoryParams,
      "Daily OHLCV of the BIST 100 benchmark (XU100), last max_rows rows plus window summary.")
def get_index_history(p: GetIndexHistoryParams):
    if p.index.strip().upper() not in INDEX_NAMES:
        raise ToolError("UNKNOWN_INDEX", f"Index '{p.index}' is not available. Available: XU100")
    as_of, w = store.resolve_as_of(p.as_of)
    bars = store.index_bars(as_of)
    w += store.staleness_warnings(bars, as_of, "XU100")
    start = p.start or (bars.index[-60] if len(bars) > 60 else bars.index[0])
    win = _window(bars, start, p.end, as_of)
    if win.empty:
        raise ToolError("NO_DATA", f"XU100: no bars between {pd.Timestamp(start).date()} and {(p.end or as_of.date())}")
    win = win.assign(volume_missing=win["volume_missing"].fillna(False))
    data = {"index": "XU100", "summary": _summary(win), "rows": _rows(win, p.max_rows)}
    return data, w, {"as_of": as_of, "last_bar_date": bars.index.max(), "sources": ["index_clean.parquet (Yahoo)"]}
