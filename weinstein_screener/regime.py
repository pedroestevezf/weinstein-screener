from __future__ import annotations

import pandas as pd

from weinstein_screener.indicators import ma_slope, moving_average


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
    ma = moving_average(df_weekly, window=ma_window)
    slope = ma_slope(ma, lookback=slope_lookback)

    close_above_ma = df_weekly["Close"] > ma
    ascending_ma = slope > 0

    return close_above_ma & ascending_ma
