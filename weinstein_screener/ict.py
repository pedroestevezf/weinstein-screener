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
