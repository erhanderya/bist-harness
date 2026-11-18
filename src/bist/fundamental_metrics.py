"""Quarterly de-cumulation and fundamental metrics (growth / profitability / leverage / liquidity / cash flow).

Input : data/processed/fundamentals_raw.parquet  (Is Yatirim; flow items are YEAR-TO-DATE cumulative)
Output: data/processed/fundamental_metrics.parquet (one row per ticker-quarter, wide)

Rules
- Flow item quarterly value = YTD(q) - YTD(q-1) (q=1: YTD itself); NaN if the previous YTD is missing.
- Balance-sheet periods whose total assets are 0 are treated as MISSING (source gap, e.g. AKBNK 2025Q3).
- Banks (UFRS, AKBNK) and the insurer (TURSG) get their OWN metric set; industrial ratios are NOT applied to them.
- Valuation ratios (P/E, P/B, EV/EBITDA) are NOT here: they need prices + share count and are built at event time.
"""
import numpy as np
import pandas as pd

from .paths import PROCESSED

INSURERS = {"TURSG"}

# item -> code, per kind. (flow=True means YTD cumulative)
IND = {  # industrial, group XI_29
    "revenue": ("3C", True), "gross_profit": ("3D", True), "op_profit": ("3DF", True),
    "net_profit_parent": ("3Z", True), "net_profit": ("3L", True), "da": ("4CAB", True), "da_alt": ("4B", True),
    "ocf": ("4C", True), "capex": ("4CAI", True),
    "total_assets": ("1BL", False), "equity_parent": ("2O", False), "equity": ("2N", False),
    "current_assets": ("1A", False), "current_liab": ("2A", False), "inventories": ("1AF", False),
    "cash": ("1AA", False), "fin_inv": ("1AB", False), "debt_st": ("2AA", False), "debt_lt": ("2BA", False),
    "paid_in_capital": ("2OA", False),
}
BANK = {
    "nii": ("3C", True), "fees": ("3CA", True), "net_profit": ("3Z", True),  # income-statement net profit (NOT 2OV: that one is zero when the balance sheet is empty)
    "total_assets": ("1Z", False), "equity": ("2O", False), "loans": ("1AF", False), "deposits": ("2A", False),
    "paid_in_capital": ("2OA", False),
}
INS = {
    "premiums_written_net": ("3AAA", True), "technical_balance": ("3K", True), "net_profit": ("3Z", True),
    "total_assets": ("1Z", False), "paid_in_capital": ("2MEA", False),
}


