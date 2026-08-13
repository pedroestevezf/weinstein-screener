import pytest

from weinstein_screener.fundamentals import TickerFundamentals, fetch_fundamentals_for_candidates


def test_fetch_fundamentals_for_candidates_maps_known_fields():
    def fake_info_getter(ticker):
        return {
            "sector": "Industrials",
            "marketCap": 90771324928,
            "trailingPE": 59.918205,
            "enterpriseValue": 113475387392,
            "freeCashflow": 2348375040,
        }

    result = fetch_fundamentals_for_candidates(["WM"], info_getter=fake_info_getter)

    assert result == [
        TickerFundamentals(
            ticker="WM",
            sector="Industrials",
            market_cap=90771324928,
            trailing_pe=59.918205,
            ev_to_fcf=pytest.approx(113475387392 / 2348375040),
        )
    ]


def test_fetch_fundamentals_for_candidates_handles_missing_free_cashflow():
    def fake_info_getter(ticker):
        return {
            "sector": "Financial Services",
            "marketCap": 339178816,
            "trailingPE": 25.883331,
            "enterpriseValue": 208148560,
            "freeCashflow": None,
        }

    result = fetch_fundamentals_for_candidates(["BCML"], info_getter=fake_info_getter)

    assert result[0].ev_to_fcf is None
    assert result[0].market_cap == 339178816


def test_fetch_fundamentals_for_candidates_handles_zero_free_cashflow():
    def fake_info_getter(ticker):
        return {"sector": "X", "marketCap": 1.0, "trailingPE": 1.0, "enterpriseValue": 500.0, "freeCashflow": 0}

    result = fetch_fundamentals_for_candidates(["ZZZ"], info_getter=fake_info_getter)

    assert result[0].ev_to_fcf is None


def test_fetch_fundamentals_for_candidates_handles_missing_info_keys():
    def fake_info_getter(ticker):
        return {}  # a ticker with no usable fundamentals data at all

    result = fetch_fundamentals_for_candidates(["NODATA"], info_getter=fake_info_getter)

    assert result[0] == TickerFundamentals(
        ticker="NODATA", sector=None, market_cap=None, trailing_pe=None, ev_to_fcf=None
    )


def test_fetch_fundamentals_for_candidates_tolerates_a_failing_ticker():
    def fake_info_getter(ticker):
        if ticker == "BAD":
            raise ValueError("simulated network failure")
        return {"sector": "Technology", "marketCap": 1.0, "trailingPE": 2.0, "enterpriseValue": 10.0, "freeCashflow": 5.0}

    result = fetch_fundamentals_for_candidates(["GOOD", "BAD", "GOOD2"], info_getter=fake_info_getter)

    assert [r.ticker for r in result] == ["GOOD", "BAD", "GOOD2"]
    assert result[1] == TickerFundamentals(ticker="BAD", sector=None, market_cap=None, trailing_pe=None, ev_to_fcf=None)
    assert result[0].sector == "Technology"
    assert result[2].sector == "Technology"


def test_fetch_fundamentals_for_candidates_preserves_order_and_count():
    def fake_info_getter(ticker):
        return {"sector": ticker, "marketCap": 1.0, "trailingPE": 1.0, "enterpriseValue": 1.0, "freeCashflow": 1.0}

    result = fetch_fundamentals_for_candidates(["A", "B", "C"], info_getter=fake_info_getter)

    assert [r.ticker for r in result] == ["A", "B", "C"]
    assert [r.sector for r in result] == ["A", "B", "C"]
