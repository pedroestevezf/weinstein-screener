"""Enriquece la shortlist de Etapa 1 con fundamentales (sector, cap.
mercado, PER, EV/FCF) y volumen relativo semanal.

Uso:
    .venv/bin/python scripts/enrich_shortlist.py [--input ...] [--output ...] [--cache-dir ...]

Paso semanal separado de `run_etapa1.py`, ejecutado inmediatamente
después (ver `docs/superpowers/specs/2026-08-12-plan6-dashboard-design.md`,
sección 3.1) -- nunca disparado en tiempo real por el dashboard, porque
`get_info()` no tiene equivalente en lote (~9-10 min para 943 tickers).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from weinstein_screener.data import get_cached_ohlcv
from weinstein_screener.fundamentals import fetch_fundamentals_for_candidates
from weinstein_screener.indicators import relative_volume

ENRICHED_FIELDS = [
    "ticker",
    "distance_pct",
    "ma_rising",
    "sector",
    "market_cap",
    "trailing_pe",
    "ev_to_fcf",
    "relative_volume",
]


def read_shortlist_csv(file_obj) -> list[dict]:
    reader = csv.DictReader(file_obj)
    rows = []
    for row in reader:
        rows.append(
            {
                "ticker": row["ticker"],
                "distance_pct": float(row["distance_pct"]),
                "ma_rising": row["ma_rising"] == "True",
            }
        )
    return rows


def build_enriched_rows(
    shortlist_rows: list[dict],
    fundamentals_by_ticker: dict,
    relative_volume_by_ticker: dict,
) -> list[dict]:
    rows = []
    for entry in shortlist_rows:
        ticker = entry["ticker"]
        fundamentals = fundamentals_by_ticker.get(ticker)
        rows.append(
            {
                "ticker": ticker,
                "distance_pct": entry["distance_pct"],
                "ma_rising": entry["ma_rising"],
                "sector": fundamentals.sector if fundamentals else None,
                "market_cap": fundamentals.market_cap if fundamentals else None,
                "trailing_pe": fundamentals.trailing_pe if fundamentals else None,
                "ev_to_fcf": fundamentals.ev_to_fcf if fundamentals else None,
                "relative_volume": relative_volume_by_ticker.get(ticker),
            }
        )
    return rows


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enriquece la shortlist de Etapa 1 con fundamentales y volumen relativo.")
    parser.add_argument("--input", default="data_cache/etapa1_shortlist.csv")
    parser.add_argument("--output", default="data_cache/etapa1_shortlist_enriched.csv")
    parser.add_argument("--cache-dir", default="data_cache/ohlcv")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    with open(args.input, newline="") as f:
        shortlist_rows = read_shortlist_csv(f)

    tickers = [row["ticker"] for row in shortlist_rows]
    fundamentals_list = fetch_fundamentals_for_candidates(tickers)
    fundamentals_by_ticker = {f.ticker: f for f in fundamentals_list}

    relative_volume_by_ticker = {}
    for ticker in tickers:
        try:
            df_weekly = get_cached_ohlcv(ticker, interval="1wk", cache_dir=Path(args.cache_dir), period="2y")
            relative_volume_by_ticker[ticker] = relative_volume(df_weekly)
        except Exception:
            relative_volume_by_ticker[ticker] = None

    enriched_rows = build_enriched_rows(shortlist_rows, fundamentals_by_ticker, relative_volume_by_ticker)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ENRICHED_FIELDS)
        writer.writeheader()
        writer.writerows(enriched_rows)

    print(f"{len(enriched_rows)} tickers enriquecidos -> {output_path}")


if __name__ == "__main__":
    main()
