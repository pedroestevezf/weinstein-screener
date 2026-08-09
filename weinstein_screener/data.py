from __future__ import annotations

import os
import re
import time
from pathlib import Path

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


def _safe_cache_key(ticker: str) -> str:
    """Normaliza un ticker a un nombre de archivo seguro (sin barras ni rutas)."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", ticker.upper())


def get_cached_ohlcv(
    ticker: str,
    interval: str,
    cache_dir: Path,
    period: str = "10y",
    max_age_days: int = 1,
    downloader=None,
) -> pd.DataFrame:
    """Devuelve OHLCV para un ticker, usando un caché local en parquet si está fresco."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_ticker = _safe_cache_key(ticker)
    cache_path = cache_dir / f"{safe_ticker}_{interval}_{period}.parquet"

    if cache_path.exists():
        age_seconds = time.time() - cache_path.stat().st_mtime
        if age_seconds <= max_age_days * 86400:
            try:
                return pd.read_parquet(cache_path)
            except Exception:
                pass  # caché corrupto: se re-descarga más abajo

    df = fetch_ohlcv(ticker, interval, period=period, downloader=downloader)
    tmp_path = cache_path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp_path)
    os.replace(tmp_path, cache_path)
    return df
