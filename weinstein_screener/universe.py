from __future__ import annotations

import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

# Excluye instrumentos que no son acciones comunes "puras": SPAC units/warrants/rights,
# preferentes, ADS/ADR (depositary shares) y vehículos de adquisición/trust. El \b antes
# del término y el "s?" opcional (en vez de quitar el \b final) evitan tanto el falso
# negativo real detectado en el prototipo ("Units" no matcheaba con `unit\b`) como un
# posible falso positivo por matchear el fragmento dentro de otra palabra.
_EXCLUDE_NAME_PATTERN = re.compile(
    r"\bunits?\b|\bwarrants?\b|\brights?\b|\bpreferred\b|\bdepositary\b|\bacquisition\b|\btrust\b",
    re.IGNORECASE,
)


@dataclass
class SymbolRecord:
    symbol: str
    name: str
    test_issue: bool
    etf: bool


def _bool_flag(value: str) -> bool:
    return value.strip().upper() == "Y"


def parse_nasdaq_listed(text: str) -> list[SymbolRecord]:
    """Parsea nasdaqlisted.txt (columnas: Symbol|Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares).

    Ignora la fila de cabecera y la fila de pie ("File Creation Time: ...") sin
    lanzar excepción: cualquier línea que no tenga exactamente 8 campos se descarta.
    """
    records: list[SymbolRecord] = []
    lines = text.splitlines()
    for line in lines[1:]:  # descarta cabecera
        fields = line.split("|")
        if len(fields) != 8:
            continue  # fila de pie u otra línea no-datos
        symbol, name, _market_category, test_issue, _financial_status, _round_lot, etf, _next_shares = fields
        if not symbol:
            continue
        records.append(
            SymbolRecord(
                symbol=symbol.strip(),
                name=name.strip(),
                test_issue=_bool_flag(test_issue),
                etf=_bool_flag(etf),
            )
        )
    return records


def parse_other_listed(text: str) -> list[SymbolRecord]:
    """Parsea otherlisted.txt (columnas: ACT Symbol|Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol).

    Nótese que ETF y Test Issue están en posiciones distintas que en nasdaqlisted.txt.
    """
    records: list[SymbolRecord] = []
    lines = text.splitlines()
    for line in lines[1:]:  # descarta cabecera
        fields = line.split("|")
        if len(fields) != 8:
            continue  # fila de pie u otra línea no-datos
        symbol, name, _exchange, _cqs_symbol, etf, _round_lot, test_issue, _nasdaq_symbol = fields
        if not symbol:
            continue
        records.append(
            SymbolRecord(
                symbol=symbol.strip(),
                name=name.strip(),
                test_issue=_bool_flag(test_issue),
                etf=_bool_flag(etf),
            )
        )
    return records


def filter_common_stock(records: list[SymbolRecord]) -> list[str]:
    """Filtra a tickers de acciones comunes: descarta test issues, ETFs y nombres
    que matcheen el patrón de instrumentos no-equity (units, warrants, rights, etc.)."""
    return [
        r.symbol
        for r in records
        if not r.test_issue and not r.etf and not _EXCLUDE_NAME_PATTERN.search(r.name)
    ]


def _default_downloader(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode()


def get_us_universe(
    cache_dir: Path,
    max_age_days: int = 7,
    downloader=None,
) -> list[str]:
    """Devuelve la lista ordenada de tickers US (NYSE + Nasdaq) de acciones comunes.

    Cachea la lista ya combinada/filtrada/deduplicada como texto plano (una línea
    por ticker) porque el universo cambia poco: no hace falta re-descargar en cada
    ejecución. `downloader` es inyectable para tests, igual que `fetch_ohlcv`.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "us_universe.txt"

    if cache_path.exists():
        age_seconds = time.time() - cache_path.stat().st_mtime
        if age_seconds <= max_age_days * 86400:
            return cache_path.read_text().splitlines()

    download = downloader or _default_downloader
    nasdaq_text = download(NASDAQ_LISTED_URL)
    other_text = download(OTHER_LISTED_URL)

    records = parse_nasdaq_listed(nasdaq_text) + parse_other_listed(other_text)
    tickers = sorted(set(filter_common_stock(records)))

    cache_path.write_text("\n".join(tickers))
    return tickers
