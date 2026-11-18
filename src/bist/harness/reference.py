"""Reference agent: drives the harness through every state with the right tools and parameters, deterministically.

It is (a) the oracle for evaluation, (b) the source of correct tool-call traces for the training data, and (c) a demo that the
harness works without any language model. The LLM agent (llm_client.py) fills the same slots by choosing tools/params itself.
"""
from __future__ import annotations

from .logdb import DecisionLog
from .machine import Harness, HarnessConfig

DEFAULT_VARIANT = {"technical_reversal": "A", "sector_catchup": "B", "fundamental_reaction": "C", "calendar_pattern": "D", "general": "D"}
STAGES = {  # optional analysis states executed per focus
    "sector_catchup": {"CALCULATE_TECHNICALS", "RUN_SECTOR_RELATIVE_ANALYSIS", "RUN_PATTERN_AND_REVERSAL_ANALYSIS", "LOAD_MACRO_CONTEXT"},
    "technical_reversal": {"CALCULATE_TECHNICALS", "RUN_PATTERN_AND_REVERSAL_ANALYSIS", "RUN_SECTOR_RELATIVE_ANALYSIS", "LOAD_MACRO_CONTEXT"},
    "fundamental_reaction": {"CALCULATE_TECHNICALS", "LOAD_FUNDAMENTALS", "LOAD_MACRO_CONTEXT"},
    "calendar_pattern": {"RUN_PATTERN_AND_REVERSAL_ANALYSIS"},
    "general": {"CALCULATE_TECHNICALS", "RUN_SECTOR_RELATIVE_ANALYSIS", "RUN_PATTERN_AND_REVERSAL_ANALYSIS", "LOAD_FUNDAMENTALS", "LOAD_MACRO_CONTEXT", "LOAD_NEWS_AND_SPEECH_CONTEXT"},
}


def plan(ticker: str, focus: str, horizon_days: int = 10, weekday: str = "THU", pattern: str = "weekday_return",
         variant: str | None = None, hold_days: int = 5) -> list[tuple[str, str, dict]]:
    """[(state, tool, params)] for the focus. Pure data: also used to build training traces."""
    p = [("LOAD_MARKET_DATA", "get_stock_history", {"ticker": ticker, "max_rows": 5}),
         ("LOAD_MARKET_DATA", "get_index_history", {"max_rows": 5}),
         ("CHECK_DATA_QUALITY", "check_data_quality", {"tickers": [ticker], "analysis_type": focus}),
         ("CALCULATE_TECHNICALS", "calculate_indicators", {"ticker": ticker}),
         ("RUN_SECTOR_RELATIVE_ANALYSIS", "rank_sector_relative_strength", {"sector": ticker, "horizon_days": horizon_days})]
    if focus == "calendar_pattern":
        extra = {"weekday": weekday} if pattern != "bounce_after_n_down_days" else {}
        p.append(("RUN_PATTERN_AND_REVERSAL_ANALYSIS", "test_weekday_pattern", {"ticker": ticker, "pattern": pattern, **extra}))
    else:
        p.append(("RUN_PATTERN_AND_REVERSAL_ANALYSIS", "detect_reversal_events", {"ticker": ticker, "direction": "both"}))
    p += [("LOAD_FUNDAMENTALS", "get_fundamental_metrics", {"ticker": ticker}),
          ("LOAD_FUNDAMENTALS", "calculate_fundamental_change", {"ticker": ticker}),
          ("LOAD_MACRO_CONTEXT", "get_macro_context", {}),
          ("LOAD_NEWS_AND_SPEECH_CONTEXT", "get_news_events", {"ticker": ticker}),
          ("BUILD_EVIDENCE", "build_evidence_bundle", {}),
          ("PREVIEW_STRATEGIES", "generate_strategy_variants", {"hold_days": hold_days}),
          ("RUN_BACKTEST", "run_backtest", {"variant": variant or DEFAULT_VARIANT[focus], "hold_days": hold_days})]
    return p


def run(question: str, ticker: str, focus: str = "general", as_of: str | None = None, human: tuple[str, str] | None = None,
        db: DecisionLog | None = None, config: HarnessConfig | None = None, close: bool = True, **plan_kw) -> Harness:
    h = Harness(question, as_of=as_of, focus=focus, db=db, config=config)
    h.advance()                                   # START -> SELECT_UNIVERSE
    h.select_universe([ticker])
    t = h.tickers[0]
    wanted = STAGES[focus] | {"LOAD_MARKET_DATA", "CHECK_DATA_QUALITY", "BUILD_EVIDENCE", "PREVIEW_STRATEGIES", "RUN_BACKTEST"}
    for state, tool, params in plan(t, focus, **plan_kw):
        if state not in wanted:
            continue
        if h.state != state:
            if state not in h.next_states():      # blocked data short-circuits the analysis states
                continue
            h.advance(state)
        if state == "BUILD_EVIDENCE" and h.blocked() is False:
            pass
        h.call(tool, **params)
    # drive the remaining mandatory states (evidence is built even when blocked, so the refusal is documented)
    while h.state != "RISK_GATE":
        if h.state == "BUILD_EVIDENCE" and not any(c["tool"] == "build_evidence_bundle" for c in h.calls):
            h.call("build_evidence_bundle")
        r = h.advance()
        if not r["ok"]:
            raise RuntimeError(f"reference agent stuck in {h.state}: {r}")
        if h.state == "BUILD_EVIDENCE" and not any(c["tool"] == "build_evidence_bundle" for c in h.calls):
            h.call("build_evidence_bundle")
    h.risk_gate()
    h.advance()                                   # -> GENERATE_EXPLANATION
    out = h.reference_output()
    res = h.propose(out["action"], out["explanation"])
    if not res["ok"]:
        raise RuntimeError(f"reference output rejected by validator: {res}")
    h.advance()                                   # -> HUMAN_REVIEW
    if human:
        h.review(human[0], human[1])
        if close:
            h.advance()
            h.close()
    return h
