from __future__ import annotations

import pandas as pd

from weinstein_screener.indicators import ma_slope, moving_average


def close_above_ma(df_weekly: pd.DataFrame, ma_window: int = 30) -> pd.Series:
    """Serie booleana: True cuando el cierre semanal está por encima de la media móvil."""
    ma = moving_average(df_weekly, window=ma_window)
    return df_weekly["Close"] > ma


def ma_rising(df_weekly: pd.DataFrame, ma_window: int = 30, slope_lookback: int = 4) -> pd.Series:
    """Serie booleana: True cuando la media móvil tiene pendiente ascendente."""
    ma = moving_average(df_weekly, window=ma_window)
    slope = ma_slope(ma, lookback=slope_lookback)
    return slope > 0


def weinstein_stage2_active(
    df_weekly: pd.DataFrame,
    ma_window: int = 30,
    slope_lookback: int = 4,
) -> pd.Series:
    """Serie booleana por semana: True cuando se confirma Weinstein Stage 2.

    Stage 2 requiere: cierre semanal por encima de la media móvil, y la
    media con pendiente ascendente (valor actual mayor que hace
    `slope_lookback` semanas).
    """
    return close_above_ma(df_weekly, ma_window) & ma_rising(df_weekly, ma_window, slope_lookback)