def _wide(df: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """ytd/stock values per (year, period) as columns named by item."""
    out = None
    for name, (code, _) in spec.items():
        s = (df[df["item_code"] == code].drop_duplicates(["year", "period"])
             .set_index(["year", "period"])["value"].rename(name))
        out = s.to_frame() if out is None else out.join(s, how="outer")
    out = out.sort_index()
    y0, y1 = out.index.get_level_values(0).min(), out.index.get_level_values(0).max()
    grid = pd.MultiIndex.from_product([range(y0, y1 + 1), [3, 6, 9, 12]], names=["year", "period"])
    return out.reindex(grid)  # continuous quarter grid -> shift()/rolling() below are safe


def _decumulate(w: pd.DataFrame, spec: dict) -> pd.DataFrame:
    q = pd.DataFrame(index=w.index)
    for name, (_, flow) in spec.items():
        if name not in w:
            continue
        if not flow:
            q[name] = w[name]
            continue
        ytd = w[name]
        prev = ytd.groupby(level=0).shift(1)  # previous quarter's YTD within the same year
        is_q1 = w.index.get_level_values(1) == 3
        q[name + "_q"] = np.where(is_q1, ytd, ytd - prev)
    # periods whose balance sheet is empty/zero (source gap, pre-listing) -> stock items are MISSING, not zero
    stock = [n for n, (_, flow) in spec.items() if not flow and n in q]
    empty = q["total_assets"].isna() | (q["total_assets"] == 0)
    q.loc[empty, stock] = np.nan
    return q


def _ttm(q: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        q[c.replace("_q", "_ttm")] = q[c].rolling(4, min_periods=4).sum()
    return q


def _avg_prior(s: pd.Series) -> pd.Series:
    return (s + s.shift(4)) / 2


def _safe_div(a, b):
    return a / b.where(b != 0)


def _industrial(df):
    w = _wide(df, IND)
    q = _decumulate(w, IND)
    q["da_q"] = q["da_q"].fillna(q["da_alt_q"])
    q["ebitda_q"] = q["op_profit_q"] + q["da_q"]
    q["ni_q"] = q["net_profit_parent_q"].fillna(q["net_profit_q"])
    q["eq"] = q["equity_parent"].fillna(q["equity"])
    q = _ttm(q, ["revenue_q", "ebitda_q", "ni_q", "ocf_q", "capex_q", "gross_profit_q"])
    q["gross_margin_q"] = _safe_div(q["gross_profit_q"], q["revenue_q"])
    q["ebitda_margin_q"] = _safe_div(q["ebitda_q"], q["revenue_q"])
    q["net_margin_q"] = _safe_div(q["ni_q"], q["revenue_q"])
    q["roe_ttm"] = _safe_div(q["ni_ttm"], _avg_prior(q["eq"]))
    q["roa_ttm"] = _safe_div(q["ni_ttm"], _avg_prior(q["total_assets"]))
    q["fin_debt"] = q["debt_st"].fillna(0) + q["debt_lt"].fillna(0)
    q["net_debt"] = q["fin_debt"] - q["cash"].fillna(0) - q["fin_inv"].fillna(0)
    q["net_debt_ebitda"] = _safe_div(q["net_debt"], q["ebitda_ttm"])
    q["debt_equity"] = _safe_div(q["fin_debt"], q["eq"])
    q["current_ratio"] = _safe_div(q["current_assets"], q["current_liab"])
    q["quick_ratio"] = _safe_div(q["current_assets"] - q["inventories"].fillna(0), q["current_liab"])
    q["cash_conversion"] = _safe_div(q["ocf_ttm"], q["ni_ttm"])
    for base in ("revenue_q", "ebitda_q", "ni_q"):
        prev = q[base].shift(4)
        q[base.replace("_q", "_yoy")] = np.where(prev > 0, q[base] / prev - 1, np.nan)  # only when prior-year base > 0
        q[base.replace("_q", "_qoq")] = np.where(q[base].shift(1) > 0, q[base] / q[base].shift(1) - 1, np.nan)
    return q


def _bank(df):
    w = _wide(df, BANK)
    q = _decumulate(w, BANK)
    q = _ttm(q, ["nii_q", "fees_q", "net_profit_q"])
    q["roe_ttm"] = _safe_div(q["net_profit_ttm"], _avg_prior(q["equity"]))
    q["roa_ttm"] = _safe_div(q["net_profit_ttm"], _avg_prior(q["total_assets"]))
    q["loan_deposit"] = _safe_div(q["loans"], q["deposits"])
    q["equity_assets"] = _safe_div(q["equity"], q["total_assets"])
    q["nii_assets"] = _safe_div(q["nii_ttm"], q["total_assets"])
    prev = q["net_profit_q"].shift(4)
    q["ni_yoy"] = np.where(prev > 0, q["net_profit_q"] / prev - 1, np.nan)
    return q


def _insurer(df):
    w = _wide(df, INS)
    q = _decumulate(w, INS)
    q = _ttm(q, ["premiums_written_net_q", "technical_balance_q", "net_profit_q"])
    q["roa_ttm"] = _safe_div(q["net_profit_ttm"], _avg_prior(q["total_assets"]))
    prev = q["net_profit_q"].shift(4)
    q["ni_yoy"] = np.where(prev > 0, q["net_profit_q"] / prev - 1, np.nan)
    return q


def build() -> pd.DataFrame:
    raw = pd.read_parquet(PROCESSED / "fundamentals_raw.parquet")
    parts = []
    for tk, df in raw.groupby("ticker"):
        grp = df["group"].iloc[0]
        kind = "insurer" if tk in INSURERS else ("bank" if grp == "UFRS" else "industrial")
        q = {"industrial": _industrial, "bank": _bank, "insurer": _insurer}[kind](df)
        ta = q["total_assets"]
        q = q[ta.notna() & (ta != 0)].copy()  # drop periods with an empty balance sheet (source gap / pre-listing)
        # a real period must be a continuous quarter series for the shift()-based metrics: reindex first
        q.insert(0, "kind", kind)
        q.insert(0, "ticker", tk)
        q = q.reset_index().rename(columns={"period": "month"})
        q["quarter"] = q["month"] // 3
        parts.append(q)
    return pd.concat(parts, ignore_index=True)


if __name__ == "__main__":
    m = build()
    m.to_parquet(PROCESSED / "fundamental_metrics.parquet", index=False)
    print("rows", len(m), "| tickers", m["ticker"].nunique(), "| kinds", m["kind"].value_counts().to_dict())
