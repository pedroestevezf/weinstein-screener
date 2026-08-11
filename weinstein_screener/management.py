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


def project_range_target(entry_price: float, range_high: float, range_low: float) -> float | None:
    """Proyecta el objetivo de toma de beneficios parcial como la
    amplitud del propio rango de acumulación semanal (Cause) sumada al
    precio de entrada.

    Es una proyección VERTICAL (altura del rango en el gráfico de
    barras), inspirada en el principio Cause→Effect de Wyckoff, pero no
    es el conteo clásico de Point & Figure (que cuenta la anchura
    horizontal de la congestión en un gráfico P&F y la proyecta con el
    tamaño de caja) — no reclamar esa precisión al consumir este valor.

    None si el rango es inconsistente (range_high <= range_low).
    """
    if range_high <= range_low:
        return None
    return entry_price + (range_high - range_low)


@dataclass
class ExitSignal:
    partial_take_profit: bool
    full_exit: bool


def evaluate_exit_signal(
    current_close: float,
    range_target: float | None,
    current_week_close_above_ma: bool,
) -> ExitSignal:
    """Señal de salida: parcial al alcanzar el objetivo de amplitud de
    rango, total al perder la MA30w. Ambos flags se calculan de forma
    independiente -- `full_exit` puede ser True aunque también se haya
    alcanzado el objetivo parcial (y viceversa), porque la invalidación
    de régimen manda sobre la gestión táctica de beneficios.

    `range_target` puede ser None (`project_range_target`, Task 4, lo
    devuelve así con datos inconsistentes) -- en ese caso
    `partial_take_profit` es simplemente False, pero `full_exit` sigue
    evaluándose con normalidad.
    """
    partial_take_profit = range_target is not None and current_close >= range_target
    return ExitSignal(
        # `current_close >= range_target` yields numpy.bool_ when either
        # operand is a numpy-derived float (e.g. from a pandas Series), which
        # violates the `bool` type contract of ExitSignal -- coerce to a
        # genuine Python bool.
        partial_take_profit=bool(partial_take_profit),
        full_exit=not current_week_close_above_ma,
    )
