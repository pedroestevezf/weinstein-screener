from __future__ import annotations

import pandas as pd
import yfinance as yf

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def fetch_ohlcv(
    ticker: str,
    interval: str,
    period: str = "10y",
    downloader=None,
) -> pd.DataFrame:
    """Descarga datos OHLCV de un ticker desde Yahoo Finance.

    `interval` debe ser "1d" o "1wk".
    """
    if interval not in ("1d", "1wk"):
        raise ValueError(f"interval must be '1d' or '1wk', got {interval!r}")

    download = downloader or yf.download
    raw = download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)

    if raw.empty:
        raise ValueError(f"No data returned for ticker {ticker!r}")

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw[OHLCV_COLUMNS].copy()
    df.index.name = "Date"
    return df
