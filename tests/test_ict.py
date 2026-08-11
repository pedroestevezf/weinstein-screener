import pandas as pd
import pytest

from weinstein_screener.ict import find_fair_value_gap, find_order_block


def _daily_df(rows):
    dates = pd.date_range("2020-01-06", periods=len(rows), freq="D")
    return pd.DataFrame(rows, index=dates)


def test_find_order_block_locates_the_last_bearish_candle():
    rows = [
        {"Open": 105, "High": 107, "Low": 103, "Close": 104, "Volume": 500_000},
        {"Open": 102, "High": 103, "Low": 97, "Close": 98, "Volume": 900_000},
        {"Open": 98, "High": 99, "Low": 96, "Close": 97, "Volume": 400_000},  # OB, índice 2
        {"Open": 97, "High": 106, "Low": 96.5, "Close": 105, "Volume": 800_000},
    ]
    df = _daily_df(rows)

    result = find_order_block(df, impulse_end_index=3, lookback=10)

    assert result == 2


def test_find_order_block_returns_none_without_a_bearish_candle_in_range():
    rows = [
        {"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 500_000},
        {"Open": 101, "High": 103, "Low": 100, "Close": 102, "Volume": 500_000},
        {"Open": 102, "High": 104, "Low": 101, "Close": 103, "Volume": 500_000},
    ]
    df = _daily_df(rows)

    result = find_order_block(df, impulse_end_index=3, lookback=10)

    assert result is None


def test_find_fair_value_gap_locates_a_valid_gap():
    calm = [{"Open": 100, "High": 101, "Low": 99, "Close": 100.3, "Volume": 400_000} for _ in range(25)]
    rows = calm + [
        {"Open": 100, "High": 101, "Low": 99.5, "Close": 100.5, "Volume": 400_000},   # vela1, índice 25
        {"Open": 101, "High": 108, "Low": 100.8, "Close": 107.5, "Volume": 900_000},  # vela2, índice 26
        {"Open": 107, "High": 109, "Low": 105, "Close": 108, "Volume": 500_000},      # vela3, índice 27
    ]
    df = _daily_df(rows)
    atr = pd.Series([1.5] * len(df), index=df.index)

    result = find_fair_value_gap(df, start_index=0, end_index=len(df) - 1, atr=atr)

    assert result == 26


def test_find_fair_value_gap_returns_none_when_wicks_overlap():
    calm = [{"Open": 100, "High": 101, "Low": 99, "Close": 100.3, "Volume": 400_000} for _ in range(25)]
    rows = calm + [
        {"Open": 100, "High": 101, "Low": 99.5, "Close": 100.5, "Volume": 400_000},
        {"Open": 101, "High": 108, "Low": 100.8, "Close": 107.5, "Volume": 900_000},
        {"Open": 107, "High": 109, "Low": 100.5, "Close": 108, "Volume": 500_000},  # vela3: Low solapa vela1 High (101)
    ]
    df = _daily_df(rows)
    atr = pd.Series([1.5] * len(df), index=df.index)

    result = find_fair_value_gap(df, start_index=0, end_index=len(df) - 1, atr=atr)

    assert result is None
