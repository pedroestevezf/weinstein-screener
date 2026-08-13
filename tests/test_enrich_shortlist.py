import csv
import io

import pandas as pd
import pytest

from scripts.enrich_shortlist import build_enriched_rows, read_shortlist_csv


def test_read_shortlist_csv_parses_ticker_distance_and_ma_rising():
    csv_text = "ticker,distance_pct,ma_rising\nWM,0.0484,True\nAAPL,3.5,True\n"

    result = read_shortlist_csv(io.StringIO(csv_text))

    assert result == [
        {"ticker": "WM", "distance_pct": 0.0484, "ma_rising": True},
        {"ticker": "AAPL", "distance_pct": 3.5, "ma_rising": True},
    ]


def test_build_enriched_rows_merges_fundamentals_and_relative_volume():
    from weinstein_screener.fundamentals import TickerFundamentals

    shortlist_rows = [{"ticker": "WM", "distance_pct": 0.0484, "ma_rising": True}]
    fundamentals_by_ticker = {
        "WM": TickerFundamentals(
            ticker="WM", sector="Industrials", market_cap=9.08e10, trailing_pe=59.9, ev_to_fcf=48.3
        )
    }
    relative_volume_by_ticker = {"WM": 1.9}

    result = build_enriched_rows(shortlist_rows, fundamentals_by_ticker, relative_volume_by_ticker)

    assert result == [
        {
            "ticker": "WM",
            "distance_pct": 0.0484,
            "ma_rising": True,
            "sector": "Industrials",
            "market_cap": 9.08e10,
            "trailing_pe": 59.9,
            "ev_to_fcf": 48.3,
            "relative_volume": 1.9,
        }
    ]


def test_build_enriched_rows_fills_missing_ticker_data_with_none():
    # a ticker present in the shortlist but missing from both lookup dicts
    # (e.g. its OHLCV fetch or fundamentals fetch failed) must not crash
    # the whole enrichment -- it gets None fields, not a KeyError
    shortlist_rows = [{"ticker": "MISSING", "distance_pct": 1.0, "ma_rising": True}]

    result = build_enriched_rows(shortlist_rows, fundamentals_by_ticker={}, relative_volume_by_ticker={})

    assert result == [
        {
            "ticker": "MISSING",
            "distance_pct": 1.0,
            "ma_rising": True,
            "sector": None,
            "market_cap": None,
            "trailing_pe": None,
            "ev_to_fcf": None,
            "relative_volume": None,
        }
    ]
