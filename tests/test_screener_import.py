import io

import pytest

from weinstein_screener.screener_import import load_shortlist


def _csv(text: str) -> io.StringIO:
    return io.StringIO(text.strip() + "\n")


def test_load_shortlist_strips_us_exchange_prefix():
    csv_source = _csv(
        """
        Ticker,Price
        NASDAQ:AAPL,150
        NYSE:KO,60
        """
    )

    result = load_shortlist(csv_source)

    assert result == ["AAPL", "KO"]


def test_load_shortlist_leaves_non_us_symbols_as_is():
    csv_source = _csv(
        """
        Ticker,Price
        XETRA:SAP,120
        """
    )

    result = load_shortlist(csv_source)

    assert result == ["XETRA:SAP"]


def test_load_shortlist_accepts_symbol_column_case_insensitive():
    csv_source = _csv(
        """
        SYMBOL,Price
        NASDAQ:MSFT,300
        """
    )

    result = load_shortlist(csv_source)

    assert result == ["MSFT"]


def test_load_shortlist_dedupes_preserving_order():
    csv_source = _csv(
        """
        Ticker,Price
        NASDAQ:AAPL,150
        NYSE:KO,60
        NASDAQ:AAPL,151
        """
    )

    result = load_shortlist(csv_source)

    assert result == ["AAPL", "KO"]


def test_load_shortlist_skips_blank_rows():
    csv_source = _csv(
        """
        Ticker,Price
        NASDAQ:AAPL,150
        ,
        NYSE:KO,60
        """
    )

    result = load_shortlist(csv_source)

    assert result == ["AAPL", "KO"]


def test_load_shortlist_raises_without_a_ticker_column():
    csv_source = _csv(
        """
        Name,Price
        Apple,150
        """
    )

    with pytest.raises(ValueError, match="No se encontró una columna"):
        load_shortlist(csv_source)
