"""generate_strategy_variants (A-E) and run_backtest.

Timing / honesty rules
- Signal is formed with information known at the CLOSE of day t; entry is the OPEN of t+1 (signal shift), exit is the close
  of day t+hold_days. Trades whose exit is after the end date are dropped (no partial trades).
- Costs: commission + slippage per side (default 10 + 5 bps). Zero-volume entry days are skipped (not tradable).
- Fundamentals: only quarters whose effective_trade_date <= t. Macro: last observation strictly before t.
- One open position per ticker; portfolio: equal slots of 1/max_concurrent, first-come by entry date, cash earns 0.
- Variant E (news/speech) needs a historical, timestamped news/speech dataset that does not exist yet -> refused, not faked.
- Results are split train 60% / validation 20% / test 20% (by signal date) and by year; few signals are flagged.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from . import store
from .envelope import ToolError, tool, warn
from .events import EVENT_TYPES, apply_cooldown, event_flags
from .indicators import indicator_frame

DEFAULT_TRIGGERS = ["rsi_oversold_exit", "bollinger_lower_reclaim", "supertrend_flip_up", "macd_cross_up", "kama_cross_up"]
MIN_TRADES_WARN = 30
MIN_TEST_TRADES = 10


class SectorFilter(BaseModel):
    horizon_days: int = Field(default=10, ge=1, le=60)
    min_lag_score: float = Field(default=0.5, description="Stock must lag the peer-group median by at least this many peer standard deviations.")
    require_strong_sector: bool = Field(default=True, description="Peer-group median return must beat XU100 and be positive.")


class FundFilter(BaseModel):
    min_roe_ttm: float | None = Field(default=0.0, description="Minimum trailing ROE (all kinds).")
    max_net_debt_ebitda: float | None = Field(default=4.0, description="Maximum net debt / EBITDA (industrial only; null values pass).")
    require_roe_not_declining: bool = Field(default=False, description="ROE must not be lower than in the previous public quarter.")


class MacroFilter(BaseModel):
    max_vix: float | None = Field(default=30.0, description="Block entries when the previous-day VIX is above this.")
    max_usdtry_20d_change: float | None = Field(default=0.15, description="Block entries when USD/TRY rose more than this over 20 days (hard-risk regime).")


class StrategySpec(BaseModel):
    name: str = "custom"
    trigger_events: list[str] = Field(default_factory=lambda: list(DEFAULT_TRIGGERS), description=f"Bullish events that trigger an entry. Valid: {', '.join(k for k, v in EVENT_TYPES.items() if v[0] == 'bullish')}")
    sector: SectorFilter | None = None
    fundamental: FundFilter | None = None
    macro: MacroFilter | None = None
    hold_days: int = Field(default=5, ge=1, le=60, description="Trading days held after the t+1 open entry.")


VARIANT_DESCRIPTIONS = {
    "A": "Technical only: bullish reversal-event triggers",
    "B": "Technical + sector relative: A + stock lags a strong peer group",
    "C": "Technical + sector + fundamental: B + point-in-time financial quality filter",
    "D": "Full structured: C + macro regime not hard-risk",
    "E": "Full contextual: D + verified news/speech context (NOT AVAILABLE: no historical timestamped news/speech dataset)",
}


def variant_spec(letter: str, hold_days: int = 5) -> StrategySpec:
    letter = letter.upper()
    if letter == "E":
        raise ToolError("LAYER_UNAVAILABLE", "Variant E needs historical timestamped news/speech data, which is not available; it cannot be backtested honestly. Use A-D.")
    return StrategySpec(name=f"variant_{letter}", hold_days=hold_days,
                        sector=SectorFilter() if letter in "BCD" else None,
                        fundamental=FundFilter() if letter in "CD" else None,
                        macro=MacroFilter() if letter == "D" else None)


class VariantsParams(BaseModel):
    hold_days: int = Field(default=5, ge=1, le=60, description="Holding period applied to all variants.")


@tool("generate_strategy_variants", VariantsParams,
      "The permitted strategy variants A-E (technical only -> full contextual) as machine-readable specs for run_backtest; E is listed but flagged unavailable.")
def generate_strategy_variants(p: VariantsParams):
    out = []
    for L in "ABCDE":
        avail = L != "E"
        out.append({"variant": L, "description": VARIANT_DESCRIPTIONS[L], "backtestable": avail,
                    "spec": variant_spec(L, p.hold_days).model_dump(mode="json") if avail else None})
    return {"variants": out}, [], {"as_of": store.data_last_date(), "sources": ["strategy definitions (project spec section 29)"]}


# ------------------------------------------------------------------ cached features
@lru_cache(maxsize=3)
def _features(as_of: pd.Timestamp) -> dict:
    """Per ticker: indicator frame (adjusted OHLC) + cooldown-filtered event flags, using bars <= as_of; peer return matrices."""
    frames, flags = {}, {}
    for t in store.tickers():
        b = store.stock_bars(t, as_of)
        f = indicator_frame(b)
        f["volume_missing"] = store.stock_bars(t, as_of, adjusted=False)["volume_missing"].reindex(f.index).fillna(False).astype(bool)
        frames[t] = f
        fl = event_flags(f)
        flags[t] = fl.apply(lambda s: apply_cooldown(s, 5))
    close = pd.DataFrame({t: frames[t]["close"] for t in frames})
    return {"frames": frames, "flags": flags, "close": close}


def _sector_cond(feat: dict, spec: SectorFilter, xu: pd.Series) -> dict[str, pd.Series]:
    close = feat["close"]
    ret = close / close.shift(spec.horizon_days) - 1
    xu_ret = (xu / xu.shift(spec.horizon_days) - 1).reindex(close.index)
    u = store.universe()
    out = {}
    for g, members in u.groupby("peer_group")["ticker"]:
        members = list(members)
        if len(members) < 3:
            for t in members:
                out[t] = pd.Series(False, index=close.index)
            continue
        r = ret[members]
        med, sd = r.median(axis=1), r.std(axis=1, ddof=0)
        strong = (med > xu_ret) & (med > 0) if spec.require_strong_sector else pd.Series(True, index=close.index)
        for t in members:
            lag = (med - r[t]) / sd.where(sd > 0)
            out[t] = ((lag >= spec.min_lag_score) & strong).fillna(False)
    return out


def _fund_cond(t: str, idx: pd.DatetimeIndex, spec: FundFilter) -> pd.Series:
    m = store.fund_metrics()
    m = m[m["ticker"] == t]
    cal = store.fund_calendar()
    cal = cal[cal["ticker"] == t][["year", "quarter", "effective_trade_date"]]
    j = m.merge(cal, on=["year", "quarter"], how="inner").dropna(subset=["effective_trade_date"]).sort_values("effective_trade_date")
    if j.empty:
        return pd.Series(False, index=idx)
    j["roe_prev"] = j["roe_ttm"].shift(1)
    cols = ["effective_trade_date", "roe_ttm", "roe_prev"] + (["net_debt_ebitda"] if "net_debt_ebitda" in j else [])
    left = pd.DataFrame({"date": pd.DatetimeIndex(idx).astype("datetime64[ns]")})
    j = j.assign(effective_trade_date=j["effective_trade_date"].astype("datetime64[ns]"))
    a = pd.merge_asof(left, j[cols], left_on="date", right_on="effective_trade_date", direction="backward")
    ok = pd.Series(True, index=range(len(a)))
    if spec.min_roe_ttm is not None:
        ok &= a["roe_ttm"] > spec.min_roe_ttm
    if spec.max_net_debt_ebitda is not None and "net_debt_ebitda" in a:
        ok &= (a["net_debt_ebitda"].isna() | (a["net_debt_ebitda"] < spec.max_net_debt_ebitda))
    if spec.require_roe_not_declining:
        ok &= a["roe_ttm"] >= a["roe_prev"]
    ok &= a["roe_ttm"].notna()
    return pd.Series(ok.fillna(False).to_numpy(), index=idx)


def _macro_cond(idx: pd.DatetimeIndex, spec: MacroFilter) -> pd.Series:
    m = store.macro()
    ok = pd.Series(True, index=idx)
    left = pd.DataFrame({"date": pd.DatetimeIndex(idx).astype("datetime64[ns]")})
    for series, thr, pct in (("vix", spec.max_vix, False), ("usdtry", spec.max_usdtry_20d_change, True)):
        if thr is None:
            continue
        s = m[m["series"] == series].sort_values("date")[["date", "value"]]
        if pct:
            s = s.assign(value=s["value"] / s["value"].shift(20) - 1)
        s = s.assign(date=s["date"].astype("datetime64[ns]"))
        a = pd.merge_asof(left, s.dropna(), on="date", direction="backward", allow_exact_matches=False)  # strictly earlier obs
        ok &= pd.Series((a["value"] <= thr).fillna(False).to_numpy(), index=idx)
    return ok


# ------------------------------------------------------------------ simulation
def _trades(t: str, f: pd.DataFrame, trig: pd.Series, spec: StrategySpec, end: pd.Timestamp, start: pd.Timestamp,
            cost: float, xu_open: pd.Series, xu_close: pd.Series) -> tuple[list[dict], int]:
    idx = f.index
    o, c = f["open"].to_numpy(), f["close"].to_numpy()
    vm = f["volume_missing"].to_numpy()
    sig = np.flatnonzero(trig.reindex(idx).fillna(False).to_numpy() & (idx >= start) & (idx <= end))
    trades, busy_until, skipped = [], -1, 0
    for i in sig:
        e, x = i + 1, i + spec.hold_days
        if e <= busy_until or x >= len(idx) or idx[x] > end:
            continue
        if vm[e] or not o[e] > 0:
            skipped += 1
            continue
        busy_until = x
        gross = c[x] / o[e] - 1
        net = c[x] * (1 - cost) / (o[e] * (1 + cost)) - 1
        xo = xu_open.get(idx[e], np.nan)
        bench = xu_close.get(idx[x], np.nan) / xo - 1 if xo and not np.isnan(xo) else np.nan
        trades.append({"ticker": t, "signal_date": idx[i], "entry_date": idx[e], "exit_date": idx[x], "gross_return": gross,
                       "net_return": net, "xu100_return": bench, "excess_vs_xu100": net - bench,
                       "_e": e, "_x": x})
    return trades, skipped


def _portfolio(trades: list[dict], feats: dict, calendar: pd.DatetimeIndex, cost: float, max_concurrent: int) -> tuple[pd.Series, list[dict], int]:
    """Equal 1/max_concurrent slots, first-come by (entry_date, ticker). Returns daily portfolio return series."""
    accepted, open_exit, rejected = [], [], 0
    for tr in sorted(trades, key=lambda x: (x["entry_date"], x["ticker"])):
        open_exit = [d for d in open_exit if d >= tr["entry_date"]]
        if len(open_exit) >= max_concurrent:
            rejected += 1
            continue
        open_exit.append(tr["exit_date"])
        accepted.append(tr)
    daily = pd.Series(0.0, index=calendar)
    npos = pd.Series(0, index=calendar)
    for tr in accepted:
        f = feats["frames"][tr["ticker"]]
        o, c = f["open"].to_numpy(), f["close"].to_numpy()
        e, x = tr["_e"], tr["_x"]
        for k in range(e, x + 1):
            if k == e:
                r = c[k] / (o[k] * (1 + cost)) - 1
                if x == e:
                    r = c[k] * (1 - cost) / (o[k] * (1 + cost)) - 1
            elif k == x:
                r = c[k] / c[k - 1] * (1 - cost) - 1
            else:
                r = c[k] / c[k - 1] - 1
            d = f.index[k]
            if d in daily.index:
                daily[d] += r / max_concurrent
                npos[d] += 1
    return daily, accepted, rejected


def _perf(r: pd.Series) -> dict:
    eq = (1 + r).cumprod()
    sd = r.std(ddof=1)
    return {"total_return": float(eq.iloc[-1] - 1) if len(eq) else None,
            "sharpe_annualized_rf0": float(r.mean() / sd * np.sqrt(252)) if sd and sd > 0 else None,
            "max_drawdown": float((eq / eq.cummax() - 1).min()) if len(eq) else None}


def _stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"n_trades": 0}
    return {"n_trades": int(len(df)), "mean_net_return": float(df["net_return"].mean()), "median_net_return": float(df["net_return"].median()),
            "win_rate": float((df["net_return"] > 0).mean()), "mean_excess_vs_xu100": float(df["excess_vs_xu100"].mean(skipna=True))}


class RunBacktestParams(BaseModel):
    variant: Literal["A", "B", "C", "D", "E"] | None = Field(default=None, description="Use a predefined variant (see generate_strategy_variants). Provide either variant or spec.")
    spec: StrategySpec | None = Field(default=None, description="Custom strategy spec; provide either variant or spec.")
    hold_days: int = Field(default=5, ge=1, le=60, description="Holding days when `variant` is used.")
    tickers: list[str] | None = Field(default=None, description="Universe subset; default all 30 stocks.")
    start: date | None = Field(default=None, description="First signal date. Default 2017-01-01.")
    end: date | None = Field(default=None, description="Last date (exit must happen on or before it). Default and maximum: as_of.")
    as_of: date | None = Field(default=None, description="Analysis date; nothing after it is used.")
    cost_bps_per_side: float = Field(default=10.0, ge=0, le=200, description="Commission/tax cost per side in basis points.")
    slippage_bps_per_side: float = Field(default=5.0, ge=0, le=200, description="Slippage per side in basis points.")
    max_concurrent: int = Field(default=5, ge=1, le=30, description="Portfolio slots (each 1/max_concurrent of capital).")


@tool("run_backtest", RunBacktestParams,
      "Event-based backtest of a strategy variant/spec on the universe: signal shift (entry at next open), costs, trade log, per-period/per-year breakdown, portfolio Sharpe/max drawdown/exposure, XU100 and equal-weight benchmarks, flags for few signals and instability.")
def run_backtest(p: RunBacktestParams):
    if (p.variant is None) == (p.spec is None):
        raise ToolError("INVALID_PARAMS", "provide exactly one of `variant` or `spec`")
    spec = variant_spec(p.variant, p.hold_days) if p.variant else p.spec
    bad = [e for e in spec.trigger_events if e not in EVENT_TYPES or EVENT_TYPES[e][0] != "bullish"]
    if bad or not spec.trigger_events:
        raise ToolError("UNKNOWN_EVENT_TYPE", f"trigger_events must be a non-empty subset of the bullish events; invalid: {bad}")
    as_of, w = store.resolve_as_of(p.as_of)
    universe = [store.resolve_ticker(t)[0] for t in p.tickers] if p.tickers else store.tickers()
    start = pd.Timestamp(p.start) if p.start else pd.Timestamp("2017-01-01")
    end = min(pd.Timestamp(p.end), as_of) if p.end else as_of
    if start >= end:
        raise ToolError("INVALID_RANGE", f"start {start.date()} must be before end {end.date()}")
    feat = _features(as_of)
    ib = store.index_bars(as_of)
    xu_c = ib["close"]
    xu_o = ib["open"].where(ib["open"] > 0, xu_c.shift(1))
    sector = _sector_cond(feat, spec.sector, xu_c) if spec.sector else None
    cost = (p.cost_bps_per_side + p.slippage_bps_per_side) / 1e4
    all_tr, skipped, excluded = [], 0, []
    for t in universe:
        f = feat["frames"][t]
        trig = feat["flags"][t][spec.trigger_events].any(axis=1)
        if sector is not None:
            trig &= sector[t].reindex(f.index).fillna(False)
            if store.universe().set_index("ticker").loc[t, "peer_group"] in set(
                    g for g, n in store.universe().groupby("peer_group").size().items() if n < 3):
                excluded.append(t)
        if spec.fundamental:
            trig &= _fund_cond(t, f.index, spec.fundamental)
        if spec.macro:
            trig &= _macro_cond(f.index, spec.macro)
        tr, sk = _trades(t, f, trig, spec, end, start, cost, xu_o, xu_c)
        all_tr += tr
        skipped += sk
    df = pd.DataFrame(all_tr)
    if df.empty:
        w.append(warn("NO_TRADES", "The strategy produced no trades in the period."))
        data = {"spec": spec.model_dump(mode="json"), "period": [start, end], "n_trades": 0}
        return data, w, {"as_of": as_of, "sources": ["prices_clean.parquet"]}
    df = df.sort_values(["signal_date", "ticker"]).reset_index(drop=True)
    span = (end - start).days
    t1, t2 = start + pd.Timedelta(days=int(span * 0.6)), start + pd.Timedelta(days=int(span * 0.8))
    part = {"train": df[df["signal_date"] < t1], "validation": df[(df["signal_date"] >= t1) & (df["signal_date"] < t2)], "test": df[df["signal_date"] >= t2]}
    by_period = {k: _stats(v) | {"from": v["signal_date"].min() if len(v) else None, "to": v["signal_date"].max() if len(v) else None} for k, v in part.items()}
    by_year = {str(y): _stats(g) for y, g in df.groupby(df["signal_date"].dt.year)}
    cal = xu_c.loc[start:end].index
    daily, accepted, rejected = _portfolio(all_tr, feat, cal, cost, p.max_concurrent)
    perf = _perf(daily)
    perf["exposure_days_pct"] = float((daily != 0).mean())
    perf["trades_taken"], perf["trades_rejected_by_slot_limit"] = len(accepted), rejected
    xu_period = xu_c.loc[start:end]
    ew = feat["close"][universe].loc[start:end].pct_change().mean(axis=1).fillna(0)
    bench = {"xu100_total_return": float(xu_period.iloc[-1] / xu_period.iloc[0] - 1), "equal_weight_universe_total_return": float((1 + ew).prod() - 1)}
    perf["return_minus_xu100"] = perf["total_return"] - bench["xu100_total_return"]
    sc = _stats(df)
    n_test = by_period["test"]["n_trades"]
    if sc["n_trades"] < MIN_TRADES_WARN:
        w.append(warn("FEW_SIGNALS", f"Only {sc['n_trades']} trades (< {MIN_TRADES_WARN}); results are anecdotal."))
    if n_test < MIN_TEST_TRADES:
        w.append(warn("SMALL_TEST_SAMPLE", f"Only {n_test} trades in the out-of-sample test period (< {MIN_TEST_TRADES}); out-of-sample evidence is weak."))
    tr_m, te_m = by_period["train"].get("mean_net_return"), by_period["test"].get("mean_net_return")
    stable = None
    if tr_m is not None and te_m is not None:
        stable = bool(np.sign(tr_m) == np.sign(te_m))
        if not stable:
            w.append(warn("UNSTABLE_OUT_OF_SAMPLE", "Mean net return has a different sign in the train and test periods: the result does not persist out-of-sample."))
    if perf["exposure_days_pct"] < 0.2:
        w.append(warn("LOW_EXPOSURE", "Portfolio is invested on fewer than 20% of days; compare per-trade statistics rather than total return."))
    if excluded:
        w.append(warn("PEER_GROUP_TOO_SMALL", f"Excluded from sector-based entries (peer group < 3): {', '.join(excluded)}"))
    if spec.fundamental:
        w.append(warn("FUNDAMENTAL_FILTER_RATIOS_ONLY", "Fundamental filter uses same-period ratios (ROE, net debt/EBITDA), which are robust to the TMS 29 restatement issue; level-based growth is not used."))
    if skipped:
        w.append(warn("ZERO_VOLUME_ENTRY_SKIPPED", f"{skipped} signals skipped because the entry day had zero volume (not tradable)."))
    log = df.drop(columns=["_e", "_x"]).tail(10)
    data = {
        "spec": spec.model_dump(mode="json"),
        "assumptions": {"signal_shift": "signal at close t, entry at open t+1", "exit": f"close of day t+{spec.hold_days}", "round_trip_cost_bps": 2 * (p.cost_bps_per_side + p.slippage_bps_per_side),
                        "max_concurrent": p.max_concurrent, "one_position_per_ticker": True, "universe_size": len(universe),
                        "benchmark_note": "Cash earns 0% and buy-and-hold benchmarks carry the TRY inflation drift (nominal TL); the like-for-like comparison is signal_level.mean_excess_vs_xu100 (same holding window)."},
        "period": [start, end], "signal_level": sc | {"avg_holding_days": spec.hold_days}, "by_period": by_period, "by_year": by_year,
        "out_of_sample_same_sign": stable, "portfolio": perf, "benchmarks": bench,
        "last_10_trades": [{k: v for k, v in r.items()} for r in log.to_dict("records")], "n_trades_total": int(len(df)),
    }
    return data, w, {"as_of": as_of, "sources": ["prices_clean.parquet", "index_clean.parquet", "fundamental_metrics.parquet", "macro_market_daily.parquet"]}
