import os
from pathlib import Path

from weinstein_screener.universe import (
    SymbolRecord,
    filter_common_stock,
    get_us_universe,
    parse_nasdaq_listed,
    parse_other_listed,
)

# Trailer line real: pipe-padded al número total de columnas del formato (8),
# no un único campo suelto — "File Creation Time: ...|||||||" (7 pipes -> 8
# campos). `len(fields) != 8` NO detecta esto (ver FIX 2 del review final).
NASDAQ_LISTED_FIXTURE = "\n".join(
    [
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares",
        "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N",
        "ZWZZT|Test Issue Symbol|Q|Y|N|100|N|N",
        "QQQ|Invesco QQQ Trust|Q|N|N|100|Y|N",
        "File Creation Time: 0812202606:00|||||||",
    ]
)

OTHER_LISTED_FIXTURE = "\n".join(
    [
        "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol",
        "A|Agilent Technologies, Inc. Common Stock|N|A|N|100|N|A",
        "ZTEST|Some Test Symbol|N|ZTEST|N|100|Y|ZTEST",
        "File Creation Time: 0812202606:00|||||||",
    ]
)


def test_parse_nasdaq_listed_parses_data_rows():
    records = parse_nasdaq_listed(NASDAQ_LISTED_FIXTURE)

    assert records == [
        SymbolRecord(symbol="AAPL", name="Apple Inc. - Common Stock", test_issue=False, etf=False),
        SymbolRecord(symbol="ZWZZT", name="Test Issue Symbol", test_issue=True, etf=False),
        SymbolRecord(symbol="QQQ", name="Invesco QQQ Trust", test_issue=False, etf=True),
    ]


def test_parse_nasdaq_listed_drops_trailer_row():
    records = parse_nasdaq_listed(NASDAQ_LISTED_FIXTURE)

    symbols = [r.symbol for r in records]
    assert "File Creation Time: 0812202606:00" not in symbols
    assert not any("File Creation Time" in r.name for r in records)


def test_parse_other_listed_parses_data_rows():
    records = parse_other_listed(OTHER_LISTED_FIXTURE)

    assert records == [
        SymbolRecord(
            symbol="A", name="Agilent Technologies, Inc. Common Stock", test_issue=False, etf=False
        ),
        SymbolRecord(symbol="ZTEST", name="Some Test Symbol", test_issue=True, etf=False),
    ]


def test_parse_other_listed_drops_trailer_row():
    records = parse_other_listed(OTHER_LISTED_FIXTURE)

    symbols = [r.symbol for r in records]
    assert "File Creation Time: 0812202606:00" not in symbols


def test_parse_nasdaq_listed_drops_trailer_row_with_different_padding_width():
    # La detección no debe depender de cuántos pipes exactos trae el trailer
    # real (puede variar); confirma que se detecta también con un padding
    # distinto al de la fixture principal.
    text = "\n".join(
        [
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares",
            "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N",
            "File Creation Time: 0812202612:11||||||",
        ]
    )

    records = parse_nasdaq_listed(text)

    assert [r.symbol for r in records] == ["AAPL"]


def test_parse_nasdaq_listed_drops_any_row_with_blank_name():
    # Segunda señal de detección independiente del prefijo de texto: un
    # registro con name en blanco nunca es un dato real y debe descartarse
    # aunque el símbolo no empiece por "File Creation Time".
    text = "\n".join(
        [
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares",
            "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N",
            "JUNK||Q|N|N|100|N|N",
        ]
    )

    records = parse_nasdaq_listed(text)

    assert [r.symbol for r in records] == ["AAPL"]


def test_filter_common_stock_keeps_normal_common_stock_names():
    records = [
        SymbolRecord(symbol="AAPL", name="Apple Inc. - Common Stock", test_issue=False, etf=False),
        SymbolRecord(
            symbol="A", name="Agilent Technologies, Inc. Common Stock", test_issue=False, etf=False
        ),
    ]

    assert filter_common_stock(records) == ["AAPL", "A"]


def test_filter_common_stock_excludes_plural_units():
    # Bug real del prototipo: `unit\b` no matchea "Units" porque la "s" es un
    # carácter de palabra y por tanto no hay boundary entre "t" y "s".
    records = [
        SymbolRecord(
            symbol="ARTIU", name="Artius II Acquisition Inc. - Units", test_issue=False, etf=False
        )
    ]

    assert filter_common_stock(records) == []


def test_filter_common_stock_excludes_plural_units_without_other_keywords():
    # Aísla el caso anterior de la palabra "Acquisition" (que por sí sola ya
    # excluiría el nombre vía `\bacquisition\b`). Verificado: el patrón viejo
    # `\bunit\b` (sin el "s?") NO matchea "Units" aislado, así que este caso
    # sí distingue el fix real del bug que describe el brief.
    records = [SymbolRecord(symbol="EXUN", name="Example Corp - Units", test_issue=False, etf=False)]

    assert filter_common_stock(records) == []


def test_filter_common_stock_excludes_singular_warrant():
    records = [
        SymbolRecord(
            symbol="ARMAW", name="Armada Acquisition Corp. III - Warrant", test_issue=False, etf=False
        )
    ]

    assert filter_common_stock(records) == []


def test_filter_common_stock_excludes_warrants_without_other_keywords():
    # Un "Warrant" singular ya matchea el patrón viejo `\bwarrant\b` (sin "s?"),
    # así que aislarlo de "Acquisition" no distinguiría el bug. Usamos la forma
    # plural "Warrants", que es donde `\bwarrant\b` (sin "s?") realmente falla
    # por el mismo motivo que "Units"/"Rights": la "s" rompe el boundary final.
    records = [
        SymbolRecord(symbol="EXWA", name="Example Corp - Warrants", test_issue=False, etf=False)
    ]

    assert filter_common_stock(records) == []


