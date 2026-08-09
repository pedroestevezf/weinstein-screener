import pandas as pd
import pytest

from weinstein_screener.data import fetch_ohlcv


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
