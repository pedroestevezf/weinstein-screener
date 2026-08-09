from __future__ import annotations

import pandas as pd


def moving_average(df: pd.DataFrame, window: int, column: str = "Close") -> pd.Series:
    return df[column].rolling(window=window).mean()


def ma_slope(ma: pd.Series, lookback: int) -> pd.Series:
    """Diferencia entre la media móvil actual y `lookback` periodos atrás.

    Positivo = ascendente.
    """
    return ma - ma.shift(lookback)


def average_true_range(df: pd.DataFrame, window: int = 14) -> pd.Series:
    prev_close = df["Close"].shift(1)
    true_range = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window=window).mean()
