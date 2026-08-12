import pandas as pd
import pytest

from weinstein_screener.etapa1 import screen_ticker


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


def test_screen_ticker_is_a_candidate_when_close_and_rising():
    closes = [100.0 + i * 2 for i in range(40)]
    df = _weekly_df(closes)

    result = screen_ticker("AAA", df, distance_pct_threshold=7.5, ma_window=10, slope_lookback=4)

    assert result is not None
    assert result.ma_rising is True
    assert result.distance_pct <= 7.5
    assert result.is_candidate is True


def test_screen_ticker_rejects_when_ma_is_not_rising():
    closes = [100.0] * 40  # precio plano -> MA plana -> pendiente no ascendente
    df = _weekly_df(closes)

    result = screen_ticker("BBB", df, distance_pct_threshold=7.5, ma_window=10, slope_lookback=4)

    assert result is not None
    assert result.ma_rising is False
    assert result.is_candidate is False


def test_screen_ticker_rejects_when_too_far_from_a_rising_ma():
    rising = [100.0 + i * 2 for i in range(19)]
    # Salto grande en la última semana para alejar el precio de la MA
    closes = rising + [400.0]
    df = _weekly_df(closes)

    result = screen_ticker("CCC", df, distance_pct_threshold=7.5, ma_window=10, slope_lookback=4)

    assert result is not None
    assert result.ma_rising is True
    assert result.distance_pct > 7.5
    assert result.is_candidate is False


def test_screen_ticker_returns_none_with_insufficient_history():
    closes = [100.0 + i for i in range(5)]
    df = _weekly_df(closes)

    result = screen_ticker("DDD", df, ma_window=30, slope_lookback=4)

    assert result is None


def test_screen_ticker_distance_pct_is_numerically_correct():
    # 9 semanas planas en 100 + última semana en 121 -> MA(10) = (9*100 + 121)/10 = 102.1
    # distance = |121 - 102.1| / 102.1 * 100
    closes = [100.0] * 9 + [121.0]
    df = _weekly_df(closes)

    result = screen_ticker("EEE", df, ma_window=10, slope_lookback=4, distance_pct_threshold=100)

    ma_last = (9 * 100.0 + 121.0) / 10
    expected_distance = abs(121.0 - ma_last) / ma_last * 100
    assert result is not None
    assert result.distance_pct == pytest.approx(expected_distance)
