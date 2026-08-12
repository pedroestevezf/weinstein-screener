from __future__ import annotations

import os
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


def _is_trailer_row(symbol: str, name: str) -> bool:
    """True si el registro parseado corresponde en realidad a la fila de pie
    ("File Creation Time: ...") en vez de un dato real.

    La fila de pie real viene pipe-padded hasta el mismo número de campos que
    una fila de datos (p.ej. "File Creation Time: 0812202612:11|||||||" para
    el formato de 8 columnas), así que un guard de `len(fields) != 8` NO la
    detecta: se parsea como un SymbolRecord con symbol="File Creation Time:
    ..." y name="" (los demás campos quedan vacíos por el padding). Se
    detecta por dos señales independientes, cualquiera de las dos basta:
    el símbolo empieza literalmente con el texto de la fila de pie, o el
    nombre viene vacío (ninguna fila de datos real tiene `Security Name`
    vacío).
    """
    return symbol.startswith("File Creation Time") or not name


def parse_nasdaq_listed(text: str) -> list[SymbolRecord]:
    """Parsea nasdaqlisted.txt (columnas: Symbol|Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares).

    Ignora la fila de cabecera y la fila de pie ("File Creation Time: ...") sin
    lanzar excepción: cualquier línea que no tenga exactamente 8 campos se descarta,
    y adicionalmente se descarta cualquier fila que parezca ser la fila de pie
    pipe-padded (ver `_is_trailer_row`).
    """
    records: list[SymbolRecord] = []
    lines = text.splitlines()
    for line in lines[1:]:  # descarta cabecera
        fields = line.split("|")
        if len(fields) != 8:
            continue  # fila de pie u otra línea no-datos
        symbol, name, _market_category, test_issue, _financial_status, _round_lot, etf, _next_shares = fields
        symbol = symbol.strip()
        name = name.strip()
        if not symbol:
            continue
        if _is_trailer_row(symbol, name):
            continue
        records.append(
            SymbolRecord(
                symbol=symbol,
                name=name,
                test_issue=_bool_flag(test_issue),
                etf=_bool_flag(etf),
            )
        )
    return records


def parse_other_listed(text: str) -> list[SymbolRecord]:
    """Parsea otherlisted.txt (columnas: ACT Symbol|Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol).

    Nótese que ETF y Test Issue están en posiciones distintas que en nasdaqlisted.txt.
    Igual que en `parse_nasdaq_listed`, se descarta también la fila de pie
    pipe-padded vía `_is_trailer_row` (el guard de `len(fields) != 8` no basta).
    """
    records: list[SymbolRecord] = []
    lines = text.splitlines()
    for line in lines[1:]:  # descarta cabecera
        fields = line.split("|")
        if len(fields) != 8:
            continue  # fila de pie u otra línea no-datos
        symbol, name, _exchange, _cqs_symbol, etf, _round_lot, test_issue, _nasdaq_symbol = fields
        symbol = symbol.strip()
        name = name.strip()
        if not symbol:
            continue
        if _is_trailer_row(symbol, name):
            continue
        if "." in symbol:
            # Símbolos de clase dual en notación de punto (p.ej. "BRK.A",
            # "BF.B") no matchean la convención de guion de Yahoo Finance
            # ("BRK-A") y quedan silenciosamente sin datos aguas abajo.
            # Normalizamos aquí en vez de depender de la columna "NASDAQ
            # Symbol" (su semántica varía entre filas).
            symbol = symbol.replace(".", "-")
        records.append(
            SymbolRecord(
                symbol=symbol,
                name=name,
                test_issue=_bool_flag(test_issue),
                etf=_bool_flag(etf),
            )
        )
    return records


def filter_common_stock(records: list[SymbolRecord]) -> list[str]:
    """Filtra a tickers de acciones comunes: descarta test issues, ETFs, símbolos
    con notación CQS de preferentes/otras clases especiales ("$", p.ej. "BAC$L",
    "NEE$U" — no son acciones comunes y su Security Name no siempre contiene la
    palabra "preferred"), y nombres que matcheen el patrón de instrumentos
    no-equity (units, warrants, rights, etc.)."""
    return [
        r.symbol
        for r in records
        if not r.test_issue
        and not r.etf
        and "$" not in r.symbol
        and not _EXCLUDE_NAME_PATTERN.search(r.name)
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
            try:
                return cache_path.read_text().splitlines()
            except Exception:
                pass  # caché corrupto: se re-descarga más abajo

    download = downloader or _default_downloader
    nasdaq_text = download(NASDAQ_LISTED_URL)
    other_text = download(OTHER_LISTED_URL)

    records = parse_nasdaq_listed(nasdaq_text) + parse_other_listed(other_text)
    tickers = sorted(set(filter_common_stock(records)))

    tmp_path = cache_path.with_suffix(".txt.tmp")
    tmp_path.write_text("\n".join(tickers))
    os.replace(tmp_path, cache_path)
    return tickers
