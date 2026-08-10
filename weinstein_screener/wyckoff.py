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


def find_spring(
    df: pd.DataFrame,
    phase_b_start: int,
    as_of: int,
    sc_low: float,
    close_tolerance: float = 0.03,
    close_position_min: float = 0.5,
) -> int | None:
    """Primera semana dentro de la Fase B que cumple los criterios de Spring.

    El umbral de ruptura es `sc_low` (el mínimo del Selling Climax que marca
    el soporte de TODA la estructura), no un mínimo más local observado
    solo dentro de la Fase B — así el Spring barre los stops acumulados
    bajo el soporte real de la estructura, no un mínimo circunstancial.

    El volumen medio de referencia sí se calcula de forma expansiva usando
    solo las semanas de la Fase B ANTERIORES a la semana evaluada (sin
    look-ahead) — el volumen del propio SC no se usa aquí porque es un pico
    atípico que distorsionaría la media.
    """
    for i in range(phase_b_start + 1, as_of + 1):
        prior = df.iloc[phase_b_start:i]
        avg_volume = prior["Volume"].mean()

        low = df["Low"].iloc[i]
        high = df["High"].iloc[i]
        close = df["Close"].iloc[i]
        volume = df["Volume"].iloc[i]

        if low >= sc_low or volume <= avg_volume:
            continue

        candle_range = high - low
        if candle_range == 0:
            continue

        close_position = (close - low) / candle_range
        if close_position < close_position_min:
            continue

        if sc_low * (1 - close_tolerance) <= close <= sc_low * (1 + close_tolerance):
            return i

    return None


def find_distribution(df: pd.DataFrame, phase_b_start: int, as_of: int, ar_high: float) -> int | None:
    """Primera semana cuyo cierre rompe al alza `ar_high` (el máximo del
    Automatic Rally, la resistencia de toda la estructura) con volumen por
    encima de la media de la Fase B hasta ese punto (sin look-ahead).
    """
    for i in range(phase_b_start + 1, as_of + 1):
        prior = df.iloc[phase_b_start:i]
        avg_volume = prior["Volume"].mean()

        close = df["Close"].iloc[i]
        volume = df["Volume"].iloc[i]

        if close > ar_high and volume > avg_volume:
            return i

    return None
