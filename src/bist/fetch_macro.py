"""Download market-based macro series (no API key needed): FX, global risk, commodities (Yahoo) and Fed rates (NY Fed API).
(FRED is not reachable from this network, so the effective Fed funds rate + target range come from markets.newyorkfed.org.)

Small downloads (a few hundred KB in total), sequential, low CPU. TCMB (EVDS) and TUIK series are separate (need a key).
Output: data/processed/macro_market_daily.parquet  (long: date, series, value)  + data/raw/macro_meta.json
As-of rule for features (applied later in the tools): value of day D-1 or earlier, because the global closes
(US markets, Brent) happen AFTER the BIST close at 18:00 Istanbul.
Usage: python -m bist.fetch_macro [--start 2015-01-01]
"""
import argparse
import io
import json
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import requests
import yfinance as yf

from .paths import PROCESSED, RAW

CACHE = RAW / "macro"  # one parquet per series: a failed run never loses what already arrived

YAHOO = {  # series name -> yahoo symbol
    "usdtry": "TRY=X", "eurtry": "EURTRY=X", "dxy": "DX-Y.NYB", "vix": "^VIX",
    "us10y": "^TNX", "brent": "BZ=F", "gold": "GC=F", "sp500": "^GSPC",
}


def _yahoo(sym: str, start: str, retries: int = 4) -> pd.DataFrame | None:
    for k in range(1, retries + 1):
        try:
            d = yf.Ticker(sym).history(start=start, auto_adjust=False, actions=False)
            if d is None or len(d) == 0:  # Yahoo sometimes returns nothing for a long start= window: fall back to max
                d = yf.Ticker(sym).history(period="max", auto_adjust=False, actions=False)
                d = d[d.index >= pd.Timestamp(start, tz=d.index.tz)] if len(d) else d
            if d is not None and len(d) > 0:
                s = d["Close"].copy()
                s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
                return s.rename("value").rename_axis("date").reset_index()
        except Exception as e:
            print(f"  {sym} attempt {k}: {type(e).__name__}: {str(e)[:80]}")
        time.sleep(15 * k)  # Yahoo soft rate limit: back off generously
    return None


def _nyfed(start: str, retries: int = 4) -> pd.DataFrame | None:
    """EFFR (percent) and the FOMC target range upper/lower bound, daily business days."""
    url = ("https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json"
           f"?startDate={start}&endDate={datetime.now(timezone.utc).date()}")
    for k in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                d = pd.DataFrame(r.json()["refRates"])
                d["date"] = pd.to_datetime(d["effectiveDate"])
                long = pd.concat([
                    d[["date", "percentRate"]].rename(columns={"percentRate": "value"}).assign(series="fed_funds_effective"),
                    d[["date", "targetRateTo"]].rename(columns={"targetRateTo": "value"}).assign(series="fed_target_upper"),
                    d[["date", "targetRateFrom"]].rename(columns={"targetRateFrom": "value"}).assign(series="fed_target_lower")])
                return long.dropna(subset=["value"]).sort_values(["series", "date"])
            print(f"  nyfed attempt {k}: HTTP {r.status_code}")
        except Exception as e:
            print(f"  nyfed attempt {k}: {type(e).__name__}: {str(e)[:80]}")
        time.sleep(3 * k)
    return None


def main(start: str) -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    missing = []
    for name, sym in YAHOO.items():
        f = CACHE / f"{name}.parquet"
        if f.exists():
            print(f"{name}: cached")
            continue
        d = _yahoo(sym, start)
        if d is None:
            missing.append(name)
            print(f"{name}: FAILED")
            time.sleep(20)
            continue
        d["series"], d["source"] = name, "yahoo:" + sym
        d.to_parquet(f, index=False)
        print(f"{name}: {len(d)} rows {d['date'].min().date()} -> {d['date'].max().date()}")
        time.sleep(3)
    d = _nyfed(start)
    if d is None:
        missing.append("fed")
        print("fed: FAILED")
    else:
        d["source"] = "nyfed:effr"
        d.to_parquet(CACHE / "fed.parquet", index=False)
        print(f"fed: {len(d)} rows")
    if missing:
        print(f"\nABORT: missing {missing}; combined file NOT written (per-series cache kept; re-run to fill the gaps).")
        return 1
    out = pd.concat([pd.read_parquet(f) for f in sorted(CACHE.glob("*.parquet"))], ignore_index=True)[["date", "series", "value", "source"]]
    out.to_parquet(PROCESSED / "macro_market_daily.parquet", index=False)
    meta = {"fetched_at_utc": datetime.now(timezone.utc).isoformat(), "start": start,
            "per_series": out.groupby("series")["date"].agg(["min", "max", "count"]).astype(str).to_dict("index")}
    (RAW / "macro_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\nOK rows={len(out)} series={out['series'].nunique()}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2015-01-01")
    sys.exit(main(ap.parse_args().start))
