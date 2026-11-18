"""SQLite decision log (data/db/decisions.sqlite): analyses, state transitions, tool calls (full envelopes), evidence, human reviews.

Used for audit, temporal memory (`recall`) and `replay_analysis`. Records are append-only except the final analysis row.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..paths import DB

DEFAULT_PATH = DB / "decisions.sqlite"
SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses(id TEXT PRIMARY KEY, created_utc TEXT, question TEXT, as_of TEXT, focus TEXT, tickers TEXT, sector TEXT,
  final_state TEXT, gate_verdict TEXT, action TEXT, reference_action TEXT, explanation TEXT, violations TEXT, schema_version TEXT, closed_utc TEXT, record TEXT);
CREATE TABLE IF NOT EXISTS transitions(analysis_id TEXT, seq INTEGER, from_state TEXT, to_state TEXT, ok INTEGER, note TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS tool_calls(analysis_id TEXT, seq INTEGER, call_id TEXT, state TEXT, tool TEXT, params TEXT, status TEXT, result_hash TEXT, envelope TEXT, allowed INTEGER, ts TEXT);
CREATE TABLE IF NOT EXISTS evidence(analysis_id TEXT, evidence_id TEXT, kind TEXT, statement TEXT, committed INTEGER, reason TEXT, source_call TEXT);
CREATE TABLE IF NOT EXISTS reviews(analysis_id TEXT, reviewer TEXT, decision TEXT, reason TEXT, ts TEXT);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DecisionLog:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else Path(os.environ.get("BIST_DECISION_DB", DEFAULT_PATH))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)

    def exec(self, sql: str, *a):
        cur = self.con.execute(sql, a)
        self.con.commit()
        return cur

    def start(self, aid, question, as_of, focus, sector=None):
        self.exec("INSERT OR REPLACE INTO analyses(id, created_utc, question, as_of, focus, sector, final_state) VALUES(?,?,?,?,?,?,?)", aid, _now(), question, as_of, focus, sector, "START")

    def transition(self, aid, seq, a, b, ok, note=""):
        self.exec("INSERT INTO transitions VALUES(?,?,?,?,?,?,?)", aid, seq, a, b, int(ok), note, _now())

    def tool_call(self, aid, seq, call_id, state, tool, params, env, allowed=True):
        h = ((env or {}).get("provenance") or {}).get("result_hash")
        self.exec("INSERT INTO tool_calls VALUES(?,?,?,?,?,?,?,?,?,?,?)", aid, seq, call_id, state, tool, json.dumps(params, default=str, ensure_ascii=False),
                  (env or {}).get("status"), h, json.dumps(env, default=str, ensure_ascii=False), int(allowed), _now())

    def evidence(self, aid, items):
        for it in items:
            self.exec("INSERT INTO evidence VALUES(?,?,?,?,?,?,?)", aid, it["id"], it["kind"], it["statement"], int(it["commit"]), it.get("reason"), it["source_call"])

    def review(self, aid, reviewer, decision, reason):
        self.exec("INSERT INTO reviews VALUES(?,?,?,?,?)", aid, reviewer, decision, reason, _now())

    def finish(self, aid, **f):
        cols = ", ".join(f"{k}=?" for k in f)
        self.exec(f"UPDATE analyses SET {cols}, closed_utc=? WHERE id=?", *f.values(), _now(), aid)

    # -- reading
    def analysis(self, aid) -> dict | None:
        r = self.exec("SELECT * FROM analyses WHERE id=?", aid).fetchone()
        return dict(r) if r else None

    def calls(self, aid, allowed_only=True) -> list[dict]:
        q = "SELECT * FROM tool_calls WHERE analysis_id=?" + (" AND allowed=1" if allowed_only else "") + " ORDER BY seq"
        return [dict(r) for r in self.exec(q, aid).fetchall()]

    def reviews(self, aid) -> list[dict]:
        return [dict(r) for r in self.exec("SELECT * FROM reviews WHERE analysis_id=? ORDER BY ts", aid).fetchall()]

    def recall(self, ticker: str, limit: int = 5) -> list[dict]:
        """Temporal memory: earlier closed analyses of the same ticker with their action and the human decision."""
        rows = self.exec("SELECT id, as_of, focus, action, gate_verdict FROM analyses WHERE tickers LIKE ? AND closed_utc IS NOT NULL ORDER BY closed_utc DESC LIMIT ?", f"%{ticker}%", limit).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            rv = self.reviews(d["id"])
            d["human_decision"] = rv[-1]["decision"] if rv else None
            d["human_reason"] = rv[-1]["reason"] if rv else None
            out.append(d)
        return out
