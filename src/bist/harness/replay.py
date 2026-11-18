"""replay_analysis: re-executes the recorded tool calls of a logged analysis in a fresh session and checks that the
deterministic results (result_hash), the evidence, the gate and the decision are reproduced."""
from __future__ import annotations

import json
import uuid

from ..tools import session
from . import policy
from .logdb import DecisionLog


def replay_analysis(analysis_id: str, db: DecisionLog | None = None) -> dict:
    db = db or DecisionLog()
    a = db.analysis(analysis_id)
    if not a:
        return {"ok": False, "error": f"unknown analysis {analysis_id}"}
    rid = f"R-{uuid.uuid4().hex[:8]}"
    session.new_analysis(rid, as_of=a["as_of"], question=a["question"])
    mism, n = [], 0
    for c in db.calls(analysis_id):
        old = json.loads(c["envelope"])
        params = json.loads(c["params"])
        if c["tool"] == "build_evidence_bundle":
            params = {"analysis_id": rid}
        new = session.run(rid, c["tool"], **params)
        n += 1
        if c["tool"] == "build_evidence_bundle":
            same = [i["statement"] for i in new["data"]["observed"]] == [i["statement"] for i in old["data"]["observed"]]
        else:
            same = (old.get("provenance") or {}).get("result_hash") == (new.get("provenance") or {}).get("result_hash") and old["status"] == new["status"]
        if not same:
            mism.append({"call": c["call_id"], "tool": c["tool"]})
    tk = (a["tickers"] or "").split(",")[0]
    calls = session.calls(rid)
    gate = policy.risk_gate(calls)
    dec = policy.decide(calls, tk, a["focus"], a["as_of"], gate)
    return {"ok": not mism and dec["action"] == a["reference_action"], "analysis_id": analysis_id, "calls_replayed": n, "mismatched_calls": mism,
            "recorded_reference_action": a["reference_action"], "replayed_action": dec["action"], "recorded_gate": a["gate_verdict"],
            "replayed_gate": gate["verdict"], "recorded_final_action": a["action"]}
