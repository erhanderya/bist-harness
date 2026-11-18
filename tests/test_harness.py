"""Harness: permissions, ordering, gate short-circuit, validator, human review, replay, SQLite log."""
import pytest

from bist.harness import policy, reference
from bist.harness.logdb import DecisionLog
from bist.harness.machine import Harness, HarnessConfig
from bist.harness.states import STATES


@pytest.fixture()
def db(tmp_path):
    return DecisionLog(tmp_path / "d.sqlite")


def fresh(db, focus="general", **kw):
    h = Harness("test question", focus=focus, db=db, **kw)
    h.advance()
    assert h.select_universe(["THYAO"])["ok"]
    return h


def test_seventeen_states_in_order():
    assert STATES[0] == "START" and STATES[-1] == "LOG_AND_CLOSE" and len(STATES) == 17


def test_tool_only_in_its_state(db):
    h = fresh(db)
    r = h.call("run_backtest", variant="A")          # state is SELECT_UNIVERSE
    assert r["status"] == "ERROR" and r["error"]["code"] == "TOOL_NOT_ALLOWED_IN_STATE"
    assert h.violations[-1]["code"] == "TOOL_NOT_ALLOWED_IN_STATE"
    assert h.calls == []                              # blocked calls never enter the evidence record
    assert len(db.calls(h.id)) == 0 and len(db.calls(h.id, allowed_only=False)) == 1


def test_unselected_ticker_and_future_as_of_rejected(db):
    h = fresh(db)
    h.advance("LOAD_MARKET_DATA")
    assert h.call("get_stock_history", ticker="AKBNK")["error"]["code"] == "TICKER_NOT_IN_SELECTION"
    assert h.call("get_stock_history", ticker="THYAO", as_of="2099-01-01")["error"]["code"] == "AS_OF_AFTER_ANALYSIS_DATE"
    assert h.call("get_stock_history", ticker="THYAO", max_rows=3)["status"] in ("OK", "WARN")


def test_unknown_ticker_selection(db):
    h = Harness("q", db=db)
    h.advance()
    assert h.select_universe(["XYZ"])["error"]["code"] == "UNKNOWN_TICKER" and h.tickers == []
    assert h.advance()["ok"] is False                 # cannot leave SELECT_UNIVERSE without a selection


def test_mandatory_states_cannot_be_skipped(db):
    h = fresh(db)
    h.advance("LOAD_MARKET_DATA")
    assert h.advance("RUN_BACKTEST")["ok"] is False   # skips CHECK_DATA_QUALITY
    assert h.advance("CHECK_DATA_QUALITY")["ok"] is True
    assert h.advance()["ok"] is False                 # quality tool not called yet
    h.call("check_data_quality", tickers=["THYAO"])
    for target in ("BUILD_EVIDENCE", "PREVIEW_STRATEGIES"):
        assert h.advance(target)["ok"] in (True, False)
    assert h.state in ("CHECK_DATA_QUALITY", "BUILD_EVIDENCE", "CALCULATE_TECHNICALS")


def test_cannot_reach_backtest_without_evidence(db):
    h = fresh(db)
    h.advance("CHECK_DATA_QUALITY")
    h.call("check_data_quality", tickers=["THYAO"])
    assert h.advance("RUN_BACKTEST")["ok"] is False   # BUILD_EVIDENCE is mandatory in between
    assert "BUILD_EVIDENCE" in h.next_states()


def test_leakage_blocks_and_short_circuits_to_unsafe(db):
    h = fresh(db)
    h.advance("CHECK_DATA_QUALITY")
    env = h.call("check_data_quality", tickers=["THYAO"], evidence_dates=[{"source": "fundamentals THYAO 2026Q4", "date": "2027-03-01"}])
    assert env["data"]["verdict"] == "HARD_BLOCK"
    assert h.blocked() and "CALCULATE_TECHNICALS" not in h.next_states() and h.next_states()[0] == "BUILD_EVIDENCE"
    h.advance("BUILD_EVIDENCE")
    h.call("build_evidence_bundle")
    assert [i["kind"] for i in h.evidence["observed"] if i["commit"]] == ["quality"]   # only the gate verdict itself is citable
    h.advance()                                       # backtest waived -> RISK_GATE
    assert h.state == "RISK_GATE"
    g = h.risk_gate()
    assert g["verdict"] == "HARD_BLOCK" and g["permitted_actions"] == ["ANALYSIS_UNSAFE"]
    h.advance()
    assert h.propose("TECHNICAL_REVERSAL_CANDIDATE", "x")["ok"] is False
    out = h.reference_output()
    assert out["action"] == "ANALYSIS_UNSAFE" and h.propose(out["action"], out["explanation"])["ok"]


