import math

import pandas as pd
import pytest

from weinstein_screener.wyckoff import (
    find_automatic_rally,
    find_secondary_test,
    find_selling_climax_candidates,
    select_most_recent_sc,
)


def _weekly_df(rows):
    dates = pd.date_range("2020-01-06", periods=len(rows), freq="W-MON")
    return pd.DataFrame(rows, index=dates)


def _wyckoff_scenario_rows():
    """Escenario sintético verificado end-to-end (ver docs/superpowers/plans/2026-08-09-plan2-wyckoff-crt-structure.md):
    SC en índice 15, AR en 20, ST en 24, Spring en 35, Distribution en 39.
    """
    rows = []
    price = 150.0
    for _ in range(15):
        price -= 1.5
        rows.append({"Open": price + 1, "High": price + 2, "Low": price - 1, "Close": price, "Volume": 1_000_000})
    sc_low = price - 15
    rows.append({"Open": price - 1, "High": price + 1, "Low": sc_low, "Close": price - 5, "Volume": 5_000_000})
    price = price - 5
    for _ in range(5):
        price += 3
        rows.append({"Open": price - 3, "High": price + 1, "Low": price - 4, "Close": price, "Volume": 900_000})
    for _ in range(3):
        price -= 2
        rows.append({"Open": price + 2, "High": price + 3, "Low": price - 1, "Close": price, "Volume": 800_000})
    rows.append({"Open": 122, "High": 123, "Low": 115.0, "Close": 121, "Volume": 700_000})
    for i in range(10):
        c = 122 + math.sin(i) * 5
        rows.append({"Open": c - 1, "High": c + 3, "Low": c - 3, "Close": c, "Volume": 600_000 + i * 5000})
    rows.append({"Open": 114, "High": 116, "Low": 108, "Close": 113, "Volume": 900_000})
    for i in range(3):
        c = 118 + i
        rows.append({"Open": c - 1, "High": c + 2, "Low": c - 2, "Close": c, "Volume": 500_000})
    rows.append({"Open": 138, "High": 144, "Low": 137, "Close": 141, "Volume": 950_000})
    return rows


def test_find_selling_climax_candidates_flags_the_climax_week():
    rows = _wyckoff_scenario_rows()[:16]  # hasta el SC (índice 15) incluido
    df = _weekly_df(rows)

    candidates = find_selling_climax_candidates(df)

    assert candidates.iloc[15]
    assert not candidates.iloc[:15].any()


def test_find_selling_climax_candidates_none_in_calm_data():
    rows = [{"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 500_000} for _ in range(30)]
    df = _weekly_df(rows)

    candidates = find_selling_climax_candidates(df)

    assert not candidates.any()


def test_select_most_recent_sc_returns_the_climax_index():
    rows = _wyckoff_scenario_rows()  # escenario completo de 40 semanas
    df = _weekly_df(rows)
    candidates = find_selling_climax_candidates(df)

    result = select_most_recent_sc(candidates, as_of=len(df) - 1, search_window=52)

    assert result == 15


def test_select_most_recent_sc_returns_none_when_no_candidate():
    rows = [{"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 500_000} for _ in range(30)]
    df = _weekly_df(rows)
    candidates = find_selling_climax_candidates(df)

    result = select_most_recent_sc(candidates, as_of=29, search_window=52)

    assert result is None


def test_find_automatic_rally_locates_the_rally_peak():
    rows = _wyckoff_scenario_rows()[:21]  # hasta el AR (índice 20) incluido
    df = _weekly_df(rows)

    result = find_automatic_rally(df, sc_index=15, window=12)

    assert result == 20


def test_find_automatic_rally_returns_none_when_sc_is_the_last_row():
    rows = [{"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 500_000} for _ in range(10)]
    df = _weekly_df(rows)

    result = find_automatic_rally(df, sc_index=9, window=12)

    assert result is None


def test_find_secondary_test_locates_the_retest():
    rows = _wyckoff_scenario_rows()[:25]  # hasta el ST (índice 24) incluido
    df = _weekly_df(rows)

    result = find_secondary_test(df, sc_index=15, ar_index=20, window=12)

    assert result == 24


def test_find_secondary_test_returns_none_when_price_never_retests():
    rows = [{"Open": 100, "High": 101, "Low": 90, "Close": 95, "Volume": 2_000_000}]  # SC en índice 0
    for i in range(15):
        rows.append({"Open": 150 + i, "High": 152 + i, "Low": 149 + i, "Close": 151 + i, "Volume": 400_000})
    df = _weekly_df(rows)

    ar_index = find_automatic_rally(df, sc_index=0, window=12)
    result = find_secondary_test(df, sc_index=0, ar_index=ar_index, window=12)

    assert result is None
