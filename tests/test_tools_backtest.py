import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bist.tools.backtest import generate_strategy_variants, run_backtest  # noqa: E402

END = "2024-12-31"


def bt(variant="A", **kw):
    return run_backtest(variant=variant, start="2017-01-01", end=END, as_of=END, **kw)


def test_variants_listed_and_E_not_backtestable():
    d = generate_strategy_variants()["data"]["variants"]
    assert [v["variant"] for v in d] == list("ABCDE")
    assert d[4]["backtestable"] is False and d[4]["spec"] is None
    r = bt("E")
    assert r["status"] == "ERROR" and r["error"]["code"] == "LAYER_UNAVAILABLE"


def test_param_validation():
    assert run_backtest()["error"]["code"] == "INVALID_PARAMS"
    r = run_backtest(variant="A", spec={"name": "x"})
    assert r["error"]["code"] == "INVALID_PARAMS"
    r = run_backtest(spec={"trigger_events": ["supertrend_flip_down"]})
    assert r["error"]["code"] == "UNKNOWN_EVENT_TYPE"


def test_signal_shift_and_no_trade_after_end():
    r = bt("A")
    assert r["status"] in ("OK", "WARN")
    for t in r["data"]["last_10_trades"]:
        assert t["entry_date"] > t["signal_date"]          # decision at t, entry at t+1
        assert t["exit_date"] <= END
    assert "signal at close t" in r["data"]["assumptions"]["signal_shift"]


def test_result_does_not_depend_on_data_after_as_of():
    full = run_backtest(variant="B", start="2017-01-01", end="2022-12-30", as_of="2026-11-16")
    cut = run_backtest(variant="B", start="2017-01-01", end="2022-12-30", as_of="2022-12-30")
    assert full["data"]["n_trades_total"] == cut["data"]["n_trades_total"] > 0
    assert full["data"]["last_10_trades"] == cut["data"]["last_10_trades"]
    assert full["data"]["signal_level"] == cut["data"]["signal_level"]
    assert full["data"]["portfolio"] == cut["data"]["portfolio"]


def test_more_filters_fewer_trades_and_costs_hurt():
    a, b, c, d = (bt(v)["data"]["n_trades_total"] for v in "ABCD")
    assert a > b > 0 and b >= c and c >= d
    cheap = bt("A", cost_bps_per_side=0, slippage_bps_per_side=0)["data"]["signal_level"]["mean_net_return"]
    dear = bt("A", cost_bps_per_side=50, slippage_bps_per_side=20)["data"]["signal_level"]["mean_net_return"]
    assert cheap > dear


def test_split_periods_and_flags_present():
    r = bt("D")
    d = r["data"]
    assert set(d["by_period"]) == {"train", "validation", "test"}
    assert d["benchmarks"]["xu100_total_return"] is not None
    codes = {w["code"] for w in r["warnings"]}
    assert "FUNDAMENTAL_FILTER_RATIOS_ONLY" in codes
    assert 0 <= d["portfolio"]["exposure_days_pct"] <= 1 and d["portfolio"]["max_drawdown"] <= 0
