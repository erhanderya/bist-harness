import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import bist.tools  # noqa: E402,F401  (registers all tools)
from bist.tools import session  # noqa: E402
from bist.tools.evidence import build_evidence_bundle  # noqa: E402

AS_OF = "2025-06-13"


def full_session(aid, tk="THYAO", quality=True):
    session.new_analysis(aid, as_of=AS_OF)
    if quality:
        session.run(aid, "check_data_quality", tickers=[tk], analysis_type="technical_reversal")
    session.run(aid, "calculate_indicators", ticker=tk)
    session.run(aid, "detect_reversal_events", ticker=tk)
    session.run(aid, "rank_sector_relative_strength", sector=tk)
    session.run(aid, "test_weekday_pattern", ticker=tk, pattern="weekday_return", weekday="THU")
    session.run(aid, "get_fundamental_metrics", ticker=tk)
    session.run(aid, "calculate_fundamental_change", ticker=tk)
    session.run(aid, "get_macro_context")
    session.run(aid, "run_backtest", variant="B", start="2019-01-01")
    return build_evidence_bundle(analysis_id=aid)


def test_bundle_separates_observed_and_committed():
    r = full_session("t1")
    d = r["data"]
    assert r["status"] in ("OK", "WARN") and d["quality_verdict"] in ("PASS", "PASS_WITH_WARNINGS")
    assert d["n_observed"] > d["n_committed"] > 0
    assert set(d["committed_ids"]).isdisjoint({x["id"] for x in d["excluded"]})
    kinds = {x["kind"] for x in d["observed"]}
    assert {"technical", "sector", "pattern", "fundamental", "macro", "backtest", "quality"} <= kinds


def test_market_wide_weekday_effect_is_observed_but_not_committed():
    d = full_session("t2")["data"]
    pat = [x for x in d["observed"] if x["kind"] == "pattern"][0]
    assert pat["commit"] is False and "MARKET_WIDE" in pat["reason"]


def test_every_item_has_id_statement_and_source():
    d = full_session("t3")["data"]
    for it in d["observed"]:
        assert it["id"].startswith("E") and it["statement"] and it["source_call"].startswith("C")


def test_no_quality_gate_means_nothing_committed():
    d = full_session("t4", quality=False)["data"]
    assert d["n_committed"] == 0 and d["quality_verdict"] is None


def test_blocking_verdict_commits_nothing():
    aid = "t5"
    session.new_analysis(aid, as_of=AS_OF)
    session.run(aid, "check_data_quality", tickers=["THYAO", "FAKE1"])
    session.run(aid, "calculate_indicators", ticker="THYAO")
    d = build_evidence_bundle(analysis_id=aid)["data"]
    assert d["quality_verdict"] == "HARD_BLOCK"
    assert all(x["kind"] == "quality" for x in d["observed"] if x["commit"])


def test_tool_errors_are_recorded_not_committed():
    aid = "t6"
    session.new_analysis(aid, as_of=AS_OF)
    session.run(aid, "check_data_quality", tickers=["THYAO"])
    session.run(aid, "calculate_indicators", ticker="NOPE")
    d = build_evidence_bundle(analysis_id=aid)["data"]
    err = [x for x in d["observed"] if x["kind"] == "tool_error"]
    assert len(err) == 1 and err[0]["commit"] is False and "UNKNOWN_TICKER" in err[0]["statement"]


def test_unknown_analysis_and_unknown_tool():
    assert build_evidence_bundle(analysis_id="does-not-exist")["error"]["code"] == "UNKNOWN_ANALYSIS"
    session.new_analysis("t7", as_of=AS_OF)
    assert session.run("t7", "no_such_tool")["error"]["code"] == "UNKNOWN_TOOL"


def test_session_as_of_is_default_for_tools():
    session.new_analysis("t8", as_of="2022-03-01")
    env = session.run("t8", "calculate_indicators", ticker="THYAO")
    assert env["as_of"] == "2022-03-01"


def test_statement_numbers_come_from_tool_output():
    aid = "t9"
    session.new_analysis(aid, as_of=AS_OF)
    env = session.run(aid, "calculate_indicators", ticker="EREGL")
    rsi = env["data"]["values"]["rsi"]
    d = build_evidence_bundle(analysis_id=aid)["data"]
    mom = [x for x in d["observed"] if "RSI(14)" in x["statement"]][0]["statement"]
    assert f"{rsi:.1f}" in mom
