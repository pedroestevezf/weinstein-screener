# Plan 2 de 6 — Estructura Wyckoff y CRT — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> ⚠️ **Terminología superada — este documento es un registro histórico de ejecución, no la API actual.** `find_distribution` y el campo `distribution_index` de `WyckoffStructure`, tal como aparecen en el código de este plan, fueron renombrados a **`find_jac`** y **`jac_index`** en la revisión posterior "Plan 4 de 6 — revisión JAC/BUEC" (`2026-08-10-plan4-revision-jac-buec-range-target.md`). El motivo: "Distribution" en Wyckoff clásico designa una estructura de techo bajista — lo opuesto a lo que esta función detecta (una ruptura alcista con volumen, Fase D) — mientras que JAC (Jump Across the Creek) es el término correcto para ese evento. **No copiar el código de este documento tal cual** — usar los nombres actuales de `weinstein_screener/wyckoff.py`.

**Goal:** Detectar, sobre datos semanales, una estructura de Acumulación/Reacumulación de Wyckoff (Selling Climax → Automatic Rally → Secondary Test → Fase B → Spring/Distribution), unificada con el modelo CRT tal como define la sección 4-5 del documento de diseño.

**Architecture:** Un único módulo `weinstein_screener/wyckoff.py` con funciones puras encadenadas (cada fase del patrón es una función independiente y testeable), más una función orquestadora `detect_wyckoff_structure` que las compone y devuelve un resultado estructurado (`WyckoffStructure`, un dataclass). Todas las funciones trabajan sobre el mismo tipo de DataFrame semanal que produce `weinstein_screener.data` (columnas `Open/High/Low/Close/Volume`), usando posiciones enteras (`iloc`) para navegar semanas.

**Tech Stack:** Python 3.9+, pandas (ya en requirements.txt — no se añade ninguna dependencia nueva).

## Global Constraints

- Python 3.9+, entorno virtual local en `.venv/` (ya existente del Plan 1).
- Dependencias pinneadas en `requirements.txt` con cota superior — no se añade ninguna dependencia nueva en este plan.
- Todos los umbrales/ventanas son argumentos de función con valor por defecto, nunca constantes hardcodeadas — están marcados como "a validar en backtest" y deben poder variarse sin tocar el código interno.
- Ninguna función de este plan hace I/O (red, disco) — todas son funciones puras sobre un DataFrame ya cargado en memoria. Los tests no requieren red ni filesystem real.
- Todas las funciones de búsqueda usan **solo datos hasta la semana que están evaluando** (nunca miran hacia adelante / no hay look-ahead bias) — esto es crítico porque el sistema se usará para generar alertas en tiempo real, no solo para backtesting retrospectivo.

## Alcance de este plan (2 de 6)

Cubre únicamente la detección de la estructura Wyckoff/CRT sobre datos semanales ya cargados (no descarga datos — usa `weinstein_screener.data` del Plan 1 externamente, pero este plan no lo importa). Cubre:
- Detección de Selling Climax (SC) y selección del más reciente dentro de una ventana.
- Detección de Automatic Rally (AR).
- Detección de Secondary Test (ST), con validación de vigencia (recencia) y de la ratio Fase B / Fase A.
- Detección de Spring (Manipulation) y Distribution — la parte CRT unificada con Wyckoff.
- Una función orquestadora que compone todo lo anterior en un único resultado.

**Fuera de alcance** (planes siguientes): las 3 entradas ICT (Order Block, FVG, MSS), la proyección PO3 de salida, el importador de la Etapa 1, y la app Streamlit.

## Parámetros de este plan y sus valores por defecto (todos "a validar en backtest")

| Parámetro | Valor por defecto | Qué controla |
|---|---|---|
| `range_lookback` | 10 semanas | Ventana para el rango medio que define un Selling Climax |
| `volume_lookback` | 12 semanas | Ventana para el percentil 80 de volumen del Selling Climax |
| `volume_percentile` | 80 | Percentil de volumen mínimo del Selling Climax |
| `range_multiplier` | 2.0 | El rango del SC debe superar 2x el rango medio |
| `new_low_lookback` | 10 semanas | El mínimo del SC debe ser un nuevo mínimo de N semanas |
| `sc_search_window` | 52 semanas | Ventana hacia atrás para buscar el SC más reciente |
| `ar_window` | 12 semanas | Ventana tras el SC para buscar el Automatic Rally |
| `st_window` | 12 semanas | Ventana tras el AR para buscar el Secondary Test |
| `st_tol_low` / `st_tol_high` | 0.98 / 1.10 | Tolerancia del retest del ST respecto al mínimo del SC |
| `phase_a_recency_weeks` | 26 semanas | El ST debe haber ocurrido dentro de esta ventana para considerarse vigente |
| `phase_b_ratio` | 1.5 | Duración mínima de la Fase B relativa a la Fase A |
| `spring_close_tolerance` | 0.03 (±3%) | Tolerancia del cierre del Spring respecto al mínimo del rango |
| `spring_close_position_min` | 0.5 | Posición mínima del cierre dentro del rango de su propia vela |

