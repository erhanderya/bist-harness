"""Validate Is Yatirim fundamentals against the ORIGINAL figures from the official KAP VYK API (test gateway, 2023).

For each official consolidated financial report (FY2022, Q1-Q3 2023) we read the CURRENT-period values of key
items (XBRL names) and compare them with fundamentals_raw.parquet (Is Yatirim). Question answered:
  1) do the two sources agree?   2) is Is Yatirim's value the ORIGINAL (point-in-time) figure or a restated one?
Output: data/processed/validation_kap_vs_isyatirim.parquet (one row per report x item)
"""
import json

import pandas as pd

from .paths import PROCESSED, RAW

OUT = RAW / "kap_official"
MONTH = {"Annual": 12, "3 Months": 3, "6 Months": 6, "9 Months": 9}
PERIOD_END = {3: "03-31", 6: "06-30", 9: "09-30", 12: "12-31"}

# XBRL name -> (Is Yatirim code, statement kind: 'bs' instant | 'flow' year-to-date)
TARGETS = {
    "Assets": ("1BL", "bs"), "CurrentAssets": ("1A", "bs"), "CurrentLiabilities": ("2A", "bs"),
    "Equity": ("2N", "bs"), "EquityAttributableToOwnersOfParent": ("2O", "bs"),
    "CashAndCashEquivalents": ("1AA", "bs"), "Inventories": ("1AF", "bs"),
    "Revenue": ("3C", "flow"), "GrossProfit": ("3D", "flow"),
    "ProfitLoss": ("3L", "flow"), "ProfitLossAttributableToOwnersOfParent": ("3Z", "flow"),
    "CashFlowsFromUsedInOperatingActivities": ("4C", "flow"),
}


def _walk(n, acc):
    if isinstance(n, dict):
        if "name" in n and "Values" in n:
            v = n["Values"]["Value"]
            v = v if isinstance(v, list) else [v]
            acc.setdefault(n["name"], {}).update({x["contextId"]: x["value"] for x in v if "contextId" in x})
        for x in n.values():
            _walk(x, acc)
    elif isinstance(n, list):
        for x in n:
            _walk(x, acc)


def parse_report(path):
    d = json.loads(path.read_text(encoding="utf-8"))
    by_kind = {"bs": {}, "flow": {}}
    for p in d.get("presentation") or []:
        rid = p["id"]
        role_no = rid.split("_role_")[-1] if "_role_" in rid else ""
        if role_no.startswith("2"):
            _walk(p["content"], by_kind["bs"])
        elif role_no.startswith("3"):
            _walk(p["content"], by_kind["flow"])
        elif role_no.startswith("5"):
            _walk(p["content"], by_kind["flow"])
    return d, by_kind


def build() -> pd.DataFrame:
    man = pd.read_parquet(OUT / "manifest.parquet")
    man = man[man["consolidation"] == "CS"].drop_duplicates(["ticker", "year", "period"], keep="first")
    iy = pd.read_parquet(PROCESSED / "fundamentals_raw.parquet")
    iy_idx = iy.set_index(["ticker", "year", "period", "item_code"])["value"]
    rows = []
    for r in man.itertuples():
        month = MONTH.get(r.period)
        if month is None:
            continue
        d, kinds = parse_report(OUT / f"detail_{r.disclosure_index}.json")
        year = int(r.year)
        end = f"{year}-{PERIOD_END[month]}"
        for name, (code, kind) in TARGETS.items():
            ctx = kinds[kind].get(name)
            if not ctx:
                continue
            key = end if kind == "bs" else f"{year}-01-01{end}"
            if key not in ctx:
                continue
            kap_v = float(ctx[key])
            try:
                iy_v = float(iy_idx.loc[(r.ticker, year, month, code)])
            except KeyError:
                iy_v = float("nan")
            rows.append({"ticker": r.ticker, "year": year, "month": month, "item": name, "code": code,
                         "which": "CURR", "kap_value": kap_v, "isy_value": iy_v, "kap_time": r.time})
            # PREV = prior-year comparative AS PRESENTED in this filing (same purchasing power as CURR).
            # flows: prior-year YTD; balance sheet: only for annual reports (prior year-end).
            pkey = f"{year - 1}-01-01{year - 1}-{PERIOD_END[month]}" if kind == "flow" else (f"{year - 1}-12-31" if month == 12 else None)
            if pkey and pkey in ctx:
                try:
                    iy_p = float(iy_idx.loc[(r.ticker, year - 1, month, code)])
                except KeyError:
                    iy_p = float("nan")
                rows.append({"ticker": r.ticker, "year": year - 1, "month": month, "item": name, "code": code,
                             "which": "PREV", "kap_value": float(ctx[pkey]), "isy_value": iy_p, "kap_time": r.time})
    df = pd.DataFrame(rows)
    df["rel_diff"] = (df["kap_value"] - df["isy_value"]).abs() / df["kap_value"].abs().where(df["kap_value"] != 0)
    return df


if __name__ == "__main__":
    df = build()
    df.to_parquet(PROCESSED / "validation_kap_vs_isyatirim.parquet", index=False)
    print("comparisons:", len(df))
