"""Fetch quarterly financial statements for the 30-stock universe from Is Yatirim MaliTablo (unofficial).

Flow items (income / cash-flow) are YEAR-TO-DATE cumulative -> quarterly de-cumulation happens later.
NO publication date here (joined from KAP disclosures later). Output (long format):
data/processed/fundamentals_raw.parquet  [ticker, group, year, period, item_code, item_tr, item_en, value]
Usage: python -m bist.fetch_fundamentals [--first-year 2015] [--last-year 2026] [--tickers THYAO,AKBNK]
"""
import argparse
import json
import time

import pandas as pd
import requests

from .paths import PROCESSED, RAW
from .universe import load_universe

B = "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/MaliTablo"
GROUPS = ["XI_29", "UFRS"]  # industrial, bank (a wrong group returns 0 rows silently!)


def _call(code, grp, periods, retries=5):
    p = {"companyCode": code, "exchange": "TRY", "financialGroup": grp}
    for i, (y, m) in enumerate(periods, 1):
        p[f"year{i}"] = y
        p[f"period{i}"] = m
    for k in range(1, retries + 1):
        try:
            r = requests.get(B, params=p, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
            if r.status_code == 200:
                d = r.json()
                if d.get("ok"):
                    return d.get("value") or []
            print(f"  {code} {grp} {periods[0]} HTTP {r.status_code} (try {k})")
        except Exception as e:
            print(f"  {code} {grp} {type(e).__name__} (try {k})")
        time.sleep(3 * k)
    return None


def period_list(first, last):
    ps = [(y, m) for y in range(last, first - 1, -1) for m in (12, 9, 6, 3)]
    return [ps[i:i + 4] for i in range(0, len(ps), 4)]


def fetch_company(code, first, last):
    rows, group_used = [], None
    probe = [(last - 1, 12), (last - 1, 9), (last - 1, 6), (last - 1, 3)]
    for grp in GROUPS:
        if _call(code, grp, probe):
            group_used = grp
            break
    if group_used is None:
        print(f"{code}: NO DATA in any group")
        return rows, None
    for chunk in period_list(first, last):
        v = _call(code, group_used, chunk)
        if v is None:
            print(f"{code}: chunk {chunk[0]} FAILED")
            continue
        for it in v:
            for i, (y, m) in enumerate(chunk, 1):
                val = it.get(f"value{i}")
                if val not in (None, ""):
                    rows.append({"ticker": code, "group": group_used, "year": y, "period": m,
                                 "item_code": it["itemCode"], "item_tr": it["itemDescTr"],
                                 "item_en": it.get("itemDescEng"), "value": float(val)})
        time.sleep(0.8)
    return rows, group_used


def main(first, last, tickers):
    codes = tickers or load_universe()["ticker"].tolist()
    allrows, groups = [], {}
    for c in codes:
        rows, g = fetch_company(c, first, last)
        groups[c] = g
        allrows += rows
        periods = sorted({(r["year"], r["period"]) for r in rows})
        print(f"{c:6} group={g} rows={len(rows):6d} periods={len(periods)} "
              f"span={periods[0] if periods else None}..{periods[-1] if periods else None}", flush=True)
    df = pd.DataFrame(allrows)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out = PROCESSED / ("fundamentals_raw.parquet" if not tickers else "fundamentals_raw_partial.parquet")
    df.to_parquet(out, index=False)
    (RAW / "fundamentals_meta.json").write_text(json.dumps({"groups": groups, "rows": len(df)}, indent=2),
                                                encoding="utf-8")
    print("saved", out.name, len(df))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--first-year", type=int, default=2015)
    ap.add_argument("--last-year", type=int, default=2026)
    ap.add_argument("--tickers", default="")
    a = ap.parse_args()
    main(a.first_year, a.last_year, [t for t in a.tickers.split(",") if t])
