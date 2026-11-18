import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bist.tools import events, indicators as ind, store  # noqa: E402
from bist.tools.envelope import REGISTRY  # noqa: E402
from bist.tools.market import get_index_history, get_stock_history  # noqa: E402
from bist.tools.indicators import calculate_indicators  # noqa: E402
from bist.tools.events import detect_reversal_events, find_support_resistance  # noqa: E402


# ------------------------------------------------------------- primitives
def test_rsi_monotone_up_is_100():
    s = pd.Series(np.arange(1, 60, dtype=float))
    assert ind.rsi(s).iloc[-1] == pytest.approx(100.0)


def test_sma_and_bollinger_basic():
    s = pd.Series(np.arange(1, 31, dtype=float))
    assert ind.sma(s, 5).iloc[-1] == pytest.approx(28.0)
    b = ind.bollinger(s, 20, 2.0)
    assert b["bb_mid"].iloc[-1] == pytest.approx(20.5)
    assert b["bb_upper"].iloc[-1] > b["bb_mid"].iloc[-1] > b["bb_lower"].iloc[-1]


def test_kama_constant_series_is_constant():
    s = pd.Series([10.0] * 50)
    assert ind.kama(s).dropna().eq(10.0).all()


def test_supertrend_uptrend_direction_up():
    n = 80
    c = pd.Series(np.linspace(100, 200, n))
    df = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1.0})
    assert ind.supertrend(df)["st_dir"].iloc[-1] == 1


# ------------------------------------------------------------- no look-ahead invariants (real data)
@pytest.fixture(scope="module")
def thyao():
    return store.stock_bars("THYAO", store.data_last_date())


def test_indicator_frame_is_causal(thyao):
    full = ind.indicator_frame(thyao)
    for cut in (-300, -120, -40):
        part = ind.indicator_frame(thyao.iloc[:cut])
        a, b = full.loc[part.index], part
        pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9, atol=1e-9)


def test_event_flags_are_causal(thyao):
    f_full = ind.indicator_frame(thyao)
    e_full = events.event_flags(f_full)
    cut = len(thyao) - 200
    e_part = events.event_flags(ind.indicator_frame(thyao.iloc[:cut]))
    pd.testing.assert_frame_equal(e_full.iloc[:cut], e_part)


def test_pivots_are_confirmed_only(thyao):
    k = 5
    pv_full = events.pivots(thyao, k)
    cut = len(thyao) - 100
    pv_part = events.pivots(thyao.iloc[:cut], k)
    # truncated run may only contain pivots that are also in the full run, and none from the last k bars
    assert set(pv_part["date"]) <= set(pv_full["date"])
    assert pv_part["date"].max() <= thyao.index[cut - 1 - k]


# ------------------------------------------------------------- tool contract
def test_registry_has_market_tools():
    for name in ("get_stock_history", "get_index_history", "calculate_indicators", "detect_reversal_events", "find_support_resistance"):
        assert name in REGISTRY


def test_unknown_ticker_is_structured_error():
    r = calculate_indicators(ticker="ABCDE")
    assert r["status"] == "ERROR" and r["error"]["code"] == "UNKNOWN_TICKER" and r["data"] is None


def test_invalid_params_is_structured_error():
    r = get_stock_history(ticker="THYAO", max_rows=0)
    assert r["status"] == "ERROR" and r["error"]["code"] == "INVALID_PARAMS"


def test_ticker_normalisation_and_as_of_cut():
    r = get_stock_history(ticker="thyao.is", as_of="2022-06-30", max_rows=5)
    assert r["status"] in ("OK", "WARN")
    assert r["data"]["ticker"] == "THYAO"
    assert all(row["date"] <= "2022-06-30" for row in r["data"]["rows"])
    assert r["as_of"] == "2022-06-30"
    assert len(r["data"]["rows"]) == 5


def test_as_of_after_data_is_clamped_with_warning():
    r = get_index_history(as_of="2099-01-01")
    assert any(w["code"] == "AS_OF_CLAMPED" for w in r["warnings"])
    assert r["as_of"] == str(store.data_last_date().date())


def test_indicators_at_old_as_of_use_no_future():
    r = calculate_indicators(ticker="AKBNK", as_of="2021-03-15")
    assert r["data"]["date"] <= "2021-03-15"
    r2 = calculate_indicators(ticker="AKBNK", as_of="2021-03-15")
    assert r["provenance"]["result_hash"] == r2["provenance"]["result_hash"]  # deterministic


