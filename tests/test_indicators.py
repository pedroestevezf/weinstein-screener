import pandas as pd
import pytest

from weinstein_screener.indicators import average_true_range, ma_slope, moving_average


def _sample_df():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    return pd.DataFrame(
        {
            "Open": [10, 11, 12, 13, 14, 15],
            "High": [11, 12, 13, 14, 15, 16],
            "Low": [9, 10, 11, 12, 13, 14],
            "Close": [10, 11, 12, 13, 14, 15],
            "Volume": [100, 100, 100, 100, 100, 100],
        },
        index=dates,
    )


def test_moving_average_computes_rolling_mean():
    df = _sample_df()
    ma = moving_average(df, window=3)

    assert pd.isna(ma.iloc[0])
    assert pd.isna(ma.iloc[1])
    assert ma.iloc[2] == pytest.approx(11.0)
    assert ma.iloc[5] == pytest.approx(14.0)


def test_ma_slope_is_positive_for_rising_series():
    df = _sample_df()
    ma = moving_average(df, window=3)
    slope = ma_slope(ma, lookback=2)

    assert slope.iloc[4] == pytest.approx(ma.iloc[4] - ma.iloc[2])
    assert slope.iloc[4] > 0


def test_average_true_range_matches_manual_calculation():
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    df = pd.DataFrame(
        {
            "Open": [10, 12, 11, 15],
            "High": [11, 14, 13, 18],
            "Low": [9, 10, 10, 12],
            "Close": [10, 12, 12, 16],
            "Volume": [100, 100, 100, 100],
        },
        index=dates,
    )

    atr = average_true_range(df, window=2)

    # True Range: día0=2 (sin prevClose), día1=max(4,4,0)=4, día2=max(3,1,2)=3, día3=max(6,6,0)=6
    # ATR (media móvil de ventana 2 sobre True Range):
    # día1=mean(2,4)=3.0, día2=mean(4,3)=3.5, día3=mean(3,6)=4.5
    assert atr.iloc[1] == pytest.approx(3.0)
    assert atr.iloc[2] == pytest.approx(3.5)
    assert atr.iloc[3] == pytest.approx(4.5)


def test_average_true_range_wilder_method_differs_from_sma():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    df = pd.DataFrame(
        {
            "Open": [10, 12, 11, 15, 13, 17],
            "High": [11, 14, 13, 18, 16, 20],
            "Low": [9, 10, 10, 12, 11, 14],
            "Close": [10, 12, 12, 16, 14, 18],
            "Volume": [100] * 6,
        },
        index=dates,
    )

    atr_sma = average_true_range(df, window=3, method="sma")
    atr_wilder = average_true_range(df, window=3, method="wilder")

    assert atr_sma.iloc[-1] != pytest.approx(atr_wilder.iloc[-1])


def test_average_true_range_rejects_invalid_method():
    dates = pd.date_range("2024-01-01", periods=2, freq="D")
    df = pd.DataFrame(
        {"Open": [10, 11], "High": [11, 12], "Low": [9, 10], "Close": [10, 11], "Volume": [100, 100]},
        index=dates,
    )

    with pytest.raises(ValueError, match="method"):
        average_true_range(df, method="bogus")
