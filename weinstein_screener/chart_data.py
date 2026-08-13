from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from weinstein_screener.indicators import moving_average

_MARKER_PRICE_FIELD = {
    "SC": "Low",
    "AR": "High",
    "ST": "Low",
    "Spring": "Low",
    "JAC": "Close",
    "BUEC": "Low",
}


@dataclass
class ChartMarker:
    date: pd.Timestamp
    label: str
    price: float


@dataclass
class ChartData:
    df_visible: pd.DataFrame
    ma: pd.Series
    markers: list[ChartMarker]
    range_low: float
    range_high: float
    range_target: float | None


def build_chart_data(
    df_weekly_full: pd.DataFrame,
    marker_dates: dict[str, pd.Timestamp | None],
    range_low: float,
    range_high: float,
    range_target: float | None,
    visible_weeks: int = 32,
    ma_window: int = 30,
    context_margin_weeks: int = 8,
) -> ChartData:
    """Ensambla los datos listos para pintar el gráfico anotado de un ticker.

    `df_weekly_full` debe traer AL MENOS `visible_weeks + ma_window`
    semanas de histórico -- la MA se calcula sobre toda esa serie antes de
    recortar, para que esté bien definida en toda la ventana visible (ver
    spec, sección 4.1). Si trae menos, la MA sale con NaN al principio del
    tramo visible -- comportamiento honesto de `rolling()`, no se oculta.

    `visible_weeks` es un MÍNIMO, no un valor fijo: la ventana visible se
    ensancha automáticamente para incluir el marcador más antiguo (típicamente
    el SC) con `context_margin_weeks` semanas de margen adicional. Sin esto,
    una estructura Wyckoff cuyo SC quedó a más de `visible_weeks` semanas
    (frecuente -- `sc_search_window` en `wyckoff.py` busca hasta 52 semanas
    atrás) se recorta fuera de la ventana visible: desaparece el marcador SC
    y las líneas de rango (que sí se dibujan siempre, sin filtrar por fecha)
    quedan sin contexto de precio alrededor, ocupando casi todo el eje.

    `marker_dates` no depende de los índices posicionales internos de
    `wyckoff.py`/`ict.py` a propósito -- el llamador convierte
    `structure.sc_index` etc. a fechas antes de invocar esta función, así
    este módulo no necesita conocer esas convenciones de indexado.
    """
    ma_full = moving_average(df_weekly_full, window=ma_window)

    existing_marker_dates = [d for d in marker_dates.values() if d is not None and d in df_weekly_full.index]
    if existing_marker_dates:
        earliest_marker_date = min(existing_marker_dates)
        weeks_since_earliest_marker = int((df_weekly_full.index >= earliest_marker_date).sum())
        visible_weeks = max(visible_weeks, weeks_since_earliest_marker + context_margin_weeks)
    visible_weeks = min(visible_weeks, len(df_weekly_full))

    df_visible = df_weekly_full.iloc[-visible_weeks:]
    ma_visible = ma_full.reindex(df_visible.index)

    markers: list[ChartMarker] = []
    visible_start = df_visible.index.min()
    visible_end = df_visible.index.max()
    for label, date in marker_dates.items():
        if date is None or date not in df_weekly_full.index:
            continue
        if date < visible_start or date > visible_end:
            continue
        field = _MARKER_PRICE_FIELD[label]
        price = float(df_weekly_full.loc[date, field])
        markers.append(ChartMarker(date=date, label=label, price=price))

    return ChartData(
        df_visible=df_visible,
        ma=ma_visible,
        markers=markers,
        range_low=range_low,
        range_high=range_high,
        range_target=range_target,
    )
