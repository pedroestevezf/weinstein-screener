from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TickerFundamentals:
    ticker: str
    sector: str | None
    market_cap: float | None
    trailing_pe: float | None
    ev_to_fcf: float | None


def _default_info_getter(ticker: str) -> dict:
    import yfinance as yf

    return yf.Ticker(ticker).get_info()


def _compute_ev_to_fcf(info: dict) -> float | None:
    enterprise_value = info.get("enterpriseValue")
    free_cashflow = info.get("freeCashflow")
    if enterprise_value is None or not free_cashflow:
        return None
    return enterprise_value / free_cashflow


def fetch_fundamentals_for_candidates(
    tickers: list[str],
    info_getter=None,
) -> list[TickerFundamentals]:
    """Fundamentales (sector, cap. mercado, PER, EV/FCF) por ticker, vía
    `yfinance.Ticker.get_info()`. SOLO llamar sobre listas ya filtradas
    (los candidatos de Etapa 1, no el universo completo) -- `get_info()`
    no tiene equivalente en lote, ~0.4-0.85s por ticker verificado con
    datos reales.

    Tolerante a fallos por ticker: uno que falle no aborta el resto, se
    devuelve con todos los campos a None en la misma posición de la lista
    de salida (mismo orden y cuenta que la entrada).
    """
    info_getter = info_getter or _default_info_getter

    results: list[TickerFundamentals] = []
    for ticker in tickers:
        try:
            info = info_getter(ticker)
        except Exception:
            results.append(
                TickerFundamentals(ticker=ticker, sector=None, market_cap=None, trailing_pe=None, ev_to_fcf=None)
            )
            continue

        results.append(
            TickerFundamentals(
                ticker=ticker,
                sector=info.get("sector"),
                market_cap=info.get("marketCap"),
                trailing_pe=info.get("trailingPE"),
                ev_to_fcf=_compute_ev_to_fcf(info),
            )
        )
    return results
