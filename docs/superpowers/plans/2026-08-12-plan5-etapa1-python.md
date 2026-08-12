# Plan 5 de 6 — Etapa 1 en Python (sustituye a TradingView Pine Screener)

**Fecha**: 2026-08-12
**Estado**: Verificado, pendiente de confirmación para ejecutar

## Contexto y motivo del cambio

El diseño original (`2026-08-09-estrategia-weinstein-wyckoff-crt-ict-design.md`, sección 3) especificaba TradingView (plan gratuito) + Pine Screener para la Etapa 1. El usuario confirmó que el Pine Screener de TradingView ahora requiere un plan de pago, invalidando esa asunción.

Se evaluaron 3 alternativas con el usuario; se eligió: **reimplementar la Etapa 1 en Python**, reutilizando el mismo pipeline de datos que la Etapa 2 (`fetch_ohlcv`, `indicators.py`). Efectos colaterales positivos: elimina el paso manual de exportación de CSV (el propio diseño lo señalaba como cuello de botella operativo, sección 9) y da control exacto sobre el cálculo de MA30w/pendiente en vez de depender de columnas aproximadas de un screener de terceros.

**Cobertura reducida en v1**: solo NYSE + Nasdaq. Eurostoxx queda fuera — no existe una fuente pública equivalente al fichero de símbolos de NASDAQ para "Eurostoxx" (que ni siquiera es una única bolsa, sino una familia de índices), y el usuario prefirió omitir Europa antes que improvisar un mapeo de bolsas incompleto. Se retoma cuando haya una fuente de universo europea decidida.

Se elimina del repo el script Pine (`pine/weinstein_screener_etapa1.pine`) y el importador de CSV (`screener_import.py` + su test) — el usuario decidió no conservarlos como vía alternativa.

## Verificaciones ya realizadas (2026-08-12, vía ejecución directa en Python)

- `https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt` y `.../otherlisted.txt` son gratuitos, públicos, sin autenticación, formato pipe-delimited estable, actualizados diariamente (verificado con `curl`/`urllib` reales).
- Universo combinado bruto: 5584 (NASDAQ) + 7547 (otherlisted, incluye NYSE/AMEX/ARCA) símbolos.
- Filtrando `Test Issue=Y`, `ETF=Y`, y nombres que contienen warrant/right/unit/preferred/depositary/acquisition corp/trust (SPACs, ETFs, ADRs, preferentes, warrants, rights, units): 3165 + 2370 → **5535 tickers únicos combinados** de acciones ordinarias candidatas. El filtro de nombres es una heurística imperfecta (un caso, `AACBU` "... - Units", no se filtró en la prueba por un bug de límite de palabra en el regex de prueba) — **el regex definitivo debe cubrirse con tests unitarios usando nombres reales problemáticos**, no darse por bueno a ojo.
- `yfinance.download()` en modo lote (lista de tickers en una sola llamada, `threads=True`) funciona correctamente mezclando tickers US y europeos con sufijo (`SAP.DE`, `ASML.AS`) en la misma llamada. 51 tickers reales (mezcla de large caps) descargados en 2.68s sin ningún ticker faltante.
- Extrapolación (no verificada a escala completa): ~5500 tickers a ese ritmo rondarían varios minutos por lote, probablemente con necesidad de trocear en lotes (p.ej. 100-200 tickers/llamada) para evitar límites no documentados de Yahoo Finance. **Riesgo abierto**: no se ha probado la descarga real a escala de miles de tickers; puede haber rate-limiting que no se manifiesta a escala de 51.

## Reutilización de código existente

- `moving_average(df, window, column)` y `ma_slope(ma, lookback)` en `indicators.py` — ya implementan exactamente el cálculo de MA30w y su pendiente. No se reimplementan.
- `ma_rising()` en `regime.py` ya calcula el booleano de pendiente ascendente con la misma semántica que necesita la Etapa 1.
- Falta únicamente la distancia porcentual `|close - ma| / ma`, que no existe como función reutilizable todavía.

## Tareas

### Task 1 — Universo US: descarga, parseo y filtro (`weinstein_screener/universe.py`)

