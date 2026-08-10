from __future__ import annotations

from dataclasses import dataclass

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

    Usa aritmética posicional en vez de convertir a etiquetas del índice y
    volver con `.index.get_loc(...)` — ese ida y vuelta por etiqueta se
    rompe silenciosamente (devuelve un `slice` en vez de un entero) si el
    índice del DataFrame tuviera timestamps duplicados.
    """
    start = max(0, as_of - search_window + 1)
    window = candidates.iloc[start : as_of + 1].to_numpy()
    hits = np.flatnonzero(window)
    if hits.size == 0:
        return None
    return start + int(hits[-1])


def find_automatic_rally(
    df: pd.DataFrame, sc_index: int, window: int = 12, as_of: int | None = None
) -> int | None:
    """Posición del máximo (High) más alto en las `window` semanas siguientes a `sc_index`.

    `as_of` acota la búsqueda para que nunca mire semanas posteriores a
    `as_of` (uso en backtest sobre un DataFrame completo sin truncar). Si
    `as_of` es None, se usa la última fila del DataFrame.
    """
    limit = len(df) - 1 if as_of is None else min(as_of, len(df) - 1)
    end = min(limit + 1, sc_index + 1 + window)
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
    as_of: int | None = None,
) -> int | None:
    """Primera semana, tras `ar_index` y dentro de `window` semanas, cuyo mínimo
    retesta la zona del mínimo del SC (`[SC_low*tol_low, SC_low*tol_high]`) con
    volumen menor que el del SC.

    `as_of` acota la búsqueda para que nunca mire semanas posteriores a
    `as_of` (uso en backtest sobre un DataFrame completo sin truncar). Si
    `as_of` es None, se usa la última fila del DataFrame.
    """
    sc_low = df["Low"].iloc[sc_index]
    sc_volume = df["Volume"].iloc[sc_index]
    limit = len(df) - 1 if as_of is None else min(as_of, len(df) - 1)
    end = min(limit + 1, ar_index + 1 + window)

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


@dataclass
class WyckoffStructure:
    sc_index: int
    ar_index: int
    st_index: int
    phase_a_weeks: int
    phase_b_weeks: int
    phase_b_ratio_met: bool  # informativo -- no aplicado como filtro por detect_wyckoff_structure
    range_low: float  # = mínimo del Selling Climax (soporte real). NUNCA un mínimo local de la Fase B.
    range_high: float  # = máximo del Automatic Rally (resistencia real). NUNCA un máximo local de la Fase B.
    spring_index: int | None
    distribution_index: int | None


def detect_wyckoff_structure(
    df_weekly: pd.DataFrame,
    as_of: int | None = None,
    range_lookback: int = 10,
    volume_lookback: int = 12,
    volume_percentile: float = 80,
    range_multiplier: float = 2.0,
    new_low_lookback: int = 10,
    sc_search_window: int = 52,
    ar_window: int = 12,
    st_window: int = 12,
    st_tol_low: float = 0.98,
    st_tol_high: float = 1.10,
    phase_a_recency_weeks: int = 26,
    phase_b_ratio: float = 1.5,
    spring_close_tolerance: float = 0.03,
    spring_close_position_min: float = 0.5,
) -> WyckoffStructure | None:
    """Detecta la estructura Wyckoff/CRT más reciente y vigente en `df_weekly`.

    Devuelve None si no se encuentra SC, AR o ST, o si el ST encontrado ya
    no está vigente (más antiguo que `phase_a_recency_weeks` respecto a
    `as_of`).
    """
    as_of = len(df_weekly) - 1 if as_of is None else min(as_of, len(df_weekly) - 1)

    candidates = find_selling_climax_candidates(
        df_weekly, range_lookback, volume_lookback, volume_percentile, range_multiplier, new_low_lookback
    )
    sc_index = select_most_recent_sc(candidates, as_of, sc_search_window)
    if sc_index is None:
        return None

    ar_index = find_automatic_rally(df_weekly, sc_index, ar_window, as_of)
    if ar_index is None:
        return None

    st_index = find_secondary_test(df_weekly, sc_index, ar_index, st_window, st_tol_low, st_tol_high, as_of)
    if st_index is None:
        return None

    if (as_of - st_index) > phase_a_recency_weeks:
        return None

    phase_a_weeks = st_index - sc_index
    phase_b_weeks = as_of - st_index
    phase_b_ratio_met = phase_b_weeks >= phase_b_ratio * phase_a_weeks

    # El rango de referencia es el de TODA la estructura (SC=soporte, AR=resistencia),
    # no un rango más local observado solo dentro de la Fase B — ver la nota en la
    # Task 4 y la Task 5 sobre por qué esto importa para el Spring y la Distribution.
    range_low = df_weekly["Low"].iloc[sc_index]
    range_high = df_weekly["High"].iloc[ar_index]

    spring_index = find_spring(
        df_weekly, st_index, as_of, range_low, spring_close_tolerance, spring_close_position_min
    )
    distribution_index = find_distribution(df_weekly, st_index, as_of, range_high)

    return WyckoffStructure(
        sc_index=sc_index,
        ar_index=ar_index,
        st_index=st_index,
        phase_a_weeks=phase_a_weeks,
        phase_b_weeks=phase_b_weeks,
        phase_b_ratio_met=phase_b_ratio_met,
        range_low=range_low,
        range_high=range_high,
        spring_index=spring_index,
        distribution_index=distribution_index,
    )
