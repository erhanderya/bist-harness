"""Backfill financial-report publish timestamps for the 30-stock universe from KAP's site endpoint.

Source: kap.org.tr /tr/api/disclosure/members/byCriteria (unofficial, undocumented). Monthly windows
(KAP requires from/to in the same calendar year). Output: data/processed/kap_fr_disclosures.parquet
Usage: python -m bist.fetch_disclosure_times [--start 2016-01] [--end 2026-11]
"""
import argparse
import calendar
import json
import sys
import time
from datetime import date, timedelta

import pandas as pd
import requests

from .paths import PROCESSED, RAW
from .universe import load_universe

URL = "https://www.kap.org.tr/tr/api/disclosure/members/byCriteria"
H = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json", "Accept": "application/json",
     "Origin": "https://www.kap.org.tr", "Referer": "https://www.kap.org.tr/tr/bildirim-sorgu"}


def _crit(a: str, b: str) -> dict:
    return {"fromDate": a, "toDate": b, "memberType": "IGS", "mkkMemberOidList": [], "inactiveMkkMemberOidList": [],
            "disclosureClass": "FR", "subjectList": [], "isLate": "", "mainSector": "", "sector": "", "subSector": "",
            "marketOidList": [], "index": "", "bdkReview": "", "bdkMemberOidList": [], "year": "", "term": "",
            "ruleType": "", "period": "", "fromSrc": False, "srcCategory": "", "disclosureIndexList": []}


def _post(a: str, b: str, retries: int = 6):
    for i in range(1, retries + 1):
        try:
            r = requests.post(URL, json=_crit(a, b), headers=H, timeout=90)
            if r.status_code == 200:
                return r.json()
            print(f"  {a}..{b} HTTP {r.status_code} (try {i})")
        except Exception as e:
            print(f"  {a}..{b} {type(e).__name__} (try {i})")
        time.sleep(min(60, 5 * i * i))
    return None


CAP = 2000  # KAP truncates a response at 2000 items -> split the window until below the cap


def _fetch_split(a: str, b: str):
    d = _post(a, b)
    if d is None or len(d) < CAP or a == b:
        if d is not None and len(d) >= CAP:
            print(f"  WARNING single day {a} hit the cap ({len(d)})")
        return d
    da, db = date.fromisoformat(a), date.fromisoformat(b)
    mid = da + (db - da) / 2
    mid = date(mid.year, mid.month, mid.day)
    print(f"  {a}..{b} hit cap {len(d)} -> split at {mid}")
    time.sleep(1.5)
    left = _fetch_split(a, mid.isoformat())
    time.sleep(1.5)
    right = _fetch_split((mid + timedelta(days=1)).isoformat(), b)
    if left is None or right is None:
        return None
    return left + right


def windows(start: str, end: str):
    y, m = map(int, start.split("-"))
    ye, me = map(int, end.split("-"))
    while (y, m) <= (ye, me):
        yield f"{y}-{m:02d}-01", f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
        m += 1
        if m == 13:
            y, m = y + 1, 1


def main(start: str, end: str, merge: bool = False) -> int:
    tickers = set(load_universe()["ticker"])
    rows, failed = [], []
    for a, b in windows(start, end):
        d = _fetch_split(a, b)
        if d is None:
            failed.append(a)
            continue
        got = 0
        for x in d:
            codes = {c.strip() for c in (x.get("stockCodes") or "").replace(";", ",").split(",")}
            for t in codes & tickers:
                rows.append({"ticker": t, "publish_ts": pd.to_datetime(x["publishDate"], format="%d.%m.%Y %H:%M:%S"),
                             "subject": x.get("subject"), "year": x.get("year"), "period": x.get("period"),
                             "disclosure_index": x.get("disclosureIndex"), "modify_status": x.get("modifyStatus"),
                             "is_late": x.get("isLate"), "attachment_count": x.get("attachmentCount")})
                got += 1
        print(f"{a[:7]}: total={len(d):4d} ours={got}", flush=True)
        time.sleep(1.5)
    if failed:
        print("FAILED windows:", failed)
    df = pd.DataFrame(rows)
    out = PROCESSED / "kap_fr_disclosures.parquet"
    if merge and out.exists():  # patch missing windows without losing earlier results
        df = pd.concat([pd.read_parquet(out), df], ignore_index=True)
        df = df.drop_duplicates(["ticker", "disclosure_index"])
    df = df.sort_values(["ticker", "publish_ts"]).reset_index(drop=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    (RAW / "kap_fr_meta.json").write_text(json.dumps({"start": start, "end": end, "failed_windows": failed,
                                                       "rows": len(df)}, indent=2), encoding="utf-8")
    print("rows", len(df), "| failed windows", len(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2016-01")
    ap.add_argument("--end", default="2026-11")
    ap.add_argument("--merge", action="store_true", help="merge into existing parquet (patch failed windows)")
    a = ap.parse_args()
    sys.exit(main(a.start, a.end, a.merge))
