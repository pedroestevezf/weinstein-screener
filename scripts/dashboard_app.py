# scripts/dashboard_app.py
"""Dashboard Streamlit del weinstein_screener -- pantallas 'Screener
Filtrado' y 'Detalle de ticker'. Solo alertas, nunca ejecuta operaciones.

Uso:
    .venv/bin/streamlit run scripts/dashboard_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from weinstein_screener.chart_data import build_chart_data
from weinstein_screener.data import get_cached_ohlcv
from weinstein_screener.ict import find_entry_1_signal, find_entry_3_signal
from weinstein_screener.indicators import average_true_range
from weinstein_screener.management import (
    evaluate_exit_signal,
    evaluate_extended_move,
    evaluate_position_management,
    find_entry_2_signal,
    project_range_target,
)
from weinstein_screener.regime import close_above_ma, weinstein_stage2_active
from weinstein_screener.rendering import render_price_chart
from weinstein_screener.wyckoff import detect_wyckoff_structure

_REPO_ROOT = Path(__file__).resolve().parent.parent
ENRICHED_SHORTLIST_PATH = _REPO_ROOT / "data_cache" / "etapa1_shortlist_enriched.csv"
OHLCV_CACHE_DIR = _REPO_ROOT / "data_cache" / "ohlcv"
VISIBLE_WEEKS = 32
MA_WINDOW = 30


@st.cache_data(ttl=3600)
def load_shortlist() -> pd.DataFrame:
    return pd.read_csv(ENRICHED_SHORTLIST_PATH)


@st.cache_data(ttl=3600)
def load_weekly(ticker: str) -> pd.DataFrame:
    # `period="5y"` comfortably covers VISIBLE_WEEKS + MA_WINDOW (62 weeks
    # ~= 1.2 years) plus the longer Wyckoff structure lookback in
    # `detect_wyckoff_structure` (up to sc_search_window=52 weeks back from
    # the ST) -- verified against both defaults, not guessed.
    return get_cached_ohlcv(ticker, interval="1wk", cache_dir=OHLCV_CACHE_DIR, period="5y")


@st.cache_data(ttl=3600)
def load_daily(ticker: str) -> pd.DataFrame:
    return get_cached_ohlcv(ticker, interval="1d", cache_dir=OHLCV_CACHE_DIR, period="2y")


def _week_containing(df_weekly: pd.DataFrame, daily_date) -> pd.Timestamp | None:
    """Mapea una fecha DIARIA a la fecha de la vela SEMANAL (índice W-MON)
    que la contiene -- `DatetimeIndex.asof` devuelve la mayor fecha del
    índice <= `daily_date`, que para un índice semanal de inicio-lunes cae
    exactamente en el lunes de esa semana (verificado). Usado para colocar
    el marcador de BUEC en el gráfico semanal, aunque `find_entry_3_signal`
    lo detecta sobre velas diarias -- ver nota de alcance en el spec,
    sección 4.1: es una referencia visual aproximada, no la vela exacta.
    """
    candidate = df_weekly.index.asof(daily_date)
    if pd.isna(candidate):
        return None
    return candidate


def _marker_dates(df_weekly: pd.DataFrame, df_daily: pd.DataFrame, structure, entry3) -> dict:
    buec_date = None
    if entry3 is not None:
        daily_buec_date = df_daily.index[entry3.trigger_index]
        buec_date = _week_containing(df_weekly, daily_buec_date)

    return {
        "SC": df_weekly.index[structure.sc_index],
        "AR": df_weekly.index[structure.ar_index],
        "ST": df_weekly.index[structure.st_index],
        "Spring": df_weekly.index[structure.spring_index] if structure.spring_index is not None else None,
        "JAC": df_weekly.index[structure.jac_index] if structure.jac_index is not None else None,
        "BUEC": buec_date,
    }


def render_screener_screen():
    st.subheader("Screener Filtrado")
    if not ENRICHED_SHORTLIST_PATH.exists():
        st.warning(
            f"No se encuentra {ENRICHED_SHORTLIST_PATH}. Ejecuta "
            "`scripts/run_etapa1.py` y luego `scripts/enrich_shortlist.py` primero."
        )
        return

    df = load_shortlist()
    st.caption(f"{len(df)} candidatos de Etapa 1")

    event = st.dataframe(
        df,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="shortlist_table",
    )

    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows:
        selected_ticker = df.iloc[selected_rows[0]]["ticker"]
        if st.session_state.get("selected_ticker") != selected_ticker:
            st.session_state["selected_ticker"] = selected_ticker
            st.session_state["screen"] = "detail"
            st.rerun()


def render_detail_screen():
    ticker = st.session_state.get("selected_ticker")
    if ticker is None:
        st.info("Selecciona un ticker en Screener Filtrado.")
        return

    if st.button("← volver a la lista"):
        st.session_state["screen"] = "screener"
        st.rerun()

    with st.spinner(f"Analizando estructura Wyckoff/CRT/ICT de {ticker} (bajo demanda)…"):
        df_weekly = load_weekly(ticker)
        df_daily = load_daily(ticker)
        structure = detect_wyckoff_structure(df_weekly)

    st.markdown(f"## {ticker}  `${df_weekly['Close'].iloc[-1]:.2f}`")

    if structure is None:
        st.info("No se detecta una estructura Wyckoff de acumulación vigente para este ticker ahora mismo.")
        return

    stage2 = weinstein_stage2_active(df_weekly).iloc[-1]
    st.markdown(f"**Stage 2 activo**: {'sí' if stage2 else 'no'}")

    atr_weekly = average_true_range(df_weekly)
    atr_daily = average_true_range(df_daily)

    entry2 = find_entry_2_signal(df_weekly, structure.jac_index, atr_weekly)

    # `structure.spring_index`/`structure.jac_index` are positions in df_weekly
    # (weekly bars) -- find_entry_1_signal/find_entry_3_signal need a position
    # in df_daily instead. Map the weekly event's date to the first daily bar
    # on/after it (`searchsorted` on a DatetimeIndex), verified against a
    # synthetic date range before writing this task. Passing the weekly
    # position directly here would silently search the wrong days entirely.
    entry1 = None
    if structure.spring_index is not None:
        spring_week_date = df_weekly.index[structure.spring_index]
        daily_search_start = int(df_daily.index.searchsorted(spring_week_date))
        entry1 = find_entry_1_signal(df_daily, structure.range_low, daily_search_start, atr_daily)

    entry3 = None
    if structure.jac_index is not None:
        jac_week_date = df_weekly.index[structure.jac_index]
        daily_breakout_index = int(df_daily.index.searchsorted(jac_week_date))
        entry3 = find_entry_3_signal(df_daily, structure.range_high, daily_breakout_index, atr_daily)

    target = None
    extended = None
    if entry2 is not None:
        target = project_range_target(entry2.entry_price, structure.range_high, structure.range_low)
        extended = evaluate_extended_move(df_weekly["Close"].iloc[-1], entry2.entry_price, target)

    if extended is not None and extended.is_extended:
        st.warning(
            f"Recorrido ya avanzado desde la ruptura: ha cubierto el "
            f"{extended.progress_pct:.0%} de la distancia hacia el objetivo proyectado "
            "— el ratio riesgo/beneficio de una entrada nueva aquí es pobre."
        )

    marker_dates = _marker_dates(df_weekly, df_daily, structure, entry3)
    chart_data = build_chart_data(
        df_weekly,
        marker_dates,
        range_low=structure.range_low,
        range_high=structure.range_high,
        range_target=target,
        visible_weeks=VISIBLE_WEEKS,
        ma_window=MA_WINDOW,
    )
    st.altair_chart(render_price_chart(chart_data), use_container_width=True)
    if marker_dates.get("BUEC") is not None:
        st.caption(
            "El marcador BUEC es una referencia semanal aproximada — Entrada 3 se evalúa sobre velas diarias, "
            "no sobre la vela semanal marcada."
        )

    cols = st.columns(3)
    for col, label, signal in zip(cols, ["Entrada 1 (Spring)", "Entrada 2 (JAC)", "Entrada 3 (BUEC)"], [entry1, entry2, entry3]):
        with col:
            st.markdown(f"**{label}**")
            if signal is None:
                st.markdown("_Sin señal_")
            else:
                st.markdown(f"Precio: `${signal.entry_price:.2f}`")
                st.markdown(f"Stop loss: `${signal.stop_loss:.2f}`")

    if entry2 is not None:
        # `entry1_stopped_out` is hardcoded False -- deciding whether a
        # triggered Entry 1 was actually later stopped out requires walking
        # the daily price path after `entry1.trigger_index` looking for a
        # touch of `entry1.stop_loss`, which no existing function in this
        # codebase computes. Out of scope for this task: it under-reports
        # the "Spring fallido" resize alert (never fires) rather than
        # over-reporting it, which is the safer direction for an
        # alerts-only tool. Documented here explicitly, not left as a
        # silent gap -- a follow-up task should add that check properly.
        management = evaluate_position_management(
            entry1_triggered=entry1 is not None,
            entry1_stopped_out=False,
            entry2_triggered=True,
        )
        if management.move_entry1_to_breakeven:
            st.info("Alerta: mover el stop de la Entrada 1 a breakeven.")

    if target is not None:
        exit_signal = evaluate_exit_signal(
            df_weekly["Close"].iloc[-1], target, bool(close_above_ma(df_weekly).iloc[-1])
        )
        st.markdown(f"**Objetivo proyectado**: `${target:.2f}`")
        if exit_signal.full_exit:
            st.error("Salida total: cierre semanal bajo la MA30w.")
        elif exit_signal.partial_take_profit:
            st.success("Toma de parcial: objetivo alcanzado.")


def main():
    st.set_page_config(page_title="Weinstein Screener", layout="wide")
    st.title("Panel de señales")

    if "screen" not in st.session_state:
        st.session_state["screen"] = "screener"

    if st.session_state["screen"] == "screener":
        render_screener_screen()
    else:
        render_detail_screen()


if __name__ == "__main__":
    main()
