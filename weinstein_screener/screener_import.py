from __future__ import annotations

import pandas as pd

_TICKER_COLUMN_NAMES = {"ticker", "symbol"}
_US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "NYSEARCA", "ARCA", "BATS", "OTC"}


def _find_ticker_column(columns) -> str:
    for col in columns:
        if str(col).strip().lower() in _TICKER_COLUMN_NAMES:
            return col
    raise ValueError(
        f"No se encontró una columna de ticker/symbol en el CSV. Columnas disponibles: {list(columns)}"
    )


def _normalize_symbol(raw: str) -> str:
    symbol = raw.strip()
    if ":" in symbol:
        exchange, ticker = symbol.split(":", 1)
        if exchange.strip().upper() in _US_EXCHANGES:
            return ticker.strip()
    return symbol


def load_shortlist(csv_source) -> list[str]:
    """Carga la shortlist exportada manualmente desde el screener de TradingView (Etapa 1).

    Acepta variantes de nombre de columna ("Ticker", "Symbol", case-insensitive).
    Los símbolos de bolsas US (NASDAQ/NYSE/AMEX/...) se normalizan quitando el
    prefijo de bolsa de TradingView (p.ej. "NASDAQ:AAPL" -> "AAPL"), que es el
    formato que espera `fetch_ohlcv` (yfinance). Los símbolos de otras bolsas
    (p.ej. Eurostoxx: "XETRA:SAP") se dejan tal cual -- la conversión al sufijo
    yfinance correspondiente (.DE, .AS, .PA, ...) no está implementada en v1;
    si el símbolo resultante no es descargable, `fetch_ohlcv` lo señalará al
    fallar en vez de mapearlo en silencio a una bolsa equivocada.
    """
    df = pd.read_csv(csv_source)
    ticker_col = _find_ticker_column(df.columns)

    tickers = []
    seen = set()
    for raw in df[ticker_col]:
        if pd.isna(raw):
            continue
        symbol = _normalize_symbol(str(raw))
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        tickers.append(symbol)

    return tickers
