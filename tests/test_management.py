import pandas as pd
import pytest

from weinstein_screener.management import find_entry_2_signal, evaluate_position_management


def _weekly_df(rows):
    dates = pd.date_range("2020-01-06", periods=len(rows), freq="W-MON")
    return pd.DataFrame(rows, index=dates)


def test_find_entry_2_signal_composes_price_and_stop_loss():
    rows = [{"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 500_000} for _ in range(7)]
    rows.append({"Open": 118, "High": 125, "Low": 117, "Close": 124, "Volume": 900_000})  # JAC, índice 7
    rows.append({"Open": 124, "High": 128, "Low": 123, "Close": 126, "Volume": 700_000})
    df = _weekly_df(rows)
    atr = pd.Series([2.0] * len(df), index=df.index)

    result = find_entry_2_signal(df, jac_index=7, atr_weekly=atr, sl_atr_multiplier=1.5)

    assert result is not None
    assert result.trigger_index == 7
    assert result.entry_price == pytest.approx(124)
    assert result.stop_loss == pytest.approx(121.0)


def test_find_entry_2_signal_returns_none_without_a_jac():
    rows = [{"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 500_000} for _ in range(5)]
    df = _weekly_df(rows)
    atr = pd.Series([2.0] * len(df), index=df.index)

    result = find_entry_2_signal(df, jac_index=None, atr_weekly=atr)

    assert result is None


def test_evaluate_position_management_flags_breakeven_when_entry2_triggers():
    result = evaluate_position_management(entry1_triggered=True, entry1_stopped_out=False, entry2_triggered=True)

    assert result.move_entry1_to_breakeven is True
    assert result.resize_entry2_pct is None
    assert result.resize_entry3_pct is None


def test_evaluate_position_management_resizes_after_a_failed_spring():
    result = evaluate_position_management(entry1_triggered=True, entry1_stopped_out=True, entry2_triggered=False)

    assert result.move_entry1_to_breakeven is False
    assert result.resize_entry2_pct == pytest.approx(42.857, abs=0.01)
    assert result.resize_entry3_pct == pytest.approx(57.143, abs=0.01)
