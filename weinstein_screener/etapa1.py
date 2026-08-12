from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from weinstein_screener.indicators import moving_average, pct_distance_from_ma
from weinstein_screener.regime import ma_rising


@dataclass
class Etapa1Candidate:
    ticker: str
    distance_pct: float
    ma_rising: bool
    is_candidate: bool


def screen_ticker(
    ticker: str,
    df_weekly: pd.DataFrame,
    distance_pct_threshold: float = 7.5,
    ma_window: int = 30,
    slope_lookback: int = 4,
) -> Etapa1Candidate | None:
    """Evalúa Etapa 1 (pre-screening grueso) para un ticker sobre la última
    semana cerrada de `df_weekly`: distancia porcentual del precio a la
    MA30w y si esa media tiene pendiente ascendente. `None` si no hay
    histórico suficiente para calcular la MA (`len(df_weekly) < ma_window`).
    """
    if len(df_weekly) < ma_window:
        return None

    ma = moving_average(df_weekly, window=ma_window)
    distance = pct_distance_from_ma(df_weekly["Close"], ma)
    rising = ma_rising(df_weekly, ma_window=ma_window, slope_lookback=slope_lookback)

    distance_pct = float(distance.iloc[-1])
    is_rising = bool(rising.iloc[-1])

    return Etapa1Candidate(
        ticker=ticker,
        distance_pct=distance_pct,
        ma_rising=is_rising,
        is_candidate=distance_pct <= distance_pct_threshold and is_rising,
    )