def test_filter_common_stock_excludes_plural_rights():
    records = [
        SymbolRecord(
            symbol="ABONR", name="Abony Acquisition Corp. I - Rights", test_issue=False, etf=False
        )
    ]

    assert filter_common_stock(records) == []


def test_filter_common_stock_excludes_plural_rights_without_other_keywords():
    # Igual que con "Units": aísla el término de "Acquisition" para probar que
    # el fix real (no el bug del brief) es lo que excluye este nombre. Verificado:
    # el patrón viejo `\bright\b` (sin "s?") NO matchea "Rights" aislado.
    records = [SymbolRecord(symbol="EXRI", name="Example Corp - Rights", test_issue=False, etf=False)]

    assert filter_common_stock(records) == []


def test_filter_common_stock_excludes_depositary_shares():
    records = [
        SymbolRecord(
            symbol="ATAI",
            name="ATA Creativity Global - American Depositary Shares, each representing two common shares",
            test_issue=False,
            etf=False,
        )
    ]

    assert filter_common_stock(records) == []


def test_filter_common_stock_excludes_acquisition_corp_ordinary_share():
    records = [
        SymbolRecord(
            symbol="AACT",
            name="Armada Acquisition Corp. III - Class A Ordinary Share",
            test_issue=False,
            etf=False,
        )
    ]

    assert filter_common_stock(records) == []


def test_parse_other_listed_normalizes_dot_form_dual_class_symbol_to_dash():
    # "ACT Symbol" en notación de punto ("BRK.A") no matchea la convención de
    # guion de Yahoo Finance ("BRK-A") y queda silenciosamente sin datos
    # aguas abajo si no se normaliza aquí.
    text = "\n".join(
        [
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol",
            "BRK.A|Berkshire Hathaway Inc. Class A Common Stock|N|BRK.A|N|100|N|BRK.A",
        ]
    )

    records = parse_other_listed(text)

    assert records == [
        SymbolRecord(
            symbol="BRK-A",
            name="Berkshire Hathaway Inc. Class A Common Stock",
            test_issue=False,
            etf=False,
        )
    ]


def test_filter_common_stock_excludes_dollar_form_preferred_symbol_regardless_of_name():
    # Notación CQS "$" (p.ej. "BAC$L") indica acciones preferentes / clases
    # especiales, no acciones comunes — y su Security Name no siempre
    # contiene la palabra "preferred", así que el filtro de nombre no basta.
    records = [
        SymbolRecord(symbol="BAC$L", name="Bank of America Corp", test_issue=False, etf=False)
    ]

    assert filter_common_stock(records) == []


def test_filter_common_stock_excludes_test_issue_regardless_of_name():
    records = [
        SymbolRecord(symbol="AAPL", name="Apple Inc. - Common Stock", test_issue=True, etf=False)
    ]

    assert filter_common_stock(records) == []


def test_filter_common_stock_excludes_etf_regardless_of_name():
    records = [
        SymbolRecord(symbol="AAPL", name="Apple Inc. - Common Stock", test_issue=False, etf=True)
    ]

    assert filter_common_stock(records) == []


def _fake_downloader(calls: list):
    def _download(url: str) -> str:
        calls.append(url)
        if "nasdaqlisted" in url:
            return NASDAQ_LISTED_FIXTURE
        return OTHER_LISTED_FIXTURE

    return _download


def test_get_us_universe_downloads_parses_filters_dedupes_and_sorts(tmp_path: Path):
    calls: list = []

    tickers = get_us_universe(cache_dir=tmp_path, downloader=_fake_downloader(calls))

    assert len(calls) == 2
    assert tickers == ["A", "AAPL"]
    assert (tmp_path / "us_universe.txt").exists()


def test_get_us_universe_uses_fresh_cache_without_downloading(tmp_path: Path):
    calls: list = []
    downloader = _fake_downloader(calls)

    get_us_universe(cache_dir=tmp_path, downloader=downloader)
    tickers = get_us_universe(cache_dir=tmp_path, downloader=downloader)

    assert len(calls) == 2  # solo la primera llamada descarga
    assert tickers == ["A", "AAPL"]


def test_get_us_universe_redownloads_when_cache_is_stale(tmp_path: Path):
    calls: list = []
    downloader = _fake_downloader(calls)

    get_us_universe(cache_dir=tmp_path, max_age_days=1, downloader=downloader)

    cache_path = tmp_path / "us_universe.txt"
    old_time = cache_path.stat().st_mtime - (2 * 86400)
    os.utime(cache_path, (old_time, old_time))

    get_us_universe(cache_dir=tmp_path, max_age_days=1, downloader=downloader)

    assert len(calls) == 4


def test_get_us_universe_dedupes_symbols_present_in_both_files(tmp_path: Path):
    nasdaq_text = "\n".join(
        [
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares",
            "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N",
        ]
    )
    other_text = "\n".join(
        [
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol",
            "AAPL|Apple Inc. - Common Stock|N|AAPL|N|100|N|AAPL",
        ]
    )

    def downloader(url: str) -> str:
        return nasdaq_text if "nasdaqlisted" in url else other_text

    tickers = get_us_universe(cache_dir=tmp_path, downloader=downloader)

    assert tickers == ["AAPL"]
