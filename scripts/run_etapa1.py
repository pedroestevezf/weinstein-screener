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
import math
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

# Umbral simple y documentado para distinguir "corrida degradada por fallos"
# de "corrida limpia con pocos/ningún candidato real". Cualquiera de las dos
# condiciones basta para considerar la corrida fallida.
MAX_BATCH_FAILURE_RATE = 0.2


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

    result = run_etapa1_screen(
        tickers,
        batch_size=args.batch_size,
        distance_pct_threshold=args.distance_pct,
        ma_window=args.ma_window,
        slope_lookback=args.slope_lookback,
    )
    candidates = result.candidates

    total_batches = math.ceil(len(tickers) / args.batch_size) if tickers else 0
    batch_failure_rate = (result.batches_failed / total_batches) if total_batches else 0.0
    run_failed = batch_failure_rate > MAX_BATCH_FAILURE_RATE or (
        result.tickers_attempted > 0 and result.tickers_screened == 0
    )

    output_path = Path(args.output)
    if run_failed and not candidates:
        # No sobrescribir una shortlist previa buena con un resultado vacío
        # cuando hay indicios claros de que la corrida falló (no cuando el
        # mercado genuinamente no ofrece candidatos ahora mismo).
        print(
            f"AVISO: no se escribe {output_path} — 0 candidatos y la corrida "
            "parece haber fallado (ver detalle de fallos abajo), se conserva "
            "la shortlist existente si la hay.",
            file=sys.stderr,
        )
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["ticker", "distance_pct", "ma_rising"])
            for candidate in candidates:
                writer.writerow(
                    [candidate.ticker, candidate.distance_pct, candidate.ma_rising]
                )

    print(
        f"{len(candidates)} candidatos de {result.tickers_screened} tickers screenados "
        f"({result.tickers_attempted} intentados, "
        f"{result.batches_failed}/{total_batches} lotes fallidos)"
    )

    if run_failed:
        print(
            "AVISO: tasa de fallos alta en la corrida de Etapa 1 "
            f"({result.batches_failed}/{total_batches} lotes fallidos = "
            f"{batch_failure_rate:.0%}, {result.tickers_screened}/"
            f"{result.tickers_attempted} tickers screenados exitosamente) "
            "— posible fallo de la fuente de datos.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