---

### Task 1: Detección y selección del Selling Climax

**Files:**
- Create: `weinstein_screener/wyckoff.py`
- Test: `tests/test_wyckoff.py`

**Interfaces:**
- Consumes: nada (primer módulo del plan, opera sobre cualquier DataFrame semanal OHLCV).
- Produces:
  - `find_selling_climax_candidates(df: pd.DataFrame, range_lookback: int = 10, volume_lookback: int = 12, volume_percentile: float = 80, range_multiplier: float = 2.0, new_low_lookback: int = 10) -> pd.Series` — serie booleana, `True` en semanas candidatas a Selling Climax.
  - `select_most_recent_sc(candidates: pd.Series, as_of: int, search_window: int = 52) -> int | None` — posición entera (`iloc`) del candidato `True` más reciente dentro de `[as_of - search_window + 1, as_of]`, o `None` si no hay ninguno.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_wyckoff.py`:

```python
import math

import pandas as pd
import pytest

from weinstein_screener.wyckoff import find_selling_climax_candidates, select_most_recent_sc


def _weekly_df(rows):
    dates = pd.date_range("2020-01-06", periods=len(rows), freq="W-MON")
    return pd.DataFrame(rows, index=dates)


def _wyckoff_scenario_rows():
    """Escenario sintético verificado end-to-end (ver docs/superpowers/plans/2026-08-09-plan2-wyckoff-crt-structure.md):
    SC en índice 15, AR en 20, ST en 24, Spring en 35, Distribution en 39.
    """
    rows = []
    price = 150.0
    for _ in range(15):
        price -= 1.5
        rows.append({"Open": price + 1, "High": price + 2, "Low": price - 1, "Close": price, "Volume": 1_000_000})
    sc_low = price - 15
    rows.append({"Open": price - 1, "High": price + 1, "Low": sc_low, "Close": price - 5, "Volume": 5_000_000})
    price = price - 5
    for _ in range(5):
        price += 3
        rows.append({"Open": price - 3, "High": price + 1, "Low": price - 4, "Close": price, "Volume": 900_000})
    for _ in range(3):
        price -= 2
        rows.append({"Open": price + 2, "High": price + 3, "Low": price - 1, "Close": price, "Volume": 800_000})
    rows.append({"Open": 122, "High": 123, "Low": 115.0, "Close": 121, "Volume": 700_000})
    for i in range(10):
        c = 122 + math.sin(i) * 5
        rows.append({"Open": c - 1, "High": c + 3, "Low": c - 3, "Close": c, "Volume": 600_000 + i * 5000})
    rows.append({"Open": 114, "High": 116, "Low": 108, "Close": 113, "Volume": 900_000})
    for i in range(3):
        c = 118 + i
        rows.append({"Open": c - 1, "High": c + 2, "Low": c - 2, "Close": c, "Volume": 500_000})
    rows.append({"Open": 138, "High": 144, "Low": 137, "Close": 141, "Volume": 950_000})
    return rows


def test_find_selling_climax_candidates_flags_the_climax_week():
    rows = _wyckoff_scenario_rows()[:16]  # hasta el SC (índice 15) incluido
    df = _weekly_df(rows)

    candidates = find_selling_climax_candidates(df)

    assert candidates.iloc[15]
    assert not candidates.iloc[:15].any()


