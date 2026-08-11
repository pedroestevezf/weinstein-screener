from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Entry2Signal:
    trigger_index: int
    entry_price: float
    stop_loss: float


def find_entry_2_signal(
    df_weekly: pd.DataFrame,
    jac_index: int | None,
    atr_weekly: pd.Series,
    sl_atr_multiplier: float = 1.5,
) -> Entry2Signal | None:
    """Compone el disparador de la Entrada 2: cierre de la semana del JAC
    (Jump Across the Creek — ruptura de `range_high` con volumen, Fase D
    de Wyckoff, ver `weinstein_screener.wyckoff.find_jac`) como precio de
    entrada, stop-loss basado en ATR semanal. None si no hay JAC o si el
    precio de entrada no queda por encima del stop-loss.
    """
    if jac_index is None:
        return None

    entry_price = df_weekly["Close"].iloc[jac_index]
    stop_loss = entry_price - sl_atr_multiplier * atr_weekly.iloc[jac_index]

    if entry_price <= stop_loss:
        return None

    return Entry2Signal(trigger_index=jac_index, entry_price=entry_price, stop_loss=stop_loss)


@dataclass
class ManagementAlert:
    move_entry1_to_breakeven: bool
    resize_entry2_pct: float | None
    resize_entry3_pct: float | None


def evaluate_position_management(
    entry1_triggered: bool,
    entry1_stopped_out: bool,
    entry2_triggered: bool,
    base_entry2_pct: float = 30.0,
    base_entry3_pct: float = 40.0,
) -> ManagementAlert:
    """Alerta de gestión conjunta de las 3 entradas.

    `move_entry1_to_breakeven`: True cuando la Entrada 1 sigue viva y se
    activa la Entrada 2 (JAC). Redimensionamiento: solo si la Entrada 1
    saltó por su SL (Spring fallido), manteniendo el ratio relativo de
    las Entradas 2 y 3 (JAC / BUEC) pero sumando el 100% en vez del 70%
    original.
    """
    move_to_breakeven = entry1_triggered and not entry1_stopped_out and entry2_triggered

    resize_entry2_pct = None
    resize_entry3_pct = None
    if entry1_stopped_out:
        total = base_entry2_pct + base_entry3_pct
        resize_entry2_pct = base_entry2_pct / total * 100
        resize_entry3_pct = base_entry3_pct / total * 100

    return ManagementAlert(
        move_entry1_to_breakeven=move_to_breakeven,
        resize_entry2_pct=resize_entry2_pct,
        resize_entry3_pct=resize_entry3_pct,
    )
