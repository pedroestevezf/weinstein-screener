from __future__ import annotations

import altair as alt
import pandas as pd

from weinstein_screener.chart_data import ChartData

_UP_COLOR = "#2f9155"
_DOWN_COLOR = "#c14b56"


def _colored(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Direction"] = df.apply(lambda r: "up" if r["Close"] >= r["Open"] else "down", axis=1)
    return df


def render_price_chart(chart_data: ChartData) -> alt.VConcatChart:
    """Gráfico de velas semanales + MA + anotaciones de estructura Wyckoff
    (panel de precio) apilado sobre un panel de volumen SEPARADO, a partir
    de un `ChartData` ya ensamblado
    (`weinstein_screener.chart_data.build_chart_data`). Esta función es
    solo de renderizado -- no calcula nada, todos los datos ya vienen
    resueltos en `chart_data`.

    Precio y volumen son paneles apilados (`alt.vconcat`), NO capas
    superpuestas en la misma área de dibujo con escala independiente --
    superponerlos así colisionaría visualmente velas y barras de volumen
    en los mismos píxeles. Solo comparten el eje X (fechas).

    El eje de precios va a la derecha (`axis=alt.Axis(orient="right")`),
    igual que en el mockup -- se fija en cada capa de precio individual
    (no basta con fijarlo en una sola capa de un `layer()`, cada capa
    declara su propia codificación de eje).
    """
    df = _colored(chart_data.df_visible.reset_index(names="Date"))
    color_scale = alt.Scale(domain=["up", "down"], range=[_UP_COLOR, _DOWN_COLOR])

    # `scale=alt.Scale(zero=False)` en TODAS las capas de precio -- Vega-Lite
    # fusiona el dominio de las escalas Y de capas en el mismo `alt.layer()`
    # y por defecto un eje cuantitativo fuerza el cero en el dominio. Sin
    # esto, un precio semanal tipo $28-35 queda comprimido en una franja
    # mínima de un eje 0-35 y apenas se distinguen las velas.
    price_scale = alt.Scale(zero=False)

    # El sombreado y las líneas de referencia del rango de acumulación --
    # ambos acotados al mismo tramo temporal, no al ancho completo del
    # gráfico: el rango no existe antes de la vela del SC, y va SÓLIDO
    # hasta el JAC (o hasta la última vela visible si el JAC todavía no ha
    # ocurrido). A partir del JAC solo el nivel superior continúa, como
    # línea de puntos -- el soporte del SC deja de ser relevante tras la
    # ruptura, pero la resistencia del AR sigue sirviendo de referencia
    # (p. ej. como soporte en el retroceso hacia el BUEC).
    range_layers = []
    if chart_data.sc_date is not None:
        solid_end = chart_data.jac_date if chart_data.jac_date is not None else chart_data.df_visible.index.max()

        # `axis=alt.Axis(title=None)` en "start" -- sin esto, Vega-Lite
        # concatena los nombres de campo de todas las capas del eje X
        # compartido en un único título ("start, end, Date" en vez de
        # "Date"), ya que estas capas usan "start"/"end" en vez de "Date".
        band_df = pd.DataFrame(
            {"start": [chart_data.sc_date], "end": [solid_end], "low": [chart_data.range_low], "high": [chart_data.range_high]}
        )
        range_layers.append(
            alt.Chart(band_df)
            .mark_rect(opacity=0.12, color="#1c7c72")
            .encode(
                x=alt.X("start:T", axis=alt.Axis(title=None)),
                x2="end:T",
                y=alt.Y("low:Q", axis=alt.Axis(orient="right"), scale=price_scale),
                y2="high:Q",
            )
        )

        solid_df = pd.DataFrame(
            {
                "start": [chart_data.sc_date, chart_data.sc_date],
                "end": [solid_end, solid_end],
                "level": [chart_data.range_low, chart_data.range_high],
            }
        )
        range_layers.append(
            alt.Chart(solid_df)
            .mark_rule(color="#1c7c72")
            .encode(
                x=alt.X("start:T", axis=alt.Axis(title=None)),
                x2="end:T",
                y=alt.Y("level:Q", axis=alt.Axis(orient="right"), scale=price_scale),
            )
        )
        if chart_data.jac_date is not None:
            dotted_df = pd.DataFrame(
                {"start": [chart_data.jac_date], "end": [chart_data.df_visible.index.max()], "level": [chart_data.range_high]}
            )
            range_layers.append(
                alt.Chart(dotted_df)
                .mark_rule(strokeDash=[2, 2], color="#1c7c72")
                .encode(
                    x=alt.X("start:T", axis=alt.Axis(title=None)),
                    x2="end:T",
                    y=alt.Y("level:Q", axis=alt.Axis(orient="right"), scale=price_scale),
                )
            )
    # `title="Precio"` va en wicks (no en el rango) porque wicks siempre se
    # dibuja -- si el título dependiera de una capa de rango condicional,
    # desaparecería del eje cuando `chart_data.sc_date` es None.
    wicks = alt.Chart(df).mark_rule().encode(
        x="Date:T", y=alt.Y("Low:Q", axis=alt.Axis(orient="right", title="Precio"), scale=price_scale), y2="High:Q",
        color=alt.Color("Direction:N", scale=color_scale, legend=None),
    )
    bodies = alt.Chart(df).mark_bar(size=6).encode(
        x="Date:T", y=alt.Y("Open:Q", axis=alt.Axis(orient="right"), scale=price_scale), y2="Close:Q",
        color=alt.Color("Direction:N", scale=color_scale, legend=None),
    )

    ma_df = chart_data.ma.reset_index()
    ma_df.columns = ["Date", "MA"]
    ma_line = alt.Chart(ma_df).mark_line(color="#4c6f96").encode(
        x="Date:T", y=alt.Y("MA:Q", axis=alt.Axis(orient="right"), scale=price_scale)
    )

    price_layers = [*range_layers, wicks, bodies, ma_line]

    if chart_data.markers:
        markers_df = pd.DataFrame(
            {
                "Date": [m.date for m in chart_data.markers],
                "price": [m.price for m in chart_data.markers],
                "label": [m.label for m in chart_data.markers],
            }
        )
        marker_points = alt.Chart(markers_df).mark_point(filled=True, size=60, color="#b3811a").encode(
            x="Date:T", y=alt.Y("price:Q", axis=alt.Axis(orient="right"), scale=price_scale)
        )
        marker_labels = alt.Chart(markers_df).mark_text(dy=-10, color="#b3811a").encode(
            x="Date:T", y=alt.Y("price:Q", axis=alt.Axis(orient="right"), scale=price_scale), text="label:N"
        )
        price_layers += [marker_points, marker_labels]

    if chart_data.range_target is not None:
        target_df = pd.DataFrame({"target": [chart_data.range_target]})
        target_line = alt.Chart(target_df).mark_rule(strokeDash=[6, 4], color="#0f5d55").encode(
            y=alt.Y("target:Q", axis=alt.Axis(orient="right"), scale=price_scale)
        )
        price_layers.append(target_line)

    price_chart = alt.layer(*price_layers).properties(height=300)

    volume_chart = alt.Chart(df).mark_bar(opacity=0.5).encode(
        x="Date:T", y=alt.Y("Volume:Q", axis=alt.Axis(orient="right", title="Volumen")),
        color=alt.Color("Direction:N", scale=color_scale, legend=None),
    ).properties(height=100)

    return alt.vconcat(price_chart, volume_chart).resolve_scale(x="shared")
