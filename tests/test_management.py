import math
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from weinstein_screener.management import find_entry_2_signal, evaluate_position_management, project_range_target, evaluate_exit_signal
from weinstein_screener.wyckoff import detect_wyckoff_structure


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


def test_project_range_target_projects_the_range_amplitude_from_entry():
    result = project_range_target(entry_price=124.0, range_high=124.0, range_low=108.0)

    assert result == pytest.approx(140.0)


def test_project_range_target_returns_none_with_inconsistent_range():
    result = project_range_target(entry_price=124.0, range_high=100.0, range_low=108.0)

    assert result is None


def test_evaluate_exit_signal_flags_partial_at_the_range_target():
    result = evaluate_exit_signal(current_close=140.0, range_target=138.5, current_week_close_above_ma=True)

    assert result.partial_take_profit is True
    assert result.full_exit is False


def test_evaluate_exit_signal_flags_full_exit_below_the_ma30w():
    result = evaluate_exit_signal(current_close=120.0, range_target=138.5, current_week_close_above_ma=False)

    assert result.partial_take_profit is False
    assert result.full_exit is True


def test_evaluate_exit_signal_full_exit_fires_even_after_the_partial_target():
    result = evaluate_exit_signal(current_close=140.0, range_target=138.5, current_week_close_above_ma=False)

    assert result.partial_take_profit is True
    assert result.full_exit is True


def test_evaluate_exit_signal_handles_a_missing_range_target():
    result = evaluate_exit_signal(current_close=120.0, range_target=None, current_week_close_above_ma=False)

    assert result.partial_take_profit is False
    assert result.full_exit is True


def _wyckoff_scenario_rows():
    """Mismo escenario sintético verificado del Plan 2: SC=15, AR=20, ST=24,
    Spring=35, JAC=39 (range_low=112.5, range_high=138.5)."""
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


def test_management_pipeline_composes_end_to_end_with_a_real_wyckoff_structure():
    df = _weekly_df(_wyckoff_scenario_rows())
    structure = detect_wyckoff_structure(df)
    atr = pd.Series([2.0] * len(df), index=df.index)

    entry2 = find_entry_2_signal(df, structure.jac_index, atr)
    target = project_range_target(entry2.entry_price, structure.range_high, structure.range_low)
    exit_signal = evaluate_exit_signal(current_close=170.0, range_target=target, current_week_close_above_ma=True)

    assert entry2.trigger_index == 39
    assert entry2.entry_price == pytest.approx(141.0)
    assert target == pytest.approx(167.0)
    assert exit_signal.partial_take_profit is True


def test_old_terminology_does_not_reappear_in_the_package():
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        ["grep", "-rniE", "distribution_index|find_distribution|RetestResult|find_retest\\b|retest_index",
         "weinstein_screener/"],
        capture_output=True, text=True, cwd=repo_root,
    )
    assert result.stdout == "", f"Terminología antigua reintroducida:\n{result.stdout}"
