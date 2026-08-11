from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class SpringReentry:
    anchor_index: int
    reentry_index: int
    high_confidence: bool


def find_order_block(df: pd.DataFrame, impulse_end_index: int, lookback: int = 10) -> int | None:
    """Última vela bajista (Close < Open) antes de `impulse_end_index`, buscando
    hacia atrás dentro de `lookback` velas. Devuelve None si no hay ninguna.
    """
    start = max(0, impulse_end_index - lookback)
    for i in range(impulse_end_index - 1, start - 1, -1):
        if df["Close"].iloc[i] < df["Open"].iloc[i]:
            return i
    return None


def find_fair_value_gap(
    df: pd.DataFrame,
    start_index: int,
    end_index: int,
    atr: pd.Series,
    body_multiplier: float = 1.5,
    body_lookback: int = 20,
    gap_range_fraction: float = 0.2,
) -> int | None:
    """Posición de la vela central (vela 2) del primer FVG alcista válido
    dentro de `[start_index, end_index]`, o None.
    """
    body = (df["Close"] - df["Open"]).abs()
    avg_body = body.shift(1).rolling(body_lookback).mean()

    for i in range(start_index + 1, end_index):
        c1_high = df["High"].iloc[i - 1]
        c3_low = df["Low"].iloc[i + 1]
        gap = c3_low - c1_high
        if gap <= 0:
            continue

        candle2_body = body.iloc[i]
        if pd.isna(avg_body.iloc[i]) or candle2_body < body_multiplier * avg_body.iloc[i]:
            continue

        candle2_range = df["High"].iloc[i] - df["Low"].iloc[i]
        min_gap = max(gap_range_fraction * candle2_range, atr.iloc[i])
        if gap < min_gap:
            continue

        return i

    return None


def find_spring_reentry_mss(
    df: pd.DataFrame,
    sc_low: float,
    search_start: int,
    window: int = 5,
    retest_tolerance: float = 0.02,
) -> SpringReentry | None:
    """Ancla (ruptura de sc_low) + reingreso (cierre de vuelta sobre sc_low),
    ambos dentro de una ventana de `window` días cada uno desde `search_start`.
    `high_confidence` marca si, tras el reingreso, el precio retestea sc_low
    de nuevo dentro de otra ventana de `window` días.
    """
    anchor_index = None
    for i in range(search_start, min(len(df), search_start + window)):
        if df["Low"].iloc[i] < sc_low:
            anchor_index = i
            break
    if anchor_index is None:
        return None

    reentry_index = None
    for i in range(anchor_index + 1, min(len(df), anchor_index + 1 + window)):
        if df["Close"].iloc[i] > sc_low:
            reentry_index = i
            break
    if reentry_index is None:
        return None

    retest_end = min(len(df), reentry_index + 1 + window)
    high_confidence = any(
        df["Low"].iloc[j] <= sc_low * (1 + retest_tolerance) for j in range(reentry_index + 1, retest_end)
    )

    return SpringReentry(anchor_index=anchor_index, reentry_index=reentry_index, high_confidence=high_confidence)
