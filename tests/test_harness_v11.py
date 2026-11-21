"""v1.1 harness wiring: new tools in their states, evidence for the new fields, catch-up policy rule, reference agent on the 5 sample questions."""
import pytest

from bist.harness import policy, reference
from bist.harness.logdb import DecisionLog
from bist.harness.machine import Harness

AS_OF = "2026-09-10"
WIN = {"start": "2024-01-01", "end": AS_OF}
SAMPLE_RUNS = [
    ("Q1 retail laggard catch-up", "MAVI", "sector_catchup", {"peers": ["BIMAS", "MGROS"], "horizon_days": 20, **WIN}),
    ("Q2 THYAO Mon-Wed down, Thu-Fri up", "THYAO", "calendar_pattern",
     {"pattern": "weekday_sequence", "pattern_kw": {"down_days": ["MON", "TUE", "WED"], "up_days": ["THU", "FRI"], "oos_start": "2026-01-01"},
      "start": "2024-01-01", "end": AS_OF}),
    ("Q3 ASELS lower Bollinger touches", "ASELS", "technical_reversal",
     {"reversal_kw": {"event_types": ["bollinger_lower_touch"], "cooldown_days": 0,
                      "condition_sets": [["rsi_trough", "high_volume"], ["supertrend_bearish", "below_ichimoku_cloud"]]}, **WIN}),
    ("Q4 TUPRS disclosures and price reaction", "TUPRS", "fundamental_reaction", dict(WIN)),
    ("Q5 Should I buy EREGL tomorrow? Give me a price target.", "EREGL", "general", {"macro_factor": "usdtry", **WIN}),
]


@pytest.fixture()
def db(tmp_path):
    return DecisionLog(tmp_path / "d.sqlite")


def env(tool, data, warnings=()):
    return {"tool": tool, "envelope": {"status": "WARN" if warnings else "OK", "data": data, "warnings": [{"code": c, "message": c} for c in warnings]}}


def test_new_tools_only_in_their_states(db):
    h = Harness("q", as_of=AS_OF, db=db)
    h.advance()
    h.select_universe(["MAVI"])
    assert h.call("test_catch_up_history", ticker="MAVI")["error"]["code"] == "TOOL_NOT_ALLOWED_IN_STATE"
    for s, tool in (("RUN_SECTOR_RELATIVE_ANALYSIS", "test_catch_up_history"), ("LOAD_FUNDAMENTALS", "analyze_disclosure_reactions"),
                    ("LOAD_MACRO_CONTEXT", "analyze_macro_sensitivity")):
        from bist.harness.states import ALLOWED_TOOLS
        assert tool in ALLOWED_TOOLS[s]
        assert sum(tool in v for v in ALLOWED_TOOLS.values()) == 1


def test_catchup_candidate_needs_history():
    rank = env("rank_sector_relative_strength", {"ranking_valid": True, "sector_strong": True,
                                                 "ranking_lagging_first": [{"ticker": "MAVI", "lag_rank": 1}]})
    calls = [rank]
    s = policy.signals(calls, "MAVI", AS_OF)["catchup"]
    assert s["present"] is False and s["partial"] is True
    hist = env("test_catch_up_history", {"by_horizon": {"h10": {"n": 12, "narrowed_rate": 0.6}}})
    assert policy.signals(calls + [hist], "MAVI", AS_OF)["catchup"]["present"] is True
    weak = env("test_catch_up_history", {"by_horizon": {"h10": {"n": 12, "narrowed_rate": 0.4}}})
    assert policy.signals(calls + [weak], "MAVI", AS_OF)["catchup"]["present"] is False
    few = env("test_catch_up_history", {"by_horizon": {"h10": {"n": 6, "narrowed_rate": 0.9}}})
    assert policy.signals(calls + [few], "MAVI", AS_OF)["catchup"]["present"] is False


@pytest.mark.parametrize("q,tk,focus,kw", SAMPLE_RUNS, ids=[r[0][:2] for r in SAMPLE_RUNS])
def test_reference_passes_validator_on_samples(db, q, tk, focus, kw):
    h = reference.run(q, tk, focus, as_of=AS_OF, db=db, **kw)      # run() raises if the validator rejects the output
    assert h.state == "HUMAN_REVIEW" and h.violations == []
    b = h.evidence
    assert all(it["as_of"] is None or it["as_of"] <= AS_OF for it in b["observed"])
    tools = {c["tool"] for c in h.calls}
    expected = {"Q1": {"rank_sector_relative_strength", "test_catch_up_history"}, "Q2": {"test_weekday_pattern"},
                "Q3": {"detect_reversal_events", "calculate_indicators"}, "Q4": {"analyze_disclosure_reactions", "get_fundamental_metrics"},
                "Q5": {"get_macro_context", "analyze_macro_sensitivity"}}[q[:2]]
    assert expected <= tools
    for c in h.calls:  # news/speech sources are not installed by design (SOURCE_NOT_AVAILABLE)
        if c["tool"] not in ("get_news_events", "get_speech_features"):
            assert c["envelope"]["status"] != "ERROR", (c["tool"], c["envelope"]["error"])
    kinds = {it["kind"] for it in b["observed"]}
    want = {"Q1": "catchup_history", "Q2": "pattern", "Q3": "reversal_history", "Q4": "disclosure", "Q5": "macro_sensitivity"}[q[:2]]
    assert want in kinds
    if q.startswith("Q5"):
        assert h.decision["action"] in ("WATCH", "INVESTIGATE", "HOLD", "REJECT_SIGNAL")


def test_q3_condition_sets_reach_evidence(db):
    q, tk, focus, kw = SAMPLE_RUNS[2]
    h = reference.run(q, tk, focus, as_of=AS_OF, db=db, **kw)
    st = [it["statement"] for it in h.evidence["observed"] if it["kind"] == "reversal_condition"]
    assert len(st) == 2 and any("rsi_trough & high_volume" in s for s in st)


def test_q2_is_and_oos_reach_evidence(db):
    q, tk, focus, kw = SAMPLE_RUNS[1]
    h = reference.run(q, tk, focus, as_of=AS_OF, db=db, **kw)
    st = " ".join(it["statement"] for it in h.evidence["observed"] if it["kind"] == "pattern")
    assert "in-sample" in st and "out-of-sample" in st and "costs" in st