- `parse_nasdaq_listed(text: str) -> list[SymbolRecord]` y `parse_other_listed(text: str) -> list[SymbolRecord]`: parseo puro de texto a registros (symbol, name, test_issue, etf), sin I/O — testeable con fixtures de texto inline.
- `SymbolRecord`: dataclass (`symbol: str`, `name: str`, `test_issue: bool`, `etf: bool`).
- `filter_common_stock(records: list[SymbolRecord]) -> list[str]`: aplica el filtro (excluye test issues, ETFs, y nombres que matcheen el patrón de warrant/right/unit/preferred/depositary/acquisition/trust). **El patrón regex debe testearse explícitamente contra los nombres reales problemáticos encontrados en la verificación** (p.ej. "... - Units", "... - Warrant", "... - Rights", "... Acquisition Corp...", "... Depositary Shares...") para que no se cuelen indirectamente como en la prueba exploratoria.
- `get_us_universe(cache_dir: Path, max_age_days: int = 7, downloader=None) -> list[str]`: función con I/O que descarga ambos ficheros (o usa caché local si es reciente — el universo cambia poco, no hace falta re-descargar en cada ejecución), parsea, filtra, deduplica y ordena. `downloader` inyectable para tests (mismo patrón que `fetch_ohlcv`).

### Task 2 — Distancia porcentual a la media móvil (`weinstein_screener/indicators.py`)

- `pct_distance_from_ma(price: pd.Series, ma: pd.Series) -> pd.Series`: `(price - ma).abs() / ma * 100`. Función pura, un añadido pequeño al módulo existente.

### Task 3 — Screening Etapa 1 por ticker (`weinstein_screener/etapa1.py`)

- `Etapa1Candidate` dataclass: `ticker: str`, `distance_pct: float`, `ma_rising: bool`, `is_candidate: bool`.
- `screen_ticker(ticker: str, df_weekly: pd.DataFrame, distance_pct_threshold: float = 7.5, ma_window: int = 30, slope_lookback: int = 4) -> Etapa1Candidate | None`: calcula MA30w y su pendiente sobre `df_weekly`, evalúa sobre la **última semana cerrada** disponible. Devuelve `None` si no hay suficientes semanas de histórico para calcular la MA (`len(df_weekly) < ma_window`), en vez de lanzar una excepción — reutiliza el criterio ya establecido en el resto del proyecto de fallar de forma silenciosa/explícita con `None` antes que con una excepción no controlada en un pipeline de barrido masivo.
- `is_candidate` = `distance_pct <= distance_pct_threshold and ma_rising`.

### Task 4 — Orquestador: descarga en lote + shortlist (`weinstein_screener/etapa1.py`)

- `run_etapa1_screen(tickers: list[str], cache_dir: Path, batch_size: int = 100, distance_pct_threshold: float = 7.5, ma_window: int = 30, slope_lookback: int = 4, downloader=None) -> list[Etapa1Candidate]`: trocea `tickers` en lotes de `batch_size`, descarga OHLCV semanal en bloque por lote (vía `downloader` inyectable, mismo patrón de test que el resto del proyecto — no se golpea la red real en los tests), aplica `screen_ticker` a cada uno.
- **Manejo de fallos por ticker**: si un ticker individual falla la descarga o no tiene datos suficientes, se omite (no se aborta el lote completo) — importante porque a escala de miles de tickers, algunos fallos individuales son inevitables (deslistados, sin histórico suficiente, etc.).
- Devuelve solo los candidatos con `is_candidate = True`, ordenados por `distance_pct` ascendente.

### Task 5 — Script de ejecución semanal (`scripts/run_etapa1.py`)

- Script de línea de comandos: obtiene el universo (`get_us_universe`), ejecuta `run_etapa1_screen`, y escribe la shortlist resultante a un CSV/parquet en una ruta configurable — este fichero es el que alimenta directamente la Etapa 2 (ya no hace falta el importador manual eliminado).
- No requiere el mismo nivel de cobertura de tests que los módulos anteriores (es un script fino de orquestación, no lógica de negocio) pero sí una verificación manual de que se ejecuta de punta a punta contra un subconjunto pequeño real del universo (p.ej. 20-30 tickers) antes de darlo por bueno.

## Riesgos y supuestos a vigilar (no bloquean el plan, documentados para la revisión final)

- Rate-limiting de Yahoo Finance a escala de miles de tickers: no verificado, solo extrapolado desde una prueba de 51 tickers.
- El fichero de símbolos de NASDAQ/NYSE puede incluir clases de acciones duales, ADRs no filtrados por el regex de nombre, u otros ruidos no cubiertos por la heurística — se acepta como limitación conocida de v1, no un objetivo de precisión perfecta.
- `get_us_universe` con caché de 7 días implica que altas/bajas de cotización muy recientes no se reflejan hasta la siguiente descarga — aceptable dado que el universo cambia lentamente.

## Fuera de alcance de este plan

- Cobertura de Eurostoxx (pendiente, sin fuente de universo decidida).
- Cualquier lógica de Etapa 2 (ya implementada en planes 1-4).
