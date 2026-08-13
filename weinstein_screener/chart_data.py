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
    sc_date: pd.Timestamp | None
    jac_date: pd.Timestamp | None


def build_chart_data(
    df_weekly_full: pd.DataFrame,
    marker_dates: dict[str, pd.Timestamp | None],
    range_low: float,
    range_high: float,
    range_target: float | None,
    visible_weeks: int = 52,
    ma_window: int = 30,
) -> ChartData:
    """Ensambla los datos listos para pintar el gráfico anotado de un ticker.

    `df_weekly_full` debe traer AL MENOS `visible_weeks + ma_window`
    semanas de histórico -- la MA se calcula sobre toda esa serie antes de
    recortar, para que esté bien definida en toda la ventana visible (ver
    spec, sección 4.1). Si trae menos, la MA sale con NaN al principio del
    tramo visible -- comportamiento honesto de `rolling()`, no se oculta.

    `visible_weeks` es una ventana FIJA de 52 semanas por defecto -- elegida
    a propósito para cubrir el SC en prácticamente todos los casos reales:
    `phase_a_recency_weeks=26` en `wyckoff.py` exige que el ST esté a lo
    sumo a 26 semanas de la semana actual, y el SC no puede preceder al ST
    en más de `ar_window + st_window` (24 semanas) para que se detecten AR
    y ST dentro de sus ventanas -- así que una estructura "vigente" tiene el
    SC, como mucho, a unas 50 semanas de hoy.

    `marker_dates` no depende de los índices posicionales internos de
    `wyckoff.py`/`ict.py` a propósito -- el llamador convierte
    `structure.sc_index` etc. a fechas antes de invocar esta función, así
    este módulo no necesita conocer esas convenciones de indexado.

    `sc_date`/`jac_date` se leen directamente de `marker_dates`, no de la
    lista `markers` ya filtrada por ventana visible -- los límites del
    rango de acumulación (ver `rendering.py`) necesitan la fecha real del
    SC/JAC aunque, en el caso límite, cayera fuera de la ventana visible.
    """
    ma_full = moving_average(df_weekly_full, window=ma_window)
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
        sc_date=marker_dates.get("SC"),
        jac_date=marker_dates.get("JAC"),
    )