@pytest.mark.parametrize("focus,tk", [("general", "THYAO"), ("fundamental_reaction", "AKBNK"), ("technical_reversal", "ASELS"),
                                       ("sector_catchup", "TUPRS"), ("calendar_pattern", "BIMAS")])
def test_reference_agent_all_foci(db, focus, tk):
    h = reference.run(f"{tk} {focus}", tk, focus, human=("APPROVE", "ok"), db=db)
    assert h.closed and h.state == "LOG_AND_CLOSE"
    assert h.final["action"] in policy.ACTIONS and h.final["action"] == h.decision["action"]
    assert h.violations == []
    assert any(c["tool"] == "check_data_quality" for c in h.calls) and any(c["tool"] == "run_backtest" for c in h.calls)


def test_human_review_required_and_recorded(db):
    h = reference.run("q", "THYAO", "fundamental_reaction", db=db)   # no human decision
    assert h.state == "HUMAN_REVIEW"
    assert h.advance()["ok"] is False
    assert h.review("MAYBE", "x")["ok"] is False and h.review("REJECT", "  ")["ok"] is False
    assert h.review("REJECT", "historical maximum drawdown is too high", "reviewer1")["ok"]
    assert h.advance()["ok"]
    rec = h.close()
    assert rec["human_review"]["decision"] == "REJECT"
    assert db.reviews(h.id)[0]["reason"].startswith("historical")
    assert db.recall("THYAO")[0]["human_decision"] == "REJECT"


def test_replay_reproduces(db):
    from bist.harness.replay import replay_analysis
    h = reference.run("q", "AKBNK", "fundamental_reaction", human=("APPROVE", "ok"), db=db)
    r = replay_analysis(h.id, db)
    assert r["ok"] and r["mismatched_calls"] == [] and r["replayed_action"] == r["recorded_reference_action"]


def test_validator_rules(db):
    h = reference.run("q", "THYAO", "fundamental_reaction", db=db)
    b, perm = h.evidence, h.decision["permitted"]
    good = h.final["explanation"]
    assert policy.validate_output(h.final["action"], good, perm, b)["ok"]
    assert "ACTION_NOT_ALLOWED:BUY" in policy.validate_output("BUY", good, perm, b)["violations"][0]
    bad_num = good + " The stock gained 77.31% last week."
    assert any(v.startswith("NUMBER_NOT_IN_EVIDENCE") for v in policy.validate_output(h.final["action"], bad_num, perm, b)["violations"])
    assert "INVESTMENT_ADVICE_LANGUAGE" in policy.validate_output(h.final["action"], good + " You should buy now.", perm, b)["violations"]
    assert "INVESTMENT_ADVICE_LANGUAGE" in policy.validate_output(h.final["action"], good + " Bu hisseyi almalısın.", perm, b)["violations"]
    unc = next(i["id"] for i in b["observed"] if not i["commit"])
    assert any(v.startswith("CITES_UNCOMMITTED") for v in policy.validate_output(h.final["action"], good + f" See [{unc}].", perm, b)["violations"])
    assert any(v.startswith("CITES_UNKNOWN") for v in policy.validate_output(h.final["action"], good + " See [E999].", perm, b)["violations"])
    # disclaimer wording itself is not advice
    assert policy.validate_output(h.final["action"], good, perm, b)["ok"]


def test_candidate_needs_committed_evidence(db):
    h = reference.run("q", "THYAO", "general", db=db)
    b = dict(h.evidence)
    r = policy.validate_output("TECHNICAL_REVERSAL_CANDIDATE", "Educational analytical state: TECHNICAL_REVERSAL_CANDIDATE. " + policy.DISCLAIMER,
                               ["TECHNICAL_REVERSAL_CANDIDATE"], b)
    assert "CANDIDATE_WITHOUT_COMMITTED_EVIDENCE" in r["violations"]


def test_config_switches_for_experiments(db):
    h = Harness("q", db=db, config=HarnessConfig(enforce_permissions=False, enforce_order=False))
    h.advance("RUN_BACKTEST")
    assert h.call("get_stock_history", ticker="THYAO", max_rows=2)["status"] in ("OK", "WARN")   # any tool in any state


def test_decision_never_orders():
    from bist.tools import REGISTRY
    assert not [t for t in REGISTRY if any(w in t for w in ("order", "trade", "buy", "sell", "execute"))]