def test_reversal_forward_returns_only_complete_horizons():
    r = detect_reversal_events(ticker="THYAO", as_of="2024-06-14", direction="both", recent_days=3)
    assert r["status"] in ("OK", "WARN")
    last_bar = r["provenance"]["last_bar_date"]
    for ev in r["data"]["recent_events"]:
        assert ev["date"] <= last_bar
        # a 10-day horizon cannot be complete for an event within the last 3 bars
        assert ev["fwd_returns"]["10d"] is None


def test_unknown_event_type():
    r = detect_reversal_events(ticker="THYAO", event_types=["nope"])
    assert r["error"]["code"] == "UNKNOWN_EVENT_TYPE"


def test_support_resistance_levels_sorted_around_price():
    r = find_support_resistance(ticker="EREGL", as_of="2023-12-29")
    d = r["data"]
    assert all(s["level"] < d["last_close"] for s in d["supports"])
    assert all(s["level"] >= d["last_close"] for s in d["resistances"])


# ------------------------------------------------------------- sector + weekday pattern tools
from bist.tools.research import pattern_stats, rank_sector_relative_strength, test_weekday_pattern  # noqa: E402


def test_sector_ranking_basic():
    r = rank_sector_relative_strength(sector="Financials", horizon_days=10, as_of="2024-06-14")
    d = r["data"]
    assert d["ranking_valid"] and d["n_members"] >= 3
    ranks = [x["lag_rank"] for x in d["ranking_lagging_first"]]
    assert ranks == sorted(ranks)
    scores = [x["lag_score"] for x in d["ranking_lagging_first"]]
    assert scores == sorted(scores, reverse=True)  # most lagging first


def test_sector_by_ticker_and_single_member_group():
    assert rank_sector_relative_strength(sector="THYAO")["data"]["sector"] == "Transport"
    r = rank_sector_relative_strength(sector="Defense_Tech")  # ASELS alone
    assert r["data"]["ranking_valid"] is False
    assert any(w["code"] == "PEER_GROUP_TOO_SMALL" for w in r["warnings"])


def test_unknown_sector():
    assert rank_sector_relative_strength(sector="Crypto")["error"]["code"] == "UNKNOWN_SECTOR"


def test_weekday_pattern_requires_weekday_and_flags_noise():
    assert test_weekday_pattern(ticker="THYAO", pattern="weekday_return")["error"]["code"] == "MISSING_PARAM"
    r = test_weekday_pattern(ticker="THYAO", pattern="weekday_return", weekday="MON", as_of="2024-12-31")
    d = r["data"]
    assert d["occurrences"] > 100 and 0 <= d["p_value"] <= 1
    assert d["p_value_bonferroni"] >= d["p_value"]
    assert d["period"][1] <= "2024-12-31"


def test_shuffled_returns_are_rarely_significant():
    # permute each stock's daily returns (destroys weekday structure, keeps the calendar): the multiple-testing +
    # out-of-sample guard must make 'significant & stable' rare
    end = store.data_last_date()
    start = end - pd.DateOffset(years=5)
    hits, total = 0, 0
    for seed in range(8):  # fixed seeds -> deterministic; 8 x 150 = 1200 tests
        rng = np.random.default_rng(seed)
        for tk in store.tickers():
            r = store.stock_bars(tk, end)["close"].pct_change().dropna()
            close = (1 + pd.Series(rng.permutation(r.to_numpy()), index=r.index)).cumprod()
            for wd in ("MON", "TUE", "WED", "THU", "FRI"):
                total += 1
                hits += pattern_stats(close, "weekday_return", wd, 3, start, end, 5)["significant_and_stable"]
    assert hits / total <= 0.02, (hits, total)  # nominal Bonferroni-5 level is 1% (measured 1.0% over 20 seeds); 2% = 3 s.d. margin


def test_real_weekday_effect_is_flagged_market_wide():
    r = test_weekday_pattern(ticker="THYAO", pattern="weekday_return", weekday="THU", as_of="2025-12-31")
    d = r["data"]
    assert d["market_wide_effect"] is True and d["stock_specific_evidence"] is False
    assert any(w["code"] == "MARKET_WIDE_EFFECT" for w in r["warnings"])
