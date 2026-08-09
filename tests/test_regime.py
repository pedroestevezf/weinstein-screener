import pandas as pd

from weinstein_screener.regime import weinstein_stage2_active


def _weekly_df(closes):
    dates = pd.date_range("2020-01-06", periods=len(closes), freq="W-MON")
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c + 1 for c in closes],
            "Low": [c - 1 for c in closes],
            "Close": closes,
            "Volume": [1000] * len(closes),
        },
        index=dates,
    )


def test_stage2_is_false_while_price_stays_flat():
    closes = [100.0] * 40
    df = _weekly_df(closes)

    result = weinstein_stage2_active(df, ma_window=30, slope_lookback=4)

    assert not result.any()


def test_stage2_becomes_true_once_price_breaks_above_a_rising_average():
    flat = [100.0] * 30
    rising = [100.0 + i * 2 for i in range(1, 15)]
    closes = flat + rising
    df = _weekly_df(closes)

    result = weinstein_stage2_active(df, ma_window=30, slope_lookback=4)

    assert not result.iloc[29]
    assert result.iloc[-1]
