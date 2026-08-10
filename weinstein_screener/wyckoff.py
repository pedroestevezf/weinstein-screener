from __future__ import annotations

import numpy as np
import pandas as pd


def find_selling_climax_candidates(
    df: pd.DataFrame,
    range_lookback: int = 10,
    volume_lookback: int = 12,
    volume_percentile: float = 80,
    range_multiplier: float = 2.0,
    new_low_lookback: int = 10,
) -> pd.Series:
    """Serie booleana: True en semanas candidatas a Selling Climax.

    Una semana es candidata si su rango (High-Low) supera `range_multiplier`
    veces el rango medio de las `range_lookback` semanas previas, su volumen
    supera el percentil `volume_percentile` de las `volume_lookback` semanas
    previas, y su mínimo es un nuevo mínimo de `new_low_lookback` semanas
    (confirma que hay una tendencia bajista previa real). Todas las ventanas
    usan `.shift(1)` para no incluir la propia semana evaluada (sin look-ahead).
    """
    week_range = df["High"] - df["Low"]
    avg_range = week_range.shift(1).rolling(range_lookback).mean()
    volume_threshold = (
        df["Volume"].shift(1).rolling(volume_lookback).apply(lambda s: np.percentile(s, volume_percentile))
    )
    prior_low = df["Low"].shift(1).rolling(new_low_lookback).min()
    is_new_low = df["Low"] < prior_low

    return (week_range > range_multiplier * avg_range) & (df["Volume"] > volume_threshold) & is_new_low


def select_most_recent_sc(candidates: pd.Series, as_of: int, search_window: int = 52) -> int | None:
    """Posición entera del candidato a SC más reciente dentro de la ventana
    `[as_of - search_window + 1, as_of]`, o None si no hay ninguno.
    """
    start = max(0, as_of - search_window + 1)
    window = candidates.iloc[start : as_of + 1]
    true_positions = window[window].index
    if len(true_positions) == 0:
        return None
    return candidates.index.get_loc(true_positions[-1])
