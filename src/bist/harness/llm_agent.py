"""LLM agent: a local model (Ollama) drives the harness by choosing tool calls and writing the final conclusion.

Per state the model sees ONLY the tools that state exposes (+ a `next_state` pseudo-tool) and compact renderings of tool results
(the deterministic evidence statements, never raw 5 KB JSON). At GENERATE_EXPLANATION it must return {"action", "explanation"};
the harness validator rejects invented numbers / wrong actions / advice wording and the model gets the violations back (max 2 retries).
No cloud API is used anywhere: `OllamaChat` talks to http://localhost:11434.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Callable

from ..tools import REGISTRY
from ..tools.evidence import EXTRACTORS
from ..tools.export_schemas import OUT as SCHEMA_FILE
from . import policy
from .logdb import DecisionLog
from .machine import Harness, HarnessConfig
from .states import ALLOWED_TOOLS

SYSTEM = """You are the analysis agent of a BIST (Borsa Istanbul) educational analytics harness. You work in states; in each state you may call only the tools shown.
Rules: (1) numbers you write must come from tool output; never invent a number, a news item or a price. (2) Never give investment advice, price targets or buy/sell instructions.
(3) The only conclusions allowed are: HOLD, WATCH, INVESTIGATE, POTENTIAL_CATCH_UP_CANDIDATE, TECHNICAL_REVERSAL_CANDIDATE, FUNDAMENTAL_IMPROVEMENT_CANDIDATE, REJECT_SIGNAL, ANALYSIS_UNSAFE.
(4) If a tool reports an error, a missing source, or the data-quality gate blocks the analysis, say so; do not fill the gap. Call `next_state` when you are done with a state."""

NEXT_TOOL = {"type": "function", "function": {"name": "next_state", "description": "Finish the current state and move to the next one.", "parameters": {"type": "object", "properties": {}}}}


class OllamaChat:
    def __init__(self, model: str = "llama3.2:3b", host: str = "http://localhost:11434", temperature: float = 0.0, num_ctx: int = 8192, timeout: int = 300):
        self.model, self.host, self.temperature, self.num_ctx, self.timeout = model, host, temperature, num_ctx, timeout

    def __call__(self, messages: list[dict], tools: list[dict] | None = None, json_format: bool = False) -> dict:
        body = {"model": self.model, "messages": messages, "stream": False, "options": {"temperature": self.temperature, "num_ctx": self.num_ctx}}
        if tools:
            body["tools"] = tools
        if json_format:
            body["format"] = "json"
        req = urllib.request.Request(f"{self.host}/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())["message"]


def tool_defs(names: list[str]) -> list[dict]:
    sch = {t["name"]: t for t in json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))["tools"]}
    out = [NEXT_TOOL]
    for n in names:
        t = sch[n]
        out.append({"type": "function", "function": {"name": n, "description": t["description"], "parameters": t["input_schema"]}})
    return out


def render(tool: str, env: dict, call_id: str = "C0") -> str:
    """Compact text the model sees for a tool result."""
    if env["status"] == "ERROR":
        return f"{tool}: ERROR {env['error']['code']} - {env['error']['message']}"
    w = [x["code"] for x in env.get("warnings", [])]
    fn = EXTRACTORS.get(tool)
    if fn:
        try:
            st = [it["statement"] for it in fn({"call_id": call_id, "tool": tool, "envelope": env})]
            return f"{tool}: {env['status']}{' warnings=' + ','.join(w) if w else ''}\n" + "\n".join(st)
        except Exception:
            pass
    return f"{tool}: {env['status']}{' warnings=' + ','.join(w) if w else ''}\n" + json.dumps(env["data"], default=str)[:700]


class LLMAgent:
    def __init__(self, chat: Callable, db: DecisionLog | None = None, config: HarnessConfig | None = None, max_steps_per_state: int = 4, max_retries: int = 2):
        self.chat, self.db, self.cfg = chat, db, config
        self.max_steps, self.max_retries = max_steps_per_state, max_retries
        self.trace: list[dict] = []

    def _args(self, tc) -> tuple[str, dict]:
        f = tc["function"]
        a = f.get("arguments") or {}
        return f["name"], (json.loads(a) if isinstance(a, str) else a)


    def _work_state(self, h: Harness, msgs: list[dict]) -> None:
        tdefs = tool_defs(ALLOWED_TOOLS[h.state])
        prompt = (f"State {h.state}. Allowed tools: {', '.join(ALLOWED_TOOLS[h.state])}. Tickers: {', '.join(h.tickers)}. "
                  "Call the tool(s) needed for the question (skip the state if none is needed), then next_state.")
        for _ in range(self.max_steps):
            m = self.chat(msgs + [{"role": "user", "content": prompt}], tools=tdefs)
            calls = m.get("tool_calls") or []
            if not calls:
                return
            done = False
            for tc in calls:
                n, a = self._args(tc)
                if n == "next_state":
                    done = True
                    continue
                env = h.call(n, **a)
                self.trace.append({"state": h.state, "tool": n, "args": a, "status": env["status"]})
                msgs.append({"role": "tool", "content": render(n, env, h.calls[-1]["call_id"] if env["status"] != "ERROR" and h.calls else "C0")})
            if done:
                return

    def _ensure_required(self, h: Harness) -> None:
        """Mandatory tools the model did not call are run by the harness with safe defaults and flagged (the model cannot skip them)."""
        defaults = {"CHECK_DATA_QUALITY": ("check_data_quality", {"tickers": h.tickers}), "BUILD_EVIDENCE": ("build_evidence_bundle", {}),
                    "RUN_BACKTEST": ("run_backtest", {"variant": "D"})}
        d = defaults.get(h.state)
        if d and not (h.state == "RUN_BACKTEST" and h.blocked()) and not any(c["tool"] == d[0] and c["envelope"]["status"] != "ERROR" for c in h.calls):
            if h.state != "BUILD_EVIDENCE":   # evidence building is always done by the harness itself; not a model failure
                h.violations.append({"state": h.state, "tool": d[0], "code": "MANDATORY_TOOL_RUN_BY_HARNESS", "message": f"model did not complete {d[0]} correctly; default parameters used"})
            h.call(d[0], **d[1])

    def run(self, question: str, as_of: str | None = None, focus: str = "general", human: tuple[str, str] | None = None) -> Harness:
        h = Harness(question, as_of=as_of, focus=focus, db=self.db, config=self.cfg)
        msgs: list[dict] = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Question: {question}\nAnalysis date: {h.as_of}"}]
        h.advance()                                                       # START -> SELECT_UNIVERSE
        # SELECT_UNIVERSE: the model names the ticker(s)
        sel = [{"type": "function", "function": {"name": "select_universe", "description": "Choose the BIST ticker(s) for this analysis.",
                                                "parameters": {"type": "object", "properties": {"tickers": {"type": "array", "items": {"type": "string"}}}, "required": ["tickers"]}}}]
        for _ in range(self.max_steps):
            m = self.chat(msgs + [{"role": "user", "content": "State SELECT_UNIVERSE: call select_universe with the ticker(s) the question is about."}], tools=sel)
            for tc in m.get("tool_calls") or []:
                n, a = self._args(tc)
                if n == "select_universe":
                    r = h.select_universe(a.get("tickers", []))
                    self.trace.append({"state": h.state, "tool": n, "args": a, "result": "ok" if r.get("ok") else r["error"]["code"]})
            if h.tickers:
                break
        if not h.tickers:
            h.violations.append({"state": h.state, "tool": None, "code": "NO_TICKER_SELECTED", "message": "model did not select a valid ticker"})
            return h
        while h.state != "RISK_GATE":
            if h.state not in ("SELECT_UNIVERSE",) and ALLOWED_TOOLS[h.state] and h.state != "BUILD_EVIDENCE" and not (h.state == "RUN_BACKTEST" and h.blocked()):
                self._work_state(h, msgs)
            self._ensure_required(h)
            if not h.advance()["ok"]:
                raise RuntimeError(f"harness refused to advance from {h.state}")
        g = h.risk_gate()
        h.advance()                                                       # -> GENERATE_EXPLANATION
        ev = h.evidence
        obs = {i["id"]: i for i in ev["observed"]}
        ctx = ("Committed evidence (cite as [E#], quote only these numbers):\n" + "\n".join(f"[{i}] {obs[i]['statement']}" for i in ev["committed_ids"])
               + f"\nRisk gate: {g['verdict']} {g['reasons']}\nPermitted actions: {g['permitted_actions']}\n"
               + 'Return JSON: {"action": <one permitted action>, "explanation": <short text citing [E#] ids; end with: ' + policy.DISCLAIMER + '>}')
        feedback = ""
        for attempt in range(self.max_retries + 1):
            m = self.chat(msgs + [{"role": "user", "content": ctx + feedback}], json_format=True)
            try:
                out = json.loads(m["content"])
                res = h.propose(str(out.get("action", "")), str(out.get("explanation", "")))
            except Exception as e:  # malformed JSON
                res = {"ok": False, "violations": [f"MALFORMED_OUTPUT:{type(e).__name__}"]}
                h.violations.append({"state": h.state, "tool": None, "code": "OUTPUT_REJECTED", "message": res["violations"][0]})
            self.trace.append({"state": "GENERATE_EXPLANATION", "attempt": attempt, "ok": res["ok"], "violations": res["violations"]})
            if res["ok"]:
                break
            feedback = "\nYour previous answer was rejected: " + "; ".join(res["violations"]) + ". Fix it."
        if h.final is None:                                               # safe failure instead of an unvalidated conclusion
            ref = h.reference_output()
            h.violations.append({"state": h.state, "tool": None, "code": "LLM_FALLBACK", "message": "model output never passed validation; reference output used and flagged"})
            h.final = {**ref, "fallback": True}
        h.advance()
        if human:
            h.review(*human)
            h.advance()
            h.close()
        return h
