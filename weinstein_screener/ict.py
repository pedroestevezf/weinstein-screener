from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


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
