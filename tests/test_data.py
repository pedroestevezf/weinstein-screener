import os
from pathlib import Path

import pandas as pd
import pytest

from weinstein_screener.data import fetch_ohlcv, get_cached_ohlcv


def _fake_downloader(rows: int = 5):
    def _download(ticker, period, interval, progress, auto_adjust):
        dates = pd.date_range("2024-01-01", periods=rows, freq="D")
        return pd.DataFrame(
            {
                "Open": range(rows),
                "High": range(rows),
                "Low": range(rows),
                "Close": range(rows),
                "Volume": range(rows),
            },
            index=dates,
        )

    return _download


def test_fetch_ohlcv_returns_expected_columns():
    df = fetch_ohlcv("FAKE", "1d", downloader=_fake_downloader())

    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df.index.name == "Date"
    assert len(df) == 5


def test_fetch_ohlcv_rejects_invalid_interval():
    with pytest.raises(ValueError, match="interval"):
        fetch_ohlcv("FAKE", "1h")


def test_fetch_ohlcv_raises_on_empty_result():
    def empty_downloader(ticker, period, interval, progress, auto_adjust):
        return pd.DataFrame()

    with pytest.raises(ValueError, match="No data"):
        fetch_ohlcv("FAKE", "1d", downloader=empty_downloader)


def _counting_downloader(calls: list):
    def _download(ticker, period, interval, progress, auto_adjust):
        calls.append(ticker)
        dates = pd.date_range("2024-01-01", periods=3, freq="D")
        return pd.DataFrame(
            {"Open": [1, 2, 3], "High": [1, 2, 3], "Low": [1, 2, 3], "Close": [1, 2, 3], "Volume": [1, 2, 3]},
            index=dates,
        )

    return _download


def test_get_cached_ohlcv_downloads_when_no_cache(tmp_path: Path):
    calls: list = []

    df = get_cached_ohlcv("FAKE", "1d", cache_dir=tmp_path, downloader=_counting_downloader(calls))

    assert len(calls) == 1
    assert len(df) == 3
    assert (tmp_path / "FAKE_1d.parquet").exists()


def test_get_cached_ohlcv_uses_fresh_cache_without_downloading(tmp_path: Path):
    calls: list = []
    downloader = _counting_downloader(calls)

    get_cached_ohlcv("FAKE", "1d", cache_dir=tmp_path, downloader=downloader)
    get_cached_ohlcv("FAKE", "1d", cache_dir=tmp_path, downloader=downloader)

    assert len(calls) == 1


def test_get_cached_ohlcv_redownloads_when_cache_is_stale(tmp_path: Path):
    calls: list = []
    downloader = _counting_downloader(calls)

    get_cached_ohlcv("FAKE", "1d", cache_dir=tmp_path, max_age_days=1, downloader=downloader)

    cache_path = tmp_path / "FAKE_1d.parquet"
    old_time = cache_path.stat().st_mtime - (2 * 86400)
    os.utime(cache_path, (old_time, old_time))

    get_cached_ohlcv("FAKE", "1d", cache_dir=tmp_path, max_age_days=1, downloader=downloader)

    assert len(calls) == 2
