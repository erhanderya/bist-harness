"""Download daily OHLCV for the 30-stock universe + XU100 into a local Parquet cache.

Sequential per-symbol download with retries. Cache files are only replaced when
ALL symbols were retrieved (no partial caches). Run once online; afterwards
everything reads from data/processed (offline).
Usage: python -m bist.fetch_prices [--start 2015-01-01]
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from .paths import PROCESSED, RAW
from .universe import load_universe

INDEX_SYMBOL = "XU100.IS"


def _fetch_one(symbol: str, start: str, retries: int = 5) -> pd.DataFrame | None:
    for attempt in range(1, retries + 1):
        try:
            d = yf.Ticker(symbol).history(start=start, auto_adjust=False, actions=True)
            if d is not None and len(d) > 0:
                d = d.copy()
                d.columns = [c.lower().replace(" ", "_") for c in d.columns]
                d.index = pd.to_datetime(d.index).tz_localize(None).normalize()
                d.index.name = "date"
                d["symbol"] = symbol
                return d.reset_index()
        except Exception as e:  # network / parsing
            print(f"  {symbol} attempt {attempt}: {type(e).__name__}: {str(e)[:80]}")
        time.sleep(2 * attempt)
    return None


def main(start: str) -> int:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    symbols = load_universe()["yahoo_symbol"].tolist()

    frames, missing = [], []
    for s in symbols + [INDEX_SYMBOL]:
        d = _fetch_one(s, start)
        if d is None:
            missing.append(s)
            print(f"{s}: FAILED")
        else:
            frames.append(d)
            print(f"{s}: {len(d)} rows {d['date'].min().date()} -> {d['date'].max().date()}")
        time.sleep(0.5)

    if missing:
        print(f"\nABORT: {len(missing)} symbols missing {missing}; cache NOT updated.")
        return 1

    all_df = pd.concat(frames, ignore_index=True)
    stocks = all_df[all_df["symbol"] != INDEX_SYMBOL]
    idx = all_df[all_df["symbol"] == INDEX_SYMBOL]
    stocks.to_parquet(PROCESSED / "prices_daily.parquet", index=False)
    idx.to_parquet(PROCESSED / "index_xu100_daily.parquet", index=False)

    per = (stocks.groupby("symbol")["date"].agg(["min", "max", "count"])
           .astype(str).to_dict("index"))
    meta = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "yfinance",
        "start_requested": start,
        "index_rows": int(len(idx)),
        "per_symbol": per,
    }
    (RAW / "prices_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\nOK stocks rows={len(stocks)} symbols={stocks['symbol'].nunique()}/30 index rows={len(idx)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2015-01-01")
    sys.exit(main(ap.parse_args().start))
