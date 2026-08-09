from __future__ import annotations

import pandas as pd


def moving_average(df: pd.DataFrame, window: int, column: str = "Close") -> pd.Series:
    return df[column].rolling(window=window).mean()


def ma_slope(ma: pd.Series, lookback: int) -> pd.Series:
    """Diferencia entre la media móvil actual y `lookback` periodos atrás.

    Positivo = ascendente.
    """
    return ma - ma.shift(lookback)


def average_true_range(df: pd.DataFrame, window: int = 14, method: str = "sma") -> pd.Series:
    """method: "sma" (media móvil simple, comportamiento original) o "wilder"
    (suavizado exponencial estilo Wilder/RMA, el que usan por defecto la
    mayoría de plataformas de trading incluida TradingView). Nota: esta
    implementación de "wilder" usa `ewm(alpha=1/window, adjust=False)`, una
    aproximación estándar — no está sembrada con una media simple inicial
    como el Wilder de libro de texto, así que puede diferir ligeramente en
    las primeras barras antes de converger.
    """
    if method not in ("sma", "wilder"):
        raise ValueError(f"method must be 'sma' or 'wilder', got {method!r}")

    prev_close = df["Close"].shift(1)
    true_range = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    if method == "wilder":
        return true_range.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    return true_range.rolling(window=window).mean()
