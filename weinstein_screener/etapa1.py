from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import yfinance as yf

from weinstein_screener.data import OHLCV_COLUMNS
from weinstein_screener.indicators import moving_average, pct_distance_from_ma
from weinstein_screener.regime import ma_rising


@dataclass
class Etapa1Candidate:
    ticker: str
    distance_pct: float
    ma_rising: bool
    is_candidate: bool


def drop_unclosed_current_week(df_weekly: pd.DataFrame) -> pd.DataFrame:
    """Descarta la última fila de `df_weekly` si corresponde a una semana que
    todavía no ha cerrado del todo.

    `yf.download(..., interval="1wk")` devuelve la semana en curso (parcial)
    como última fila cuando se ejecuta a mitad de semana. Por convención de
    este proyecto el índice de una barra semanal es el INICIO del periodo
    (lunes, "W-MON"). Una semana está cerrada una vez ha transcurrido tiempo
    real hasta pasado su domingo (barra que empieza el lunes D cierra al
    llegar al lunes D+7). Se usa la hora real del sistema porque esto es
    código de aplicación normal (screening), no un script de flujo de
    trabajo replayable. Ante el caso límite (justo en el domingo de cierre),
    se prefiere descartar la fila por precaución antes que arriesgarse a
    evaluar sobre datos todavía no definitivos.
    """
    if len(df_weekly) == 0:
        return df_weekly
    last_week_start = df_weekly.index[-1]
    if last_week_start + pd.Timedelta(days=6) >= pd.Timestamp.now().normalize():
        return df_weekly.iloc[:-1]
    return df_weekly


def screen_ticker(
    ticker: str,
    df_weekly: pd.DataFrame,
    distance_pct_threshold: float = 7.5,
    ma_window: int = 30,
    slope_lookback: int = 4,
) -> Etapa1Candidate | None:
    """Evalúa Etapa 1 (pre-screening grueso) para un ticker sobre la última
    semana cerrada de `df_weekly`: distancia porcentual del precio a la
    MA30w y si esa media tiene pendiente ascendente. `None` si no hay
    histórico suficiente para calcular la MA (`len(df_weekly) < ma_window`)
    una vez descartada la semana en curso todavía no cerrada.
    """
    df_weekly = drop_unclosed_current_week(df_weekly)

    if len(df_weekly) < ma_window:
        return None

    ma = moving_average(df_weekly, window=ma_window)
    distance = pct_distance_from_ma(df_weekly["Close"], ma)
    rising = ma_rising(df_weekly, ma_window=ma_window, slope_lookback=slope_lookback)

    distance_pct = float(distance.iloc[-1])
    is_rising = bool(rising.iloc[-1])

    return Etapa1Candidate(
        ticker=ticker,
        distance_pct=distance_pct,
        ma_rising=is_rising,
        is_candidate=distance_pct <= distance_pct_threshold and is_rising,
    )


def _default_batch_downloader(tickers: list[str], period: str, interval: str) -> pd.DataFrame:
    """Descarga OHLCV en bloque para varios tickers vía Yahoo Finance."""
    return yf.download(
        tickers,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=False,
        group_by="ticker",
        threads=True,
    )


def _extract_ticker_frame(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Extrae el DataFrame OHLCV de un ticker a partir del resultado de un lote.

    Soporta ambas formas de salida de yfinance: columnas MultiIndex (lote con
    varios tickers, nivel 0 = símbolo) y columnas planas (lote de un único
    ticker). Devuelve un DataFrame vacío si el ticker no está presente.
    """
    if isinstance(raw.columns, pd.MultiIndex):
        if ticker not in raw.columns.get_level_values(0):
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        df = raw[ticker]
    else:
        df = raw

    missing = [col for col in OHLCV_COLUMNS if col not in df.columns]
    if missing:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    return df[OHLCV_COLUMNS].dropna(how="all")


@dataclass
class Etapa1ScreenResult:
    """Resultado de `run_etapa1_screen`, con visibilidad sobre fallos.

    Sin esto, una corrida a gran escala que sufra rate-limiting (o cualquier
    otro fallo sistemático de descarga) devolvería silenciosamente una lista
    de candidatos vacía indistinguible de "no hay candidatos ahora mismo".
    """

    candidates: list[Etapa1Candidate]
    tickers_attempted: int
    tickers_screened: int
    batches_failed: int


def run_etapa1_screen(
    tickers: list[str],
    batch_size: int = 100,
    distance_pct_threshold: float = 7.5,
    ma_window: int = 30,
    slope_lookback: int = 4,
    period: str = "2y",
    downloader=None,
) -> Etapa1ScreenResult:
    """Ejecuta Etapa 1 sobre una lista de tickers, descargando OHLCV semanal
    en lotes de `batch_size`. Tolerante a fallos individuales: un ticker sin
    datos o que haga fallar `screen_ticker`, o un lote completo cuya descarga
    falle, se omite sin abortar el resto de la corrida.

    Un lote de más de un ticker cuya respuesta venga con columnas planas (no
    MultiIndex) en vez de la forma esperada para varios tickers se trata
    también como lote fallido: la forma de la respuesta no coincide con la
    del pedido, así que no hay manera segura de atribuir esas filas a un
    ticker concreto (antes esto se atribuía silenciosamente el mismo frame a
    todos los tickers del lote).

    Devuelve un `Etapa1ScreenResult` con los candidatos (`is_candidate = True`,
    ordenados por `distance_pct` ascendente) y contadores de fallos
    (`tickers_attempted`, `tickers_screened`, `batches_failed`) para que el
    llamador pueda distinguir "no hay candidatos" de "la corrida falló".
    """
    downloader = downloader or _default_batch_downloader

    candidates: list[Etapa1Candidate] = []
    tickers_screened = 0
    batches_failed = 0

    for start in range(0, len(tickers), batch_size):
        chunk = tickers[start : start + batch_size]

        try:
            raw = downloader(chunk, period, "1wk")
        except Exception:
            batches_failed += 1
            continue  # todo el lote falla: se omite, se sigue con el resto

        if len(chunk) > 1 and not isinstance(raw.columns, pd.MultiIndex):
            # Forma de respuesta inconsistente con el pedido: no se puede
            # atribuir con seguridad estas filas a un ticker del lote.
            batches_failed += 1
            continue

        for ticker in chunk:
            try:
                df = _extract_ticker_frame(raw, ticker)
                if df.empty:
                    continue
                result = screen_ticker(
                    ticker,
                    df,
                    distance_pct_threshold=distance_pct_threshold,
                    ma_window=ma_window,
                    slope_lookback=slope_lookback,
                )
            except Exception:
                continue  # fallo de un ticker individual: se omite

            tickers_screened += 1
            if result is not None:
                candidates.append(result)

    qualified = [c for c in candidates if c.is_candidate is True]
    qualified.sort(key=lambda c: c.distance_pct)
    return Etapa1ScreenResult(
        candidates=qualified,
        tickers_attempted=len(tickers),
        tickers_screened=tickers_screened,
        batches_failed=batches_failed,
    )
