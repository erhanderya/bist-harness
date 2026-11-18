"""Harvest ORIGINAL (as-first-published) financial statements for the 30 tickers from the official KAP VYK API
(test gateway: covers ~Feb-Dec 2023, i.e. FY2022 + Q1..Q3 2023).

Purpose: ground truth to validate Is Yatirim numbers (are they original or restated?).
Throttle: free plan = 6 calls/min -> KapClient spaces calls 10.5 s. Resumable: existing detail files are skipped.
Output: data/raw/kap_official/detail_<index>.json (raw, LOCAL ONLY - Borsa Istanbul licence) and manifest.parquet
"""
import json
import time

import pandas as pd

from .kap_official import KapClient
from .paths import RAW
from .universe import load_universe

OUT = RAW / "kap_official"
START_INDEX = 1100000
END_INDEX = 1231017  # last index in the test environment (a 31.12.2023 test notification)


def _get(c: KapClient, path: str, **params):
    for k in range(1, 6):
        r = c.get(path, **params)
        if r.status_code == 200:
            return r
        if r.status_code == 400 and "ER005" in r.text:  # "disclosure not found" = end of list, NOT an error
            return None
        print(f"  {path} {params} HTTP {r.status_code} (try {k}) {r.text[:80]!r}", flush=True)
        time.sleep(30 * k if r.status_code in (429, 503) else 10)
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    c = KapClient()
    members = json.loads((OUT / "members.json").read_text(encoding="utf-8")) if (OUT / "members.json").exists() else None
    if members is None:
        r = _get(c, "/members")
        members = r.json()
        (OUT / "members.json").write_text(json.dumps(members, ensure_ascii=False), encoding="utf-8")
    cid = {}
    for m in members:
        for code in [x.strip() for x in (m.get("stockCode") or "").split(",")]:
            cid.setdefault(code, m["id"])
    manifest_path = OUT / "manifest.parquet"
    done = pd.read_parquet(manifest_path).to_dict("records") if manifest_path.exists() else []
    seen = {int(x["disclosure_index"]) for x in done}

    import sys
    only = sys.argv[1:]
    for t in (only or load_universe()["ticker"]):
        if t not in cid:
            print(f"{t}: no companyId", flush=True)
            continue
        idx, fin = START_INDEX, []
        for _ in range(15):
            r = _get(c, "/disclosures", disclosureIndex=idx, disclosureClass="FR", companyId=cid[t])
            if r is None:
                break
            L = r.json()
            if not L:
                break
            # financial statements: general_/banks_/holding_/insurance_role_*  ("oda-*" are non-financial)
            fin += [int(x["disclosureIndex"]) for x in L if any("_role_" in s for s in (x.get("subReportIds") or []))]
            nxt = max(int(x["disclosureIndex"]) for x in L) + 1
            if nxt >= END_INDEX or nxt <= idx:
                break
            idx = nxt
        print(f"{t}: financial notifications {sorted(set(fin))}", flush=True)
        for di in sorted(set(fin)):
            f = OUT / f"detail_{di}.json"
            if di in seen and f.exists():
                continue
            r = _get(c, f"/disclosureDetail/{di}", fileType="data")
            if r is None:
                continue
            f.write_text(r.text, encoding="utf-8")
            d = r.json()
            done.append({"ticker": t, "disclosure_index": di, "time": d.get("time"), "year": d.get("year"),
                         "period": (d.get("period") or {}).get("en"), "consolidation": d.get("consolidation"),
                         "subject": (d.get("subject") or {}).get("tr")})
            seen.add(di)
            pd.DataFrame(done).to_parquet(manifest_path, index=False)
    print("DONE", len(done), flush=True)


if __name__ == "__main__":
    main()