def test_find_selling_climax_candidates_none_in_calm_data():
    rows = [{"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 500_000} for _ in range(30)]
    df = _weekly_df(rows)

    candidates = find_selling_climax_candidates(df)

    assert not candidates.any()


def test_select_most_recent_sc_returns_the_climax_index():
    rows = _wyckoff_scenario_rows()  # escenario completo de 40 semanas
    df = _weekly_df(rows)
    candidates = find_selling_climax_candidates(df)

    result = select_most_recent_sc(candidates, as_of=len(df) - 1, search_window=52)

    assert result == 15


def test_select_most_recent_sc_returns_none_when_no_candidate():
    rows = [{"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 500_000} for _ in range(30)]
    df = _weekly_df(rows)
    candidates = find_selling_climax_candidates(df)

    result = select_most_recent_sc(candidates, as_of=29, search_window=52)

    assert result is None


def test_select_most_recent_sc_handles_a_duplicate_index():
    # select_most_recent_sc usa aritmética posicional, no
    # `.index.get_loc(...)`, precisamente para no romperse si el índice
    # del DataFrame tuviera timestamps duplicados.
    rows = _wyckoff_scenario_rows()
    df = _weekly_df(rows)
    candidates = find_selling_climax_candidates(df)
    candidates.index = pd.Index([candidates.index[0]] * len(candidates))

    result = select_most_recent_sc(candidates, as_of=len(df) - 1, search_window=52)

    assert result == 15
    assert isinstance(result, int)
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
source .venv/bin/activate
pytest tests/test_wyckoff.py -v
```

Esperado: FAIL — `ModuleNotFoundError: No module named 'weinstein_screener.wyckoff'`.

- [ ] **Step 3: Implementar `find_selling_climax_candidates` y `select_most_recent_sc`**

Crear `weinstein_screener/wyckoff.py`:

```python
from __future__ import annotations

import numpy as np
import pandas as pd


def find_selling_climax_candidates(
    df: pd.DataFrame,
    range_lookback: int = 10,
    volume_lookback: int = 12,
    volume_percentile: float = 80,
    range_multiplier: float = 2.0,
    new_low_lookback: int = 10,
) -> pd.Series:
    """Serie booleana: True en semanas candidatas a Selling Climax.

    Una semana es candidata si su rango (High-Low) supera `range_multiplier`
    veces el rango medio de las `range_lookback` semanas previas, su volumen
    supera el percentil `volume_percentile` de las `volume_lookback` semanas
    previas, y su mínimo es un nuevo mínimo de `new_low_lookback` semanas
    (confirma que hay una tendencia bajista previa real). Todas las ventanas
    usan `.shift(1)` para no incluir la propia semana evaluada (sin look-ahead).
    """
    week_range = df["High"] - df["Low"]
    avg_range = week_range.shift(1).rolling(range_lookback).mean()
    volume_threshold = (
        df["Volume"].shift(1).rolling(volume_lookback).apply(lambda s: np.percentile(s, volume_percentile))
    )
    prior_low = df["Low"].shift(1).rolling(new_low_lookback).min()
    is_new_low = df["Low"] < prior_low

    return (week_range > range_multiplier * avg_range) & (df["Volume"] > volume_threshold) & is_new_low


def select_most_recent_sc(candidates: pd.Series, as_of: int, search_window: int = 52) -> int | None:
    """Posición entera del candidato a SC más reciente dentro de la ventana
    `[as_of - search_window + 1, as_of]`, o None si no hay ninguno.

    Usa aritmética posicional en vez de convertir a etiquetas del índice y
    volver con `.index.get_loc(...)` — ese ida y vuelta por etiqueta se
    rompe silenciosamente (devuelve un `slice` en vez de un entero) si el
    índice del DataFrame tuviera timestamps duplicados.
    """
    start = max(0, as_of - search_window + 1)
    window = candidates.iloc[start : as_of + 1].to_numpy()
    hits = np.flatnonzero(window)
    if hits.size == 0:
        return None
    return start + int(hits[-1])
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_wyckoff.py -v
```

Esperado: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/wyckoff.py tests/test_wyckoff.py
git commit -m "feat: add Selling Climax detection and selection"
```

---

### Task 2: Detección del Automatic Rally

**Files:**
- Modify: `weinstein_screener/wyckoff.py`
- Test: `tests/test_wyckoff.py`

**Interfaces:**
- Consumes: nada directamente (recibe `sc_index` ya calculado por `select_most_recent_sc` de Task 1).
- Produces: `find_automatic_rally(df: pd.DataFrame, sc_index: int, window: int = 12, as_of: int | None = None) -> int | None` — posición del máximo (`High`) más alto en las `window` semanas siguientes a `sc_index`, o `None` si no quedan semanas tras `sc_index`.

**Importante — `as_of` acota la búsqueda, no solo `len(df)`.** El sistema se usará tanto para cribado en vivo (donde `as_of` suele ser la última fila) como para backtest (donde se llamará con distintos valores de `as_of` sobre el mismo DataFrame completo, sin truncarlo en cada paso). Si la búsqueda solo se limita a `len(df)`, un `as_of` anterior al final del DataFrame no impide que la función mire semanas posteriores a `as_of` — eso es mirar al futuro, exactamente lo que la restricción global de "sin look-ahead" prohíbe. Por eso `as_of` es un parámetro explícito aquí (y en la Task 3), no solo en el orquestador.

- [ ] **Step 1: Añadir los tests que fallan**

Añadir a `tests/test_wyckoff.py`:

```python
from weinstein_screener.wyckoff import find_automatic_rally


def test_find_automatic_rally_locates_the_rally_peak():
    rows = _wyckoff_scenario_rows()[:21]  # hasta el AR (índice 20) incluido
    df = _weekly_df(rows)

    result = find_automatic_rally(df, sc_index=15, window=12)

    assert result == 20


def test_find_automatic_rally_returns_none_when_sc_is_the_last_row():
    rows = [{"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 500_000} for _ in range(10)]
    df = _weekly_df(rows)

    result = find_automatic_rally(df, sc_index=9, window=12)

    assert result is None


def test_find_automatic_rally_ignores_weeks_after_as_of():
    # Sin as_of, el máximo real está en el índice 20 (High=138.5). Con
    # as_of=18, la búsqueda no debe mirar más allá de la semana 18 aunque
    # el DataFrame completo tenga más filas -- el máximo dentro de
    # [16, 18] es el propio índice 18 (High=132.5).
    rows = _wyckoff_scenario_rows()[:21]
    df = _weekly_df(rows)

    result = find_automatic_rally(df, sc_index=15, window=12, as_of=18)

    assert result == 18
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_wyckoff.py -v -k automatic_rally
```

Esperado: FAIL — `ImportError: cannot import name 'find_automatic_rally'`.

- [ ] **Step 3: Implementar `find_automatic_rally`**

Añadir a `weinstein_screener/wyckoff.py`:

```python
def find_automatic_rally(
    df: pd.DataFrame, sc_index: int, window: int = 12, as_of: int | None = None
) -> int | None:
    """Posición del máximo (High) más alto en las `window` semanas siguientes a `sc_index`.

    `as_of` acota la búsqueda para que nunca mire semanas posteriores a
    `as_of` (uso en backtest sobre un DataFrame completo sin truncar). Si
    `as_of` es None, se usa la última fila del DataFrame.
    """
    limit = len(df) - 1 if as_of is None else min(as_of, len(df) - 1)
    end = min(limit + 1, sc_index + 1 + window)
    segment = df["High"].iloc[sc_index + 1 : end]
    if segment.empty:
        return None
    return int(segment.values.argmax()) + sc_index + 1
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_wyckoff.py -v
```

Esperado: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/wyckoff.py tests/test_wyckoff.py
git commit -m "feat: add Automatic Rally detection"
```

---

### Task 3: Detección del Secondary Test

**Files:**
- Modify: `weinstein_screener/wyckoff.py`
- Test: `tests/test_wyckoff.py`

**Interfaces:**
- Consumes: `sc_index` (Task 1), `ar_index` (Task 2).
- Produces: `find_secondary_test(df: pd.DataFrame, sc_index: int, ar_index: int, window: int = 12, tol_low: float = 0.98, tol_high: float = 1.10, as_of: int | None = None) -> int | None` — primera semana, dentro de las `window` semanas tras `ar_index`, cuyo mínimo retesta la zona `[SC_low * tol_low, SC_low * tol_high]` con volumen menor que el del SC.

**Mismo motivo que en la Task 2**: `as_of` acota la búsqueda para que nunca mire semanas posteriores a `as_of`, no solo `len(df)` — necesario tanto para el cribado en vivo como para el backtest sobre un DataFrame completo sin truncar.

- [ ] **Step 1: Añadir los tests que fallan**

Añadir a `tests/test_wyckoff.py`:

```python
from weinstein_screener.wyckoff import find_secondary_test


def test_find_secondary_test_locates_the_retest():
    rows = _wyckoff_scenario_rows()[:25]  # hasta el ST (índice 24) incluido
    df = _weekly_df(rows)

    result = find_secondary_test(df, sc_index=15, ar_index=20, window=12)

    assert result == 24


def test_find_secondary_test_returns_none_when_price_never_retests():
    rows = [{"Open": 100, "High": 101, "Low": 90, "Close": 95, "Volume": 2_000_000}]  # SC en índice 0
    for i in range(15):
        rows.append({"Open": 150 + i, "High": 152 + i, "Low": 149 + i, "Close": 151 + i, "Volume": 400_000})
    df = _weekly_df(rows)

    ar_index = find_automatic_rally(df, sc_index=0, window=12)
    result = find_secondary_test(df, sc_index=0, ar_index=ar_index, window=12)

    assert result is None


def test_find_secondary_test_ignores_weeks_after_as_of():
    # El ST real está en el índice 24. Con as_of=22 (antes de esa semana),
    # la búsqueda no debe encontrarlo -- ninguna semana en [21, 22] retesta
    # la zona del mínimo del SC.
    rows = _wyckoff_scenario_rows()[:25]
    df = _weekly_df(rows)

    result = find_secondary_test(df, sc_index=15, ar_index=20, window=12, as_of=22)

    assert result is None
```

(añadir `find_automatic_rally` al `import` de `weinstein_screener.wyckoff` ya existente en el archivo de test, si no está ya)

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_wyckoff.py -v -k secondary_test
```

Esperado: FAIL — `ImportError: cannot import name 'find_secondary_test'`.

- [ ] **Step 3: Implementar `find_secondary_test`**

Añadir a `weinstein_screener/wyckoff.py`:

```python
def find_secondary_test(
    df: pd.DataFrame,
    sc_index: int,
    ar_index: int,
    window: int = 12,
    tol_low: float = 0.98,
    tol_high: float = 1.10,
    as_of: int | None = None,
) -> int | None:
    """Primera semana, tras `ar_index` y dentro de `window` semanas, cuyo mínimo
    retesta la zona del mínimo del SC (`[SC_low*tol_low, SC_low*tol_high]`) con
    volumen menor que el del SC.

    `as_of` acota la búsqueda para que nunca mire semanas posteriores a
    `as_of` (uso en backtest sobre un DataFrame completo sin truncar). Si
    `as_of` es None, se usa la última fila del DataFrame.
    """
    sc_low = df["Low"].iloc[sc_index]
    sc_volume = df["Volume"].iloc[sc_index]
    limit = len(df) - 1 if as_of is None else min(as_of, len(df) - 1)
    end = min(limit + 1, ar_index + 1 + window)

    for i in range(ar_index + 1, end):
        low = df["Low"].iloc[i]
        volume = df["Volume"].iloc[i]
        if sc_low * tol_low <= low <= sc_low * tol_high and volume < sc_volume:
            return i
    return None
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_wyckoff.py -v
```

Esperado: `11 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/wyckoff.py tests/test_wyckoff.py
git commit -m "feat: add Secondary Test detection"
```

---

### Task 4: Detección del Spring (Manipulation)

**Files:**
- Modify: `weinstein_screener/wyckoff.py`
- Test: `tests/test_wyckoff.py`

**Interfaces:**
- Consumes: `st_index` (Task 3, usado como `phase_b_start`), `sc_low` = `df["Low"].iloc[sc_index]` (Task 1, calculado por quien orquesta — ver Task 6).
- Produces: `find_spring(df: pd.DataFrame, phase_b_start: int, as_of: int, sc_low: float, close_tolerance: float = 0.03, close_position_min: float = 0.5) -> int | None`.

**Importante — el rango de referencia del Spring es el de toda la estructura Wyckoff (SC=soporte, AR=resistencia), no solo el observado dentro de la Fase B.** En Wyckoff clásico, el Selling Climax marca el mínimo de la estructura y el Automatic Rally marca el máximo; el Spring existe precisamente para barrer los stops acumulados justo por debajo de ese mínimo del SC — no un mínimo más local que pueda haberse formado después, dentro de la propia Fase B. Por eso el umbral de ruptura del Spring se compara contra `sc_low` explícitamente, no contra el mínimo acumulado de la Fase B.

Definición del Spring (acordada, revisa `2026-08-09-estrategia-weinstein-wyckoff-crt-ict-design.md` sección 5 más los ajustes de esta conversación): una semana dentro de la Fase B (desde `phase_b_start` en adelante) donde:
1. El mínimo rompe **el mínimo del Selling Climax** (`Low < sc_low`).
2. El volumen supera la media de la Fase B acumulada **hasta esa semana, sin incluirla** (rango expansivo — nunca mira hacia adelante; esta media sí usa solo la Fase B, no toda la estructura, porque el volumen del propio SC es un pico atípico que distorsionaría la media de referencia).
3. El cierre está en la mitad superior o más del rango de su propia vela: `(Close-Low)/(High-Low) >= close_position_min`.
4. El cierre está dentro de un ±`close_tolerance` de `sc_low` — no hace falta que reingrese al rango, pero debe quedar cerca del mínimo del SC.

- [ ] **Step 1: Añadir los tests que fallan**

Añadir a `tests/test_wyckoff.py`:

```python
from weinstein_screener.wyckoff import find_spring


def test_find_spring_locates_the_manipulation_week():
    rows = _wyckoff_scenario_rows()[:36]  # hasta el Spring (índice 35) incluido
    df = _weekly_df(rows)

    result = find_spring(df, phase_b_start=24, as_of=35, sc_low=112.5)

    assert result == 35


def test_find_spring_returns_none_without_a_qualifying_week():
    rows = [{"Open": 100, "High": 102, "Low": 98, "Close": 100, "Volume": 500_000} for _ in range(15)]
    df = _weekly_df(rows)

    result = find_spring(df, phase_b_start=0, as_of=14, sc_low=95.0)

    assert result is None


def test_find_spring_ignores_a_low_that_does_not_reach_the_climax_low():
    # Rompe el mínimo local de la Fase B, pero NO el mínimo del Selling Climax (90.0)
    # -- no debe contar como Spring, aunque cumpla el resto de condiciones.
    rows = [{"Open": 100, "High": 102, "Low": 98, "Close": 100, "Volume": 500_000} for _ in range(5)]
    rows.append({"Open": 97, "High": 99, "Low": 95, "Close": 98.5, "Volume": 900_000})
    df = _weekly_df(rows)

    result = find_spring(df, phase_b_start=0, as_of=5, sc_low=90.0)

    assert result is None
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_wyckoff.py -v -k find_spring
```

Esperado: FAIL — `ImportError: cannot import name 'find_spring'`.

- [ ] **Step 3: Implementar `find_spring`**

Añadir a `weinstein_screener/wyckoff.py`:

```python
def find_spring(
    df: pd.DataFrame,
    phase_b_start: int,
    as_of: int,
    sc_low: float,
    close_tolerance: float = 0.03,
    close_position_min: float = 0.5,
) -> int | None:
    """Primera semana dentro de la Fase B que cumple los criterios de Spring.

    El umbral de ruptura es `sc_low` (el mínimo del Selling Climax que marca
    el soporte de TODA la estructura), no un mínimo más local observado
    solo dentro de la Fase B — así el Spring barre los stops acumulados
    bajo el soporte real de la estructura, no un mínimo circunstancial.

    El volumen medio de referencia sí se calcula de forma expansiva usando
    solo las semanas de la Fase B ANTERIORES a la semana evaluada (sin
    look-ahead) — el volumen del propio SC no se usa aquí porque es un pico
    atípico que distorsionaría la media.
    """
    for i in range(phase_b_start + 1, as_of + 1):
        prior = df.iloc[phase_b_start:i]
        avg_volume = prior["Volume"].mean()

        low = df["Low"].iloc[i]
        high = df["High"].iloc[i]
        close = df["Close"].iloc[i]
        volume = df["Volume"].iloc[i]

        if low >= sc_low or volume <= avg_volume:
            continue

        candle_range = high - low
        if candle_range == 0:
            continue

        close_position = (close - low) / candle_range
        if close_position < close_position_min:
            continue

        if sc_low * (1 - close_tolerance) <= close <= sc_low * (1 + close_tolerance):
            return i

    return None
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_wyckoff.py -v
```

Esperado: `14 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/wyckoff.py tests/test_wyckoff.py
git commit -m "feat: add Spring (manipulation) detection"
```

---

### Task 5: Detección de la Distribution

**Files:**
- Modify: `weinstein_screener/wyckoff.py`
- Test: `tests/test_wyckoff.py`

**Interfaces:**
- Consumes: `st_index` (Task 3, usado como `phase_b_start`), `ar_high` = `df["High"].iloc[ar_index]` (Task 2, calculado por quien orquesta — ver Task 6).
- Produces: `find_distribution(df: pd.DataFrame, phase_b_start: int, as_of: int, ar_high: float) -> int | None` — primera semana cuyo cierre rompe al alza **el máximo del Automatic Rally** (la resistencia real de toda la estructura), con volumen superior a la media de la Fase B hasta ese punto.

**Importante — mismo criterio que en la Task 4**: el umbral de ruptura se compara contra `ar_high` (el máximo del AR, la resistencia de toda la estructura), no contra un máximo local observado solo dentro de la Fase B — de lo contrario, una consolidación estrecha dentro de la Fase B podría "romper" un techo mucho más bajo que la resistencia real, generando una señal de Distribution prematura y falsa.

- [ ] **Step 1: Añadir los tests que fallan**

Añadir a `tests/test_wyckoff.py`:

```python
from weinstein_screener.wyckoff import find_distribution


def test_find_distribution_locates_the_breakout_week():
    rows = _wyckoff_scenario_rows()  # escenario completo de 40 semanas
    df = _weekly_df(rows)

    result = find_distribution(df, phase_b_start=24, as_of=39, ar_high=138.5)

    assert result == 39


def test_find_distribution_returns_none_without_a_breakout():
    rows = [{"Open": 100, "High": 102, "Low": 98, "Close": 100, "Volume": 500_000} for _ in range(15)]
    df = _weekly_df(rows)

    result = find_distribution(df, phase_b_start=0, as_of=14, ar_high=110.0)

    assert result is None


def test_find_distribution_ignores_a_close_that_does_not_reach_the_rally_high():
    # Rompe el máximo local de la Fase B, pero NO el máximo del Automatic Rally (110.0)
    # -- no debe contar como Distribution, aunque el volumen sea alto.
    rows = [{"Open": 100, "High": 102, "Low": 98, "Close": 100, "Volume": 500_000} for _ in range(5)]
    rows.append({"Open": 101, "High": 104, "Low": 100, "Close": 103, "Volume": 900_000})
    df = _weekly_df(rows)

    result = find_distribution(df, phase_b_start=0, as_of=5, ar_high=110.0)

    assert result is None
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_wyckoff.py -v -k find_distribution
```

Esperado: FAIL — `ImportError: cannot import name 'find_distribution'`.

- [ ] **Step 3: Implementar `find_distribution`**

Añadir a `weinstein_screener/wyckoff.py`:

```python
def find_distribution(df: pd.DataFrame, phase_b_start: int, as_of: int, ar_high: float) -> int | None:
    """Primera semana cuyo cierre rompe al alza `ar_high` (el máximo del
    Automatic Rally, la resistencia de toda la estructura) con volumen por
    encima de la media de la Fase B hasta ese punto (sin look-ahead).
    """
    for i in range(phase_b_start + 1, as_of + 1):
        prior = df.iloc[phase_b_start:i]
        avg_volume = prior["Volume"].mean()

        close = df["Close"].iloc[i]
        volume = df["Volume"].iloc[i]

        if close > ar_high and volume > avg_volume:
            return i

    return None
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_wyckoff.py -v
```

Esperado: `17 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/wyckoff.py tests/test_wyckoff.py
git commit -m "feat: add Distribution (breakout) detection"
```

---

### Task 6: Orquestador `detect_wyckoff_structure`

**Files:**
- Modify: `weinstein_screener/wyckoff.py`
- Test: `tests/test_wyckoff.py`

**Interfaces:**
- Consumes: todas las funciones de las Tasks 1-5 (`find_selling_climax_candidates`, `select_most_recent_sc`, `find_automatic_rally`, `find_secondary_test`, `find_spring`, `find_distribution`).
- Produces:
  - `WyckoffStructure` (dataclass): `sc_index: int`, `ar_index: int`, `st_index: int`, `phase_a_weeks: int`, `phase_b_weeks: int`, `phase_b_ratio_met: bool`, `range_low: float`, `range_high: float`, `spring_index: int | None`, `distribution_index: int | None`.
  - `detect_wyckoff_structure(df_weekly: pd.DataFrame, as_of: int | None = None, range_lookback: int = 10, volume_lookback: int = 12, volume_percentile: float = 80, range_multiplier: float = 2.0, new_low_lookback: int = 10, sc_search_window: int = 52, ar_window: int = 12, st_window: int = 12, st_tol_low: float = 0.98, st_tol_high: float = 1.10, phase_a_recency_weeks: int = 26, phase_b_ratio: float = 1.5, spring_close_tolerance: float = 0.03, spring_close_position_min: float = 0.5) -> WyckoffStructure | None`. Devuelve `None` si no hay SC, AR o ST encontrados, o si el ST no está dentro de `phase_a_recency_weeks` respecto a `as_of`. Si `as_of` es `None`, usa la última semana del DataFrame.

**Nota sobre `range_low`/`range_high`**: representan el rango de **toda la estructura Wyckoff**, no solo de la Fase B — `range_low = sc_low` (el mínimo del Selling Climax, el soporte real) y `range_high = ar_high` (el máximo del Automatic Rally, la resistencia real). Es el mismo rango que usan internamente `find_spring` y `find_distribution` (Tasks 4 y 5) para sus umbrales de ruptura — se exponen aquí para que capas posteriores (ICT, la app Streamlit) puedan dibujar y razonar sobre el mismo rango, en vez de recalcularlo por su cuenta.

**Nota sobre `phase_b_ratio_met`**: es **informativo, no un filtro que la función aplique por su cuenta**. La función devuelve una estructura siempre que encuentre SC/AR/ST vigentes, se cumpla o no el ratio 1.5x — porque ese ratio está marcado como "a validar en backtest" (sección 8 del documento de diseño) y debe poder analizarse con y sin el filtro aplicado, no quedar hardcodeado como condición de corte dentro de la detección. Quien consuma `WyckoffStructure` decide si actúa sobre estructuras con `phase_b_ratio_met=False`.

**Importante — `as_of` debe propagarse a `find_automatic_rally` y `find_secondary_test`, no solo usarse para el chequeo de vigencia y para `find_spring`/`find_distribution`.** Ambas funciones (Tasks 2 y 3) aceptan ahora un parámetro `as_of` explícito precisamente para que el orquestador se lo pase — si no se propaga, esas dos funciones seguirían buscando hasta `len(df_weekly)`, lo que permite que la estructura detectada incluya semanas posteriores a `as_of` (mirar al futuro) cuando se llama con un `as_of` distinto a la última fila del DataFrame, exactamente el escenario de un backtest sobre el DataFrame completo sin truncar.

- [ ] **Step 1: Añadir los tests que fallan**

Añadir a `tests/test_wyckoff.py`:

```python
from weinstein_screener.wyckoff import detect_wyckoff_structure


def test_detect_wyckoff_structure_finds_the_full_pattern():
    rows = _wyckoff_scenario_rows()
    df = _weekly_df(rows)

    result = detect_wyckoff_structure(df)

    assert result is not None
    assert result.sc_index == 15
    assert result.ar_index == 20
    assert result.st_index == 24
    assert result.phase_a_weeks == 9
    assert result.phase_b_weeks == 15
    assert result.phase_b_ratio_met is True
    assert result.range_low == pytest.approx(112.5)
    assert result.range_high == pytest.approx(138.5)
    assert result.spring_index == 35
    assert result.distribution_index == 39


def test_detect_wyckoff_structure_returns_none_without_a_climax():
    rows = [{"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 500_000} for _ in range(40)]
    df = _weekly_df(rows)

    result = detect_wyckoff_structure(df)

    assert result is None


def test_detect_wyckoff_structure_returns_none_when_secondary_test_is_stale():
    # 15 semanas planas de más (no 30): el ST queda a 30 semanas de as_of
    # (> phase_a_recency_weeks=26, así que caduca) pero el SC (índice 15)
    # sigue dentro de la ventana de búsqueda por defecto (52 semanas desde
    # as_of=54), así que este test SÍ ejercita la comprobación de caducidad
    # -- no un rechazo anterior por no encontrar el SC.
    rows = _wyckoff_scenario_rows() + [
        {"Open": 125, "High": 126, "Low": 124, "Close": 125, "Volume": 400_000} for _ in range(15)
    ]
    df = _weekly_df(rows)

    result = detect_wyckoff_structure(df)

    assert result is None


def test_detect_wyckoff_structure_never_looks_past_as_of():
    # Propiedad: para cualquier as_of, el resultado con el DataFrame completo
    # (pasando as_of) debe ser idéntico al resultado truncando el DataFrame
    # en ese mismo punto. Si alguna función interna mira más allá de as_of,
    # esta prueba lo detecta para el punto exacto donde ocurre.
    rows = _wyckoff_scenario_rows()
    df = _weekly_df(rows)

    for k in range(len(df)):
        result_with_as_of = detect_wyckoff_structure(df, as_of=k)
        result_truncated = detect_wyckoff_structure(df.iloc[: k + 1])

        assert result_with_as_of == result_truncated, f"mismatch at as_of={k}"
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_wyckoff.py -v -k detect_wyckoff_structure
```

Esperado: FAIL — `ImportError: cannot import name 'detect_wyckoff_structure'`.

- [ ] **Step 3: Implementar `WyckoffStructure` y `detect_wyckoff_structure`**

Añadir a `weinstein_screener/wyckoff.py` (añadir `from dataclasses import dataclass` a las importaciones del inicio del archivo):

```python
@dataclass
class WyckoffStructure:
    sc_index: int
    ar_index: int
    st_index: int
    phase_a_weeks: int
    phase_b_weeks: int
    phase_b_ratio_met: bool  # informativo -- no aplicado como filtro, ver nota en la Task 6 del plan
    range_low: float  # = mínimo del Selling Climax (soporte real). NUNCA un mínimo local de la Fase B.
    range_high: float  # = máximo del Automatic Rally (resistencia real). NUNCA un máximo local de la Fase B.
    spring_index: int | None
    distribution_index: int | None


def detect_wyckoff_structure(
    df_weekly: pd.DataFrame,
    as_of: int | None = None,
    range_lookback: int = 10,
    volume_lookback: int = 12,
    volume_percentile: float = 80,
    range_multiplier: float = 2.0,
    new_low_lookback: int = 10,
    sc_search_window: int = 52,
    ar_window: int = 12,
    st_window: int = 12,
    st_tol_low: float = 0.98,
    st_tol_high: float = 1.10,
    phase_a_recency_weeks: int = 26,
    phase_b_ratio: float = 1.5,
    spring_close_tolerance: float = 0.03,
    spring_close_position_min: float = 0.5,
) -> WyckoffStructure | None:
    """Detecta la estructura Wyckoff/CRT más reciente y vigente en `df_weekly`.

    Devuelve None si no se encuentra SC, AR o ST, o si el ST encontrado ya
    no está vigente (más antiguo que `phase_a_recency_weeks` respecto a
    `as_of`).
    """
    as_of = len(df_weekly) - 1 if as_of is None else min(as_of, len(df_weekly) - 1)

    candidates = find_selling_climax_candidates(
        df_weekly, range_lookback, volume_lookback, volume_percentile, range_multiplier, new_low_lookback
    )
    sc_index = select_most_recent_sc(candidates, as_of, sc_search_window)
    if sc_index is None:
        return None

    ar_index = find_automatic_rally(df_weekly, sc_index, ar_window, as_of)
    if ar_index is None:
        return None

    st_index = find_secondary_test(df_weekly, sc_index, ar_index, st_window, st_tol_low, st_tol_high, as_of)
    if st_index is None:
        return None

    if (as_of - st_index) > phase_a_recency_weeks:
        return None

    phase_a_weeks = st_index - sc_index
    phase_b_weeks = as_of - st_index
    phase_b_ratio_met = phase_b_weeks >= phase_b_ratio * phase_a_weeks

    # El rango de referencia es el de TODA la estructura (SC=soporte, AR=resistencia),
    # no un rango más local observado solo dentro de la Fase B — ver la nota en la
    # Task 4 y la Task 5 sobre por qué esto importa para el Spring y la Distribution.
    range_low = df_weekly["Low"].iloc[sc_index]
    range_high = df_weekly["High"].iloc[ar_index]

    spring_index = find_spring(
        df_weekly, st_index, as_of, range_low, spring_close_tolerance, spring_close_position_min
    )
    distribution_index = find_distribution(df_weekly, st_index, as_of, range_high)

    return WyckoffStructure(
        sc_index=sc_index,
        ar_index=ar_index,
        st_index=st_index,
        phase_a_weeks=phase_a_weeks,
        phase_b_weeks=phase_b_weeks,
        phase_b_ratio_met=phase_b_ratio_met,
        range_low=range_low,
        range_high=range_high,
        spring_index=spring_index,
        distribution_index=distribution_index,
    )
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_wyckoff.py -v
```

Esperado: `21 passed`.

- [ ] **Step 5: Ejecutar toda la suite de tests del proyecto**

```bash
pytest -v
```

Esperado: `41 passed` (20 del Plan 1 + 21 de este plan).

- [ ] **Step 6: Commit**

```bash
git add weinstein_screener/wyckoff.py tests/test_wyckoff.py
git commit -m "feat: add detect_wyckoff_structure orchestrator"
```

---

## Siguiente paso

Con este plan completado, el sistema puede tomar el DataFrame semanal de un ticker que ya esté en Weinstein Stage 2 (Plan 1) y determinar si tiene una estructura Wyckoff/CRT válida y vigente, incluyendo dónde está el Spring y la Distribution si ya ocurrieron. El **Plan 3** cubrirá las 3 entradas ICT (Order Block, FVG, cambio de estructura) en datos diarios, ancladas a los eventos que este plan detecta (Spring → Entrada 1, Distribution → Entrada 2, retest → Entrada 3).
