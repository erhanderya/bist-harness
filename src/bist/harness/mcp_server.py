"""MCP server exposing the harness (stdio). python -m bist.harness.mcp_server

The 16 analysis tools are NOT exposed as free-standing MCP tools: they are reachable only through `call_tool`, which runs them inside an
analysis session where the state machine decides whether the tool is allowed right now. An MCP client (an LLM) therefore cannot skip
the quality gate, look ahead of the analysis date, or leave the workflow. No tool places or prepares an order.
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from ..tools import REGISTRY, SCHEMA_VERSION
from ..tools.envelope import jsonable
from ..tools.export_schemas import OUT as SCHEMA_FILE
from .logdb import DecisionLog
from .machine import Harness
from .replay import replay_analysis
from .states import ALLOWED_TOOLS, STATES

server = MCPServer("bist-harness", instructions=(
    "BIST 30-stock educational analytics harness. Workflow: start_analysis -> advance_state -> select_universe -> then per state call_tool with a tool "
    "listed in allowed_tools -> ... -> risk_gate -> submit_conclusion (one of 8 actions, evidence ids cited, numbers only from tool output) -> "
    "submit_human_review -> close_analysis. Output is educational only; never investment advice."))

_H: dict[str, Harness] = {}
_DB: DecisionLog | None = None


def _db() -> DecisionLog:
    global _DB
    if _DB is None:
        _DB = DecisionLog()
    return _DB


def _get(aid: str) -> Harness | dict:
    h = _H.get(aid)
    return h if h else {"error": {"code": "UNKNOWN_ANALYSIS", "message": f"analysis '{aid}' does not exist; call start_analysis"}}


@server.tool()
def start_analysis(question: str, as_of: str | None = None, focus: str = "general") -> dict:
    """Open an analysis. focus: general | sector_catchup | technical_reversal | fundamental_reaction | calendar_pattern. as_of: analysis date (nothing after it is ever read)."""
    h = Harness(question, as_of=as_of, focus=focus, db=_db())
    _H[h.id] = h
    return {**h.status(), "states": STATES}


@server.tool()
def get_status(analysis_id: str) -> dict:
    """Current state, tools allowed in it, legal next states."""
    h = _get(analysis_id)
    return h.status() if isinstance(h, Harness) else h


@server.tool()
def advance_state(analysis_id: str, to: str | None = None) -> dict:
    """Move to the next state (or a legal later one). Mandatory states cannot be skipped; the response says why a move is refused."""
    h = _get(analysis_id)
    return h.advance(to) if isinstance(h, Harness) else h


@server.tool()
def select_universe(analysis_id: str, tickers: list[str]) -> dict:
    """Choose the ticker(s) of this analysis (must be in the 30-stock universe). Only in SELECT_UNIVERSE."""
    h = _get(analysis_id)
    return jsonable(h.select_universe(tickers)) if isinstance(h, Harness) else h


@server.tool()
def call_tool(analysis_id: str, tool: str, params: dict | None = None) -> dict:
    """Run one analysis tool inside the analysis. Rejected (structured error) if the tool is not allowed in the current state."""
    h = _get(analysis_id)
    return jsonable(h.call(tool, **(params or {}))) if isinstance(h, Harness) else h


@server.tool()
def risk_gate(analysis_id: str) -> dict:
    """Evaluate the risk gate (only in RISK_GATE): verdict, reasons and the set of actions the conclusion may use."""
    h = _get(analysis_id)
    return jsonable(h.risk_gate()) if isinstance(h, Harness) else h


@server.tool()
def submit_conclusion(analysis_id: str, action: str, explanation: str) -> dict:
    """Submit the conclusion: action must be one of HOLD, WATCH, INVESTIGATE, POTENTIAL_CATCH_UP_CANDIDATE, TECHNICAL_REVERSAL_CANDIDATE,
    FUNDAMENTAL_IMPROVEMENT_CANDIDATE, REJECT_SIGNAL, ANALYSIS_UNSAFE. The explanation may cite only committed evidence ids [E#] and numbers that
    appear in the evidence. Returns validation violations if rejected."""
    h = _get(analysis_id)
    return h.propose(action, explanation) if isinstance(h, Harness) else h


@server.tool()
def submit_human_review(analysis_id: str, decision: str, reason: str, reviewer: str = "human") -> dict:
    """Record the human decision (APPROVE | REJECT | DEFER) and reason on the educational conclusion. Required before closing."""
    h = _get(analysis_id)
    return h.review(decision, reason, reviewer) if isinstance(h, Harness) else h


@server.tool()
def close_analysis(analysis_id: str) -> dict:
    """Write the final record to the decision log (only in LOG_AND_CLOSE)."""
    h = _get(analysis_id)
    return jsonable(h.close()) if isinstance(h, Harness) else h


@server.tool()
def replay(analysis_id: str) -> dict:
    """replay_analysis: re-run the logged tool calls and verify the results, evidence and decision are reproduced."""
    return jsonable(replay_analysis(analysis_id, _db()))


@server.tool()
def recall_past_cases(ticker: str, limit: int = 5) -> dict:
    """Temporal memory: earlier closed analyses of the ticker with their action and the human decision."""
    return {"ticker": ticker, "cases": jsonable(_db().recall(ticker, limit))}


@server.tool()
def describe_tools(state: str | None = None) -> dict:
    """Compact schemas of the analysis tools (all, or the ones allowed in `state`) plus the state->tools map."""
    import json
    sch = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    names = ALLOWED_TOOLS.get(state) if state else list(REGISTRY)
    return {"schema_version": SCHEMA_VERSION, "tools": [t for t in sch["compact_tools"] if t["name"] in (names or [])], "state_tools": ALLOWED_TOOLS}


if __name__ == "__main__":
    server.run("stdio")
