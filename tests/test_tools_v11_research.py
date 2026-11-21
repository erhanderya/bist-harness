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
