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


def find_automatic_rally(df: pd.DataFrame, sc_index: int, window: int = 12) -> int | None:
    """Posición del máximo (High) más alto en las `window` semanas siguientes a `sc_index`."""
    end = min(len(df), sc_index + 1 + window)
    segment = df["High"].iloc[sc_index + 1 : end]
    if segment.empty:
        return None
    return int(segment.values.argmax()) + sc_index + 1


def find_secondary_test(
    df: pd.DataFrame,
    sc_index: int,
    ar_index: int,
    window: int = 12,
    tol_low: float = 0.98,
    tol_high: float = 1.10,
) -> int | None:
    """Primera semana, tras `ar_index` y dentro de `window` semanas, cuyo mínimo
    retesta la zona del mínimo del SC (`[SC_low*tol_low, SC_low*tol_high]`) con
    volumen menor que el del SC.
    """
    sc_low = df["Low"].iloc[sc_index]
    sc_volume = df["Volume"].iloc[sc_index]
    end = min(len(df), ar_index + 1 + window)

    for i in range(ar_index + 1, end):
        low = df["Low"].iloc[i]
        volume = df["Volume"].iloc[i]
        if sc_low * tol_low <= low <= sc_low * tol_high and volume < sc_volume:
            return i
    return None
