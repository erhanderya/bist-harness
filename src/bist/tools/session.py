"""Analysis sessions: every tool call made inside an analysis is recorded under an analysis_id.

The harness (Phase 4) runs tools through `run()`, so the evidence bundle can be rebuilt from the recorded results only.
In-memory here; the harness persists the same records to its SQLite decision log.
"""
from __future__ import annotations

import pandas as pd

from .envelope import REGISTRY, ToolError

_SESSIONS: dict[str, dict] = {}


def new_analysis(analysis_id: str, as_of: str | None = None, question: str | None = None) -> str:
    _SESSIONS[analysis_id] = {"as_of": as_of, "question": question, "calls": []}
    return analysis_id


def calls(analysis_id: str) -> list[dict]:
    if analysis_id not in _SESSIONS:
        raise ToolError("UNKNOWN_ANALYSIS", f"analysis_id '{analysis_id}' does not exist; start an analysis first")
    return _SESSIONS[analysis_id]["calls"]


def session_as_of(analysis_id: str) -> str | None:
    calls(analysis_id)
    return _SESSIONS[analysis_id]["as_of"]


def run(analysis_id: str, tool_name: str, /, **kwargs) -> dict:
    """Execute a registered tool inside the session and record the full envelope (including errors)."""
    log = calls(analysis_id)
    if tool_name not in REGISTRY:
        env = {"tool": tool_name, "status": "ERROR", "error": {"code": "UNKNOWN_TOOL", "message": f"'{tool_name}' is not a registered tool"},
               "data": None, "warnings": [], "params": kwargs, "as_of": None, "provenance": None}
    else:
        if _SESSIONS[analysis_id]["as_of"] and "as_of" in REGISTRY[tool_name]["params_model"].model_fields and "as_of" not in kwargs:
            kwargs = {**kwargs, "as_of": _SESSIONS[analysis_id]["as_of"]}  # the session date is the default analysis date
        env = REGISTRY[tool_name]["fn"](**kwargs)
    log.append({"call_id": f"C{len(log) + 1}", "tool": tool_name, "envelope": env})
    return env
