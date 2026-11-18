"""Build the analysis-ready price cache from the raw Yahoo cache.

Raw files are never modified. Output: data/processed/prices_clean.parquet,
index_clean.parquet and data/raw/clean_report.json.

Steps
 1. Apply manual corporate-action corrections (data/corrections.csv):
    prices before effective_date divided by factor, volume multiplied.
 2. Drop the current trading day's bar while the market may still be open
    (BIST closes 18:00 Istanbul; cutoff 18:30) -> no partial bars in analysis.
 3. Flag zero-volume days (volume_missing) -- volume indicators must skip them.
 4. Report |return| > 25% days that are not explained by a correction.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .paths import DATA, PROCESSED, RAW

PRICE_COLS = ["open", "high", "low", "close", "adj_close"]
IST = ZoneInfo("Europe/Istanbul")


def apply_corrections(df: pd.DataFrame, corr: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for _, c in corr.iterrows():
        m = (df["symbol"] == c["symbol"]) & (df["date"] < pd.Timestamp(c["effective_date"]))
        df.loc[m, PRICE_COLS] = df.loc[m, PRICE_COLS] / float(c["factor"])
        df.loc[m, "volume"] = df.loc[m, "volume"] * float(c["factor"])
    return df


def drop_partial_bar(df: pd.DataFrame, now: datetime | None = None) -> tuple[pd.DataFrame, str | None]:
    now = now or datetime.now(IST)
    today = pd.Timestamp(now.date())
    if (now.hour, now.minute) < (18, 30) and (df["date"] == today).any():
        return df[df["date"] < today].copy(), str(today.date())
    return df, None


def clean() -> dict:
    corr = pd.read_csv(DATA / "corrections.csv")
    stocks = pd.read_parquet(PROCESSED / "prices_daily.parquet")
    idx = pd.read_parquet(PROCESSED / "index_xu100_daily.parquet")

    stocks = apply_corrections(stocks, corr)
    stocks, dropped = drop_partial_bar(stocks)
    idx, _ = drop_partial_bar(idx)
    stocks = stocks.sort_values(["symbol", "date"]).reset_index(drop=True)
    idx = idx.sort_values("date").reset_index(drop=True)

    stocks["volume_missing"] = stocks["volume"] <= 0
    idx["volume_missing"] = idx["volume"] <= 0
    stocks["ret_1d"] = stocks.groupby("symbol")["adj_close"].pct_change()

    big = stocks.loc[stocks["ret_1d"].abs() > 0.25, ["symbol", "date", "ret_1d"]]
    report = {
        "built_at": datetime.now(IST).isoformat(),
        "corrections_applied": corr.to_dict("records"),
        "partial_bar_dropped": dropped,
        "last_date": str(stocks["date"].max().date()),
        "rows": int(len(stocks)),
        "volume_missing_rows": int(stocks["volume_missing"].sum()),
        "volume_missing_by_symbol": stocks.loc[stocks["volume_missing"]].groupby("symbol").size().to_dict(),
        "moves_over_25pct": [
            {"symbol": r.symbol, "date": str(r.date.date()), "ret": round(float(r.ret_1d), 4)}
            for r in big.itertuples()
        ],
    }
    stocks.to_parquet(PROCESSED / "prices_clean.parquet", index=False)
    idx.to_parquet(PROCESSED / "index_clean.parquet", index=False)
    (RAW / "clean_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    r = clean()
    print({k: v for k, v in r.items() if k not in ("volume_missing_by_symbol",)})
    print("volume_missing top:", dict(sorted(r["volume_missing_by_symbol"].items(), key=lambda x: -x[1])[:4]))
