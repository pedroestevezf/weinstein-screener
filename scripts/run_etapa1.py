"""Script de orquestación: descarga el universo US, ejecuta la Etapa 1
(pre-screening grueso) y escribe la shortlist resultante a un CSV.

Uso:
    .venv/bin/python scripts/run_etapa1.py [--limit N] [opciones...]

Este script es fino (orquestación de línea de comandos), no lógica de
negocio: la lógica ya está cubierta por los tests de `weinstein_screener`.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Permite ejecutar este script directamente como
# `.venv/bin/python scripts/run_etapa1.py` desde la raíz del repo, sin
# necesidad de instalar el paquete ni depender de `pythonpath` de pytest
# (que solo aplica a pytest). Sin esto, Python solo añade el directorio
# `scripts/` a sys.path, no la raíz del repo, y el import de
# `weinstein_screener` falla.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from weinstein_screener.etapa1 import run_etapa1_screen
from weinstein_screener.universe import get_us_universe


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejecuta Etapa 1 del screener Weinstein sobre el universo US y escribe una shortlist CSV."
    )
    parser.add_argument(
        "--cache-dir",
        default="data_cache/universe",
        help="Directorio de caché del universo de tickers (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default="data_cache/etapa1_shortlist.csv",
        help="Ruta del CSV de salida con la shortlist (default: %(default)s)",
    )
    parser.add_argument("--distance-pct", type=float, default=7.5, help="Umbral de distancia %% a la MA (default: %(default)s)")
    parser.add_argument("--ma-window", type=int, default=30, help="Ventana de la media móvil semanal (default: %(default)s)")
    parser.add_argument("--slope-lookback", type=int, default=4, help="Lookback para pendiente de la MA (default: %(default)s)")
    parser.add_argument("--batch-size", type=int, default=100, help="Tamaño de lote de descarga OHLCV (default: %(default)s)")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Si se indica, solo screenea los primeros N tickers del universo (útil para smoke tests baratos)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    tickers = get_us_universe(cache_dir=Path(args.cache_dir))
    if args.limit is not None:
        tickers = tickers[: args.limit]

    candidates = run_etapa1_screen(
        tickers,
        batch_size=args.batch_size,
        distance_pct_threshold=args.distance_pct,
        ma_window=args.ma_window,
        slope_lookback=args.slope_lookback,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "distance_pct", "ma_rising"])
        for candidate in candidates:
            writer.writerow([candidate.ticker, candidate.distance_pct, candidate.ma_rising])

    print(f"{len(candidates)} candidatos de {len(tickers)} tickers screenados")


if __name__ == "__main__":
    main()
