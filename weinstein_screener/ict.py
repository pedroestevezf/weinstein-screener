from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class SpringReentry:
    anchor_index: int
    reentry_index: int
    high_confidence: bool


def find_order_block(
    df: pd.DataFrame, impulse_end_index: int, lookback: int = 10, min_index: int = 0
) -> int | None:
    """Última vela bajista (Close < Open) antes de `impulse_end_index`, buscando
    hacia atrás dentro de `lookback` velas, sin cruzar `min_index`. Devuelve
    None si no hay ninguna.

    `min_index` evita que el Order Block se seleccione fuera de la propia
    estructura que originó el disparador (por ejemplo, antes del ancla del
    Spring o antes del propio retest) — sin este límite, `entry_price`
    podría terminar por debajo de `stop_loss` si la vela bajista más
    cercana está más allá del tramo relevante.
    """
    start = max(min_index, impulse_end_index - lookback)
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


@dataclass
class RetestResult:
    retest_index: int
    volume_declining: bool
    no_supply: bool


def _is_no_supply_candle(df: pd.DataFrame, index: int, range_lookback: int = 10) -> bool:
    is_bearish = df["Close"].iloc[index] < df["Open"].iloc[index]
    low = df["Low"].iloc[index]
    high = df["High"].iloc[index]
    candle_range = high - low

    prior_ranges = (df["High"] - df["Low"]).iloc[max(0, index - range_lookback) : index]
    avg_range = prior_ranges.mean()
    small_range = not pd.isna(avg_range) and candle_range < avg_range

    close_position = (df["Close"].iloc[index] - low) / candle_range if candle_range > 0 else 0
    upper_half_close = close_position >= 0.5

    if index >= 2:
        avg_volume_prev2 = df["Volume"].iloc[index - 2 : index].mean()
        low_volume = df["Volume"].iloc[index] < avg_volume_prev2
    else:
        low_volume = False

    return bool(is_bearish and small_range and upper_half_close and low_volume)


def find_retest(
    df: pd.DataFrame,
    ar_high: float,
    breakout_index: int,
    window: int = 5,
    tolerance: float = 0.05,
    volume_decline_fraction: float = 0.8,
    no_supply_lookback: int = 10,
) -> RetestResult | None:
    """Primera vela, dentro de `window` días tras `breakout_index`, que toca
    la banda `±tolerance` alrededor de `ar_high` con volumen descendente o
    una vela "no supply".

    La comparación de volumen descendente incluye la propia vela de ruptura
    (`breakout_index`) como primer término — si no se incluyera, una vela
    de retest que ocurre justo en el primer día tras la ruptura nunca
    tendría una "vela anterior" con la que compararse y el criterio de
    volumen descendente no podría dispararse nunca en ese caso.
    """
    band_low = ar_high * (1 - tolerance)
    band_high = ar_high * (1 + tolerance)
    end = min(len(df), breakout_index + 1 + window)
    candidates = list(range(breakout_index + 1, end))

    for position, i in enumerate(candidates):
        low = df["Low"].iloc[i]
        high = df["High"].iloc[i]
        touches_band = high >= band_low and low <= band_high
        if not touches_band:
            continue

        segment = [breakout_index] + candidates[: position + 1]
        declines = sum(
            1
            for k in range(1, len(segment))
            if df["Volume"].iloc[segment[k]] < df["Volume"].iloc[segment[k - 1]]
        )
        volume_declining = (declines / (len(segment) - 1)) >= volume_decline_fraction

        no_supply = _is_no_supply_candle(df, i, no_supply_lookback)

        if volume_declining or no_supply:
            return RetestResult(retest_index=i, volume_declining=volume_declining, no_supply=no_supply)

    return None


@dataclass
class EntrySignal:
    trigger_index: int
    order_block_index: int | None
    fvg_index: int | None
    entry_price: float | None
    stop_loss: float | None
    high_confidence: bool


def find_entry_1_signal(
    df_daily: pd.DataFrame,
    sc_low: float,
    search_start: int,
    atr: pd.Series,
    window: int = 5,
    ob_lookback: int = 10,
    sl_buffer_atr: float = 0.25,
    fvg_body_multiplier: float = 1.5,
    fvg_body_lookback: int = 20,
    fvg_gap_range_fraction: float = 0.2,
) -> EntrySignal | None:
    """Compone el disparador de la Entrada 1 (Spring): reingreso al rango,
    Order Block, y FVG opcional como refuerzo. None si no hay reingreso o
    no hay Order Block.
    """
    reentry = find_spring_reentry_mss(df_daily, sc_low, search_start, window)
    if reentry is None:
        return None

    order_block_index = find_order_block(df_daily, reentry.reentry_index, ob_lookback, min_index=reentry.anchor_index)
    if order_block_index is None:
        return None

    fvg_index = None
    if reentry.reentry_index - reentry.anchor_index >= 2:
        fvg_index = find_fair_value_gap(
            df_daily,
            reentry.anchor_index,
            reentry.reentry_index,
            atr,
            fvg_body_multiplier,
            fvg_body_lookback,
            fvg_gap_range_fraction,
        )

    entry_price = df_daily["High"].iloc[order_block_index]
    stop_loss = df_daily["Low"].iloc[reentry.anchor_index] - sl_buffer_atr * atr.iloc[reentry.anchor_index]

    if entry_price <= stop_loss:
        return None

    return EntrySignal(
        trigger_index=reentry.reentry_index,
        order_block_index=order_block_index,
        fvg_index=fvg_index,
        entry_price=entry_price,
        stop_loss=stop_loss,
        high_confidence=reentry.high_confidence,
    )


def find_entry_3_signal(
    df_daily: pd.DataFrame,
    ar_high: float,
    breakout_index: int,
    atr: pd.Series,
    window: int = 5,
    tolerance: float = 0.05,
    ob_lookback: int = 10,
    volume_decline_fraction: float = 0.8,
    no_supply_lookback: int = 10,
    fvg_body_multiplier: float = 1.5,
    fvg_body_lookback: int = 20,
    fvg_gap_range_fraction: float = 0.2,
) -> EntrySignal | None:
    """Compone el disparador de la Entrada 3 (retest): retest de `ar_high`
    con volumen descendente o vela no-supply, Order Block, y FVG opcional
    como refuerzo. None si no hay retest o no hay Order Block.
    """
    retest = find_retest(
        df_daily, ar_high, breakout_index, window, tolerance, volume_decline_fraction, no_supply_lookback
    )
    if retest is None:
        return None

    order_block_index = find_order_block(
        df_daily, retest.retest_index + 1, ob_lookback, min_index=retest.retest_index
    )
    if order_block_index is None:
        return None

    fvg_index = None
    fvg_start = retest.retest_index
    fvg_end = min(len(df_daily) - 1, retest.retest_index + window)
    if fvg_end - fvg_start >= 2:
        fvg_index = find_fair_value_gap(
            df_daily, fvg_start, fvg_end, atr, fvg_body_multiplier, fvg_body_lookback, fvg_gap_range_fraction
        )

    entry_price = df_daily["High"].iloc[order_block_index]
    stop_loss = df_daily["Low"].iloc[retest.retest_index]

    if entry_price <= stop_loss:
        return None

    return EntrySignal(
        trigger_index=retest.retest_index,
        order_block_index=order_block_index,
        fvg_index=fvg_index,
        entry_price=entry_price,
        stop_loss=stop_loss,
        high_confidence=retest.no_supply,
    )
