"""Point-in-time calendar for fundamentals.

For every (ticker, fiscal year, quarter) we keep the FIRST 'Finansal Rapor' publication timestamp (corrections /
re-issues are recorded but never move the point-in-time date earlier or later), and convert it to the first
trading day on which the information can be reflected in prices:

    published on a trading day BEFORE the open (< 09:40 Istanbul)  -> that day
    otherwise (intraday, after close, weekend, holiday)           -> next trading day

Quality flags: suspect_lag (> 100 days after period end: late filing, pre-listing back-fill, restatement),
n_notifications, corrected (DUZELTILEN/DUZENLENEN exist).
Output: data/processed/fundamental_calendar.parquet
"""
import pandas as pd

from .paths import PROCESSED

OPEN_CUTOFF = pd.Timedelta(hours=9, minutes=40)


def next_or_same_trading_day(ts: pd.Timestamp, days: pd.DatetimeIndex) -> pd.Timestamp:
    d = ts.normalize()
    pos = days.searchsorted(d)
    on_trading_day = pos < len(days) and days[pos] == d
    if on_trading_day and (ts - d) < OPEN_CUTOFF:
        return days[pos]
    pos = days.searchsorted(d, side="right")  # first trading day strictly after d
    return days[pos] if pos < len(days) else pd.NaT


def build() -> pd.DataFrame:
    k = pd.read_parquet(PROCESSED / "kap_fr_disclosures.parquet")
    fr = k[k["subject"].fillna("").str.startswith("Finansal Rapor")].copy()
    fr["year"] = fr["year"].astype("Int64")
    fr["quarter"] = fr["period"].astype("Int64")
    g = (fr.sort_values("publish_ts").groupby(["ticker", "year", "quarter"])
         .agg(first_pub_ts=("publish_ts", "min"), last_pub_ts=("publish_ts", "max"),
              n_notifications=("publish_ts", "size"),
              corrected=("modify_status", lambda s: bool(s.notna().any()))).reset_index())
    days = pd.DatetimeIndex(sorted(pd.read_parquet(PROCESSED / "index_clean.parquet")["date"].unique()))
    g["effective_trade_date"] = g["first_pub_ts"].apply(lambda t: next_or_same_trading_day(t, days))
    qe = pd.to_datetime(dict(year=g["year"].astype(int), month=g["quarter"].astype(int) * 3, day=1)) + pd.offsets.MonthEnd(0)
    g["period_end"] = qe
    g["lag_days"] = (g["first_pub_ts"] - qe).dt.days
    g["suspect_lag"] = g["lag_days"] > 100
    g["after_close_or_weekend"] = ((g["first_pub_ts"].dt.hour * 60 + g["first_pub_ts"].dt.minute) >= 18 * 60) | \
                                  (g["first_pub_ts"].dt.dayofweek >= 5)
    return g


if __name__ == "__main__":
    g = build()
    g.to_parquet(PROCESSED / "fundamental_calendar.parquet", index=False)
    print("rows", len(g), "| tickers", g["ticker"].nunique(), "| suspect_lag", int(g["suspect_lag"].sum()),
          "| corrected", int(g["corrected"].sum()), "| after-close/weekend share", round(float(g["after_close_or_weekend"].mean()), 3),
          "| unresolved effective date", int(g["effective_trade_date"].isna().sum()))
    print(g.loc[g["ticker"] == "BIMAS"].tail(3)[["year", "quarter", "first_pub_ts", "effective_trade_date"]].to_string(index=False))
