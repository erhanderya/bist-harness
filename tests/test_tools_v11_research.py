import numpy as np
import pandas as pd
import pytest

from bist.tools.research import rank_sector_relative_strength, test_weekday_pattern
from conftest import assert_causal


# ------------------------------------------------------------- rank_sector_relative_strength (Q1)
def test_custom_group_retail_q1():
    r = rank_sector_relative_strength(tickers=["BIMAS", "MGROS", "MAVI"], horizon_days=20, as_of="2026-09-10")
    d = r["data"]
    assert r["status"] in ("OK", "WARN") and d["custom_group"] and d["n_members"] == 3
    worst = d["ranking_lagging_first"][0]
    assert worst["lag_gap"] == pytest.approx(worst["excess_vs_sector_median"]) and worst["lag_gap"] <= 0


def test_custom_group_unknown_and_duplicate_tickers():
    assert rank_sector_relative_strength(tickers=["BIMAS", "XXXX", "MAVI"])["error"]["code"] == "UNKNOWN_TICKER"
    d = rank_sector_relative_strength(tickers=["BIMAS", "bimas", "MGROS", "MAVI"])["data"]
    assert d["n_members"] == 3


def test_rank_sector_v10_call_unchanged():
    d = rank_sector_relative_strength(sector="THYAO", horizon_days=10, as_of="2026-09-10")["data"]
    assert d["custom_group"] is False and d["sector"] == "Transport"


def test_rank_sector_needs_sector_or_tickers():
    assert rank_sector_relative_strength(horizon_days=10)["error"]["code"] == "MISSING_PARAM"


def test_rank_sector_causal(truncate_store):
    assert_causal(rank_sector_relative_strength, "2026-09-10", truncate_store, tickers=["BIMAS", "MGROS", "MAVI"], horizon_days=20)


# ------------------------------------------------------------- test_weekday_pattern: weekday_sequence (Q2)
from bist.tools.research import sequence_stats  # noqa: E402


def test_sequence_stats_synthetic():
    idx = pd.bdate_range("2024-01-01", "2024-12-31")
    r = pd.Series(0.0, index=idx)
    r[idx.dayofweek <= 2] = -0.01
    r[idx.dayofweek >= 3] = 0.01
    close = (1 + r).cumprod() * 100
    d = sequence_stats(close, ["MON", "TUE", "WED"], ["THU", "FRI"], idx[0], idx[-1], 1, 30)
    assert d["occurrences"] == d["full_pattern_count"] > 40 and d["hit_rate"] == 1.0
    assert d["mean"] == pytest.approx(1.01 ** 2 - 1) and d["net_mean_after_cost"] == pytest.approx(d["mean"] - 0.003)


def test_weekday_sequence_skips_incomplete_weeks():
    idx = pd.bdate_range("2023-12-25", "2024-03-29").drop(pd.Timestamp("2024-01-02"))  # week of 2024-01-01 has no TUE
    close = pd.Series(np.linspace(100, 90, len(idx)), index=idx)
    d = sequence_stats(close, ["MON", "TUE", "WED"], ["THU", "FRI"], pd.Timestamp("2024-01-01"), idx[-1], 1, 30)
    assert d["n_weeks_total"] == 12          # 13 weeks, one dropped


def test_weekday_sequence_q2_is_oos():
    r = test_weekday_pattern(ticker="THYAO", pattern="weekday_sequence", down_days=["MON", "TUE", "WED"], up_days=["THU", "FRI"],
                             start="2024-01-01", end="2026-09-10", oos_start="2026-01-01", as_of="2026-09-10")
    assert r["status"] != "ERROR", r["error"]
    d = r["data"]
    assert d["in_sample"]["period"][1] < "2026-01-01" <= d["out_of_sample"]["period"][0]
    assert "in_sample_70pct" not in d and "net_mean_after_cost" in d["in_sample"]
    assert d["xu100_reference"]["occurrences"] is not None


def test_weekday_sequence_requires_days():
    assert test_weekday_pattern(ticker="THYAO", pattern="weekday_sequence")["error"]["code"] == "MISSING_PARAM"
    r = test_weekday_pattern(ticker="THYAO", pattern="weekday_sequence", down_days=["MON"], up_days=["MON", "FRI"])
    assert r["error"]["code"] == "INVALID_PARAMS"


def test_oos_start_outside_range_rejected():
    r = test_weekday_pattern(ticker="THYAO", pattern="weekday_return", weekday="MON", start="2024-01-01", end="2025-01-01", oos_start="2026-01-01")
    assert r["error"]["code"] == "INVALID_DATE_RANGE"


def test_weekday_v10_unchanged():
    d = test_weekday_pattern(ticker="THYAO", pattern="weekday_return", weekday="MON", as_of="2026-09-10")["data"]
    assert "in_sample_70pct" in d and "in_sample" not in d


def test_weekday_sequence_causal(truncate_store):
    assert_causal(test_weekday_pattern, "2026-09-10", truncate_store, ticker="THYAO", pattern="weekday_sequence",
                  down_days=["MON", "TUE", "WED"], up_days=["THU", "FRI"], start="2024-01-01", oos_start="2026-01-01")
