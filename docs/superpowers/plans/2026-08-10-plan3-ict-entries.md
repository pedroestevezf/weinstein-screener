# Plan 3 de 6 — Entradas ICT (Order Block, FVG, MSS, retest) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> ⚠️ **Terminología superada — este documento es un registro histórico de ejecución, no la API actual.** El disparador de la Entrada 3, llamado "retest" en este documento (`RetestResult`, `find_retest`, `retest_index`), fue renombrado a **`BuecResult`**, **`find_buec`** y **`buec_index`** en la revisión posterior "Plan 4 de 6 — revisión JAC/BUEC" (`2026-08-10-plan4-revision-jac-buec-range-target.md`). BUEC = Back Up to Edge of Creek, el término clásico de Wyckoff para ese evento. **Importante**: el "retest" dentro de `find_spring_reentry_mss` (Entrada 1) es un concepto *distinto* (el redescenso hacia el mínimo del Spring tras el reingreso) y **no** se renombró — sigue llamándose "retest" tanto aquí como en el código actual. **No copiar el código de este documento tal cual** — usar los nombres actuales de `weinstein_screener/ict.py`.

**Goal:** Detectar, sobre datos diarios, los disparadores de las Entradas 1 y 3 (ICT: cambio de estructura/reingreso al rango, Order Block, Fair Value Gap, retest con volumen descendente o vela "no supply"), ancladas a los eventos que detecta el Plan 2 (`sc_low`, `ar_high`) sobre datos semanales.

**Architecture:** Un módulo `weinstein_screener/ict.py` con funciones puras encadenadas — cada concepto ICT es una función independiente y testeable — más dos orquestadores (`find_entry_1_signal`, `find_entry_3_signal`) que las componen en un resultado único (`EntrySignal`). Todas las funciones trabajan sobre un DataFrame diario OHLCV (el mismo formato que produce `weinstein_screener.data`) usando posiciones enteras, igual que el Plan 2. **Este plan no integra automáticamente el resultado semanal del Plan 2 con un DataFrame diario real** (esa integración de fechas se deja para un plan posterior) — cada función recibe `sc_low`/`ar_high` y una posición de inicio de búsqueda ya calculados por quien la llame.

**Tech Stack:** Python 3.9+, pandas, numpy (ya en requirements.txt — no se añade ninguna dependencia nueva). Reutiliza `average_true_range` de `weinstein_screener.indicators` (Plan 1) para el filtro de tamaño del FVG.

## Global Constraints

- Python 3.9+, entorno virtual local en `.venv/` (ya existente).
- Dependencias pinneadas en `requirements.txt` con cota superior — no se añade ninguna dependencia nueva en este plan.
- Todos los umbrales/ventanas son argumentos de función con valor por defecto, nunca constantes hardcodeadas — marcados como "a validar en backtest".
- Ninguna función de este plan hace I/O — todas son funciones puras sobre un DataFrame ya cargado en memoria.
- Todas las funciones de búsqueda usan **solo datos hasta el límite explícito que reciben** (sin look-ahead) — lección aprendida en la revisión final del Plan 2: toda función que acote una búsqueda debe aceptar ese límite como parámetro y respetarlo, no inferirlo de `len(df)`.

## Alcance de este plan (3 de 6)

Cubre únicamente la detección de los disparadores ICT sobre datos diarios ya cargados:
- Order Block (Tasks 1, reutilizado en Entradas 1 y 3).
- Fair Value Gap (Task 2, reutilizado en Entradas 1 y 3).
- Cambio de estructura / reingreso al rango tras el Spring (Task 3 — dispara la Entrada 1).
- Retest de la zona alta del rango con volumen descendente o vela no-supply (Task 4 — dispara la Entrada 3).
- Orquestadores `find_entry_1_signal` y `find_entry_3_signal` (Tasks 5 y 6) que componen todo lo anterior en un resultado con precio de entrada y stop-loss.

**Fuera de alcance** (planes siguientes): la Entrada 2 (no necesita ICT, solo la confirmación semanal ya detectada en el Plan 2 — se implementará junto a la proyección PO3 en el Plan 4), la integración de fechas entre el DataFrame semanal del Plan 2 y el diario de este plan, el importador de la Etapa 1, y la app Streamlit.

## Parámetros de este plan y sus valores por defecto (todos "a validar en backtest")

| Parámetro | Valor por defecto | Qué controla |
|---|---|---|
| `lookback` (Order Block) | 10 velas | Ventana hacia atrás para buscar la última vela bajista antes del impulso |
| `body_multiplier` (FVG) | 1.5 | El cuerpo de la vela 2 debe superar 1.5x el cuerpo medio |
| `body_lookback` (FVG) | 20 velas | Ventana para el cuerpo medio de referencia |
| `gap_range_fraction` (FVG) | 0.2 | El hueco debe superar el 20% del rango de la vela 2 (además de superar el ATR) |
| `window` (MSS/retest) | 5 días | Ventana de búsqueda en cada etapa (ancla→reingreso, ruptura→retest) antes de caducar |
| `retest_tolerance` (MSS) | 0.02 (±2%) | Cercanía a `sc_low` para marcar un reingreso como de "mayor confianza" |
| `tolerance` (Entrada 3) | 0.05 (±5%) | Banda alrededor de `ar_high` que cuenta como retest |
| `volume_decline_fraction` | 0.8 (80%) | Fracción de velas consecutivas con volumen decreciente para confirmar el retest |
| `no_supply_lookback` | 10 velas | Ventana de rango medio para calificar una vela como "no supply" |
| `sl_buffer_atr` (Entrada 1) | 0.25 | Multiplicador del ATR diario para el buffer del stop-loss bajo el ancla del Spring |

---

### Task 1: Order Block

**Files:**
- Create: `weinstein_screener/ict.py`
- Test: `tests/test_ict.py`

**Interfaces:**
- Consumes: nada (primer módulo, opera sobre cualquier DataFrame diario OHLCV).
- Produces: `find_order_block(df: pd.DataFrame, impulse_end_index: int, lookback: int = 10, min_index: int = 0) -> int | None` — posición de la última vela bajista (`Close < Open`) antes de `impulse_end_index`, buscando hacia atrás dentro de `lookback` velas sin cruzar `min_index`, o `None` si no hay ninguna. `min_index` existe para que quien orqueste (Tasks 5 y 6) pueda acotar el Order Block a la propia estructura del disparador, evitando que `entry_price` termine por debajo de `stop_loss`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_ict.py`:

```python
import pandas as pd
import pytest

from weinstein_screener.ict import find_order_block


def _daily_df(rows):
    dates = pd.date_range("2020-01-06", periods=len(rows), freq="D")
    return pd.DataFrame(rows, index=dates)


def test_find_order_block_locates_the_last_bearish_candle():
    rows = [
        {"Open": 105, "High": 107, "Low": 103, "Close": 104, "Volume": 500_000},
        {"Open": 102, "High": 103, "Low": 97, "Close": 98, "Volume": 900_000},
        {"Open": 98, "High": 99, "Low": 96, "Close": 97, "Volume": 400_000},  # OB, índice 2
        {"Open": 97, "High": 106, "Low": 96.5, "Close": 105, "Volume": 800_000},
    ]
    df = _daily_df(rows)

    result = find_order_block(df, impulse_end_index=3, lookback=10)

    assert result == 2


def test_find_order_block_returns_none_without_a_bearish_candle_in_range():
    rows = [
        {"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 500_000},
        {"Open": 101, "High": 103, "Low": 100, "Close": 102, "Volume": 500_000},
        {"Open": 102, "High": 104, "Low": 101, "Close": 103, "Volume": 500_000},
    ]
    df = _daily_df(rows)

    result = find_order_block(df, impulse_end_index=3, lookback=10)

    assert result is None


def test_find_order_block_does_not_cross_min_index():
    # La primera vela es bajista pero cae antes de min_index=1 -- no debe
    # seleccionarse. Sin este límite, el Order Block podría quedar fuera
    # de la propia estructura del disparador (ver Tasks 5 y 6).
    rows = [
        {"Open": 100, "High": 102, "Low": 99, "Close": 98, "Volume": 500_000},
        {"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 500_000},
        {"Open": 101, "High": 103, "Low": 100, "Close": 102, "Volume": 500_000},
        {"Open": 102, "High": 104, "Low": 101, "Close": 103, "Volume": 500_000},
    ]
    df = _daily_df(rows)

    result = find_order_block(df, impulse_end_index=4, lookback=10, min_index=1)

    assert result is None
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
source .venv/bin/activate
pytest tests/test_ict.py -v
```

Esperado: FAIL — `ModuleNotFoundError: No module named 'weinstein_screener.ict'`.

- [ ] **Step 3: Implementar `find_order_block`**

Crear `weinstein_screener/ict.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def find_order_block(
    df: pd.DataFrame, impulse_end_index: int, lookback: int = 10, min_index: int = 0
) -> int | None:
    """Última vela bajista (Close < Open) antes de `impulse_end_index`, buscando
    hacia atrás dentro de `lookback` velas, sin cruzar `min_index`. Devuelve
    None si no hay ninguna.

    `min_index` evita que el Order Block se seleccione fuera de la propia
    estructura que originó el disparador (por ejemplo, antes del ancla del
    Spring o antes del propio retest) — sin este límite, `entry_price`
    podría terminar por debajo de `stop_loss` si la vela bajista más
    cercana está más allá del tramo relevante.
    """
    start = max(min_index, impulse_end_index - lookback)
    for i in range(impulse_end_index - 1, start - 1, -1):
        if df["Close"].iloc[i] < df["Open"].iloc[i]:
            return i
    return None
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_ict.py -v
```

Esperado: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/ict.py tests/test_ict.py
git commit -m "feat: add Order Block detection"
```

---

### Task 2: Fair Value Gap

**Files:**
- Modify: `weinstein_screener/ict.py`
- Test: `tests/test_ict.py`

**Interfaces:**
- Consumes: una serie de ATR diario ya calculada (`average_true_range` del Plan 1, `weinstein_screener.indicators` — este task no la importa, la recibe como parámetro `atr: pd.Series`).
- Produces: `find_fair_value_gap(df: pd.DataFrame, start_index: int, end_index: int, atr: pd.Series, body_multiplier: float = 1.5, body_lookback: int = 20, gap_range_fraction: float = 0.2) -> int | None` — posición de la vela central (vela 2) del primer FVG alcista válido dentro de `[start_index, end_index]`, o `None`.

**Criterios del FVG (acordados en la conversación de diseño)**:
1. El cuerpo de la vela 2 debe superar `body_multiplier` veces el cuerpo medio de las `body_lookback` velas previas (desproporción visual).
2. Hueco real sin solape: `Low(vela3) > High(vela1)`, estrictamente.
3. El hueco debe superar **ambas** condiciones a la vez: `gap >= max(gap_range_fraction × rango(vela2), ATR)`.

- [ ] **Step 1: Añadir los tests que fallan**

Añadir a `tests/test_ict.py`:

```python
from weinstein_screener.ict import find_fair_value_gap


def test_find_fair_value_gap_locates_a_valid_gap():
    calm = [{"Open": 100, "High": 101, "Low": 99, "Close": 100.3, "Volume": 400_000} for _ in range(25)]
    rows = calm + [
        {"Open": 100, "High": 101, "Low": 99.5, "Close": 100.5, "Volume": 400_000},   # vela1, índice 25
        {"Open": 101, "High": 108, "Low": 100.8, "Close": 107.5, "Volume": 900_000},  # vela2, índice 26
        {"Open": 107, "High": 109, "Low": 105, "Close": 108, "Volume": 500_000},      # vela3, índice 27
    ]
    df = _daily_df(rows)
    atr = pd.Series([1.5] * len(df), index=df.index)

    result = find_fair_value_gap(df, start_index=0, end_index=len(df) - 1, atr=atr)

    assert result == 26


def test_find_fair_value_gap_returns_none_when_wicks_overlap():
    calm = [{"Open": 100, "High": 101, "Low": 99, "Close": 100.3, "Volume": 400_000} for _ in range(25)]
    rows = calm + [
        {"Open": 100, "High": 101, "Low": 99.5, "Close": 100.5, "Volume": 400_000},
        {"Open": 101, "High": 108, "Low": 100.8, "Close": 107.5, "Volume": 900_000},
        {"Open": 107, "High": 109, "Low": 100.5, "Close": 108, "Volume": 500_000},  # vela3: Low solapa vela1 High (101)
    ]
    df = _daily_df(rows)
    atr = pd.Series([1.5] * len(df), index=df.index)

    result = find_fair_value_gap(df, start_index=0, end_index=len(df) - 1, atr=atr)

    assert result is None
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_ict.py -v -k fair_value_gap
```

Esperado: FAIL — `ImportError: cannot import name 'find_fair_value_gap'`.

- [ ] **Step 3: Implementar `find_fair_value_gap`**

Añadir a `weinstein_screener/ict.py`:

```python
def find_fair_value_gap(
    df: pd.DataFrame,
    start_index: int,
    end_index: int,
    atr: pd.Series,
    body_multiplier: float = 1.5,
    body_lookback: int = 20,
    gap_range_fraction: float = 0.2,
) -> int | None:
    """Posición de la vela central (vela 2) del primer FVG alcista válido
    dentro de `[start_index, end_index]`, o None.
    """
    body = (df["Close"] - df["Open"]).abs()
    avg_body = body.shift(1).rolling(body_lookback).mean()

    for i in range(start_index + 1, end_index):
        c1_high = df["High"].iloc[i - 1]
        c3_low = df["Low"].iloc[i + 1]
        gap = c3_low - c1_high
        if gap <= 0:
            continue

        candle2_body = body.iloc[i]
        if pd.isna(avg_body.iloc[i]) or candle2_body < body_multiplier * avg_body.iloc[i]:
            continue

        candle2_range = df["High"].iloc[i] - df["Low"].iloc[i]
        min_gap = max(gap_range_fraction * candle2_range, atr.iloc[i])
        if gap < min_gap:
            continue

        return i

    return None
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_ict.py -v
```

Esperado: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/ict.py tests/test_ict.py
git commit -m "feat: add Fair Value Gap detection"
```

---

### Task 3: Cambio de estructura (reingreso al rango) — disparador de la Entrada 1

**Files:**
- Modify: `weinstein_screener/ict.py`
- Test: `tests/test_ict.py`

**Interfaces:**
- Consumes: `sc_low` (Plan 2, calculado a partir del `WyckoffStructure` semanal).
- Produces:
  - `SpringReentry` (dataclass): `anchor_index: int`, `reentry_index: int`, `high_confidence: bool`.
  - `find_spring_reentry_mss(df: pd.DataFrame, sc_low: float, search_start: int, window: int = 5, retest_tolerance: float = 0.02) -> SpringReentry | None`.

**Definición (acordada en la conversación de diseño)**: el "cambio de estructura" de la Entrada 1 no es un MSS clásico (romper un máximo local), sino un **reingreso al rango**:
1. **Ancla**: primera vela diaria, dentro de `window` días desde `search_start`, cuyo mínimo rompe `sc_low`.
2. **Reingreso/confirmación**: primera vela diaria posterior (dentro de otros `window` días desde el ancla) que cierra de vuelta por encima de `sc_low`.
3. **`high_confidence`**: `True` si, dentro de `window` días DESPUÉS del reingreso, el precio vuelve a acercarse a `sc_low` (`Low <= sc_low × (1 + retest_tolerance)`) sin necesariamente rompirlo — un retest genuino tras la reclamación, no solo el tramo bajista previo al reingreso. Es un flag informativo, no bloqueante.

- [ ] **Step 1: Añadir los tests que fallan**

Añadir a `tests/test_ict.py`:

```python
from weinstein_screener.ict import find_spring_reentry_mss


def test_find_spring_reentry_mss_locates_anchor_and_reentry():
    rows = [{"Open": 105, "High": 107, "Low": 103, "Close": 104, "Volume": 500_000} for _ in range(4)]
    rows.append({"Open": 102, "High": 103, "Low": 97, "Close": 98, "Volume": 900_000})    # ancla, índice 4
    rows.append({"Open": 98, "High": 99, "Low": 96, "Close": 97, "Volume": 400_000})      # índice 5
    rows.append({"Open": 97, "High": 106, "Low": 96.5, "Close": 105, "Volume": 800_000})  # reingreso, índice 6
    rows.append({"Open": 106, "High": 110, "Low": 105, "Close": 109, "Volume": 600_000})
    rows.append({"Open": 109, "High": 112, "Low": 108, "Close": 111, "Volume": 500_000})
    df = _daily_df(rows)

    result = find_spring_reentry_mss(df, sc_low=100, search_start=0, window=5)

    assert result.anchor_index == 4
    assert result.reentry_index == 6
    assert result.high_confidence is False


def test_find_spring_reentry_mss_flags_high_confidence_on_a_post_reentry_retest():
    rows = [{"Open": 105, "High": 107, "Low": 103, "Close": 104, "Volume": 500_000} for _ in range(4)]
    rows.append({"Open": 102, "High": 103, "Low": 97, "Close": 98, "Volume": 900_000})
    rows.append({"Open": 98, "High": 99, "Low": 96, "Close": 97, "Volume": 400_000})
    rows.append({"Open": 97, "High": 106, "Low": 96.5, "Close": 105, "Volume": 800_000})  # reingreso, índice 6
    rows.append({"Open": 106, "High": 107, "Low": 101, "Close": 102, "Volume": 400_000})  # retest tras reingreso, índice 7
    rows.append({"Open": 102, "High": 108, "Low": 101.5, "Close": 107, "Volume": 700_000})
    df = _daily_df(rows)

    result = find_spring_reentry_mss(df, sc_low=100, search_start=0, window=5)

    assert result.reentry_index == 6
    assert result.high_confidence is True


def test_find_spring_reentry_mss_returns_none_without_an_anchor():
    rows = [{"Open": 105, "High": 107, "Low": 103, "Close": 104, "Volume": 500_000} for _ in range(10)]
    df = _daily_df(rows)

    result = find_spring_reentry_mss(df, sc_low=100, search_start=0, window=5)

    assert result is None
```

(añadir `pytest` sigue ya importado; `SpringReentry` no hace falta importarlo en el test porque no se instancia directamente, solo se leen sus atributos)

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_ict.py -v -k spring_reentry
```

Esperado: FAIL — `ImportError: cannot import name 'find_spring_reentry_mss'`.

- [ ] **Step 3: Implementar `SpringReentry` y `find_spring_reentry_mss`**

Añadir a `weinstein_screener/ict.py`:

```python
@dataclass
class SpringReentry:
    anchor_index: int
    reentry_index: int
    high_confidence: bool


def find_spring_reentry_mss(
    df: pd.DataFrame,
    sc_low: float,
    search_start: int,
    window: int = 5,
    retest_tolerance: float = 0.02,
) -> SpringReentry | None:
    """Ancla (ruptura de sc_low) + reingreso (cierre de vuelta sobre sc_low),
    ambos dentro de una ventana de `window` días cada uno desde `search_start`.
    `high_confidence` marca si, tras el reingreso, el precio retestea sc_low
    de nuevo dentro de otra ventana de `window` días.
    """
    anchor_index = None
    for i in range(search_start, min(len(df), search_start + window)):
        if df["Low"].iloc[i] < sc_low:
            anchor_index = i
            break
    if anchor_index is None:
        return None

    reentry_index = None
    for i in range(anchor_index + 1, min(len(df), anchor_index + 1 + window)):
        if df["Close"].iloc[i] > sc_low:
            reentry_index = i
            break
    if reentry_index is None:
        return None

    retest_end = min(len(df), reentry_index + 1 + window)
    high_confidence = any(
        df["Low"].iloc[j] <= sc_low * (1 + retest_tolerance) for j in range(reentry_index + 1, retest_end)
    )

    return SpringReentry(anchor_index=anchor_index, reentry_index=reentry_index, high_confidence=high_confidence)
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_ict.py -v
```

Esperado: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/ict.py tests/test_ict.py
git commit -m "feat: add spring reentry (structure shift) detection for Entrada 1"
```

---

### Task 4: Retest con volumen descendente o vela "no supply" — disparador de la Entrada 3

**Files:**
- Modify: `weinstein_screener/ict.py`
- Test: `tests/test_ict.py`

**Interfaces:**
- Consumes: `ar_high` (Plan 2).
- Produces:
  - `RetestResult` (dataclass): `retest_index: int`, `volume_declining: bool`, `no_supply: bool`.
  - `find_retest(df: pd.DataFrame, ar_high: float, breakout_index: int, window: int = 5, tolerance: float = 0.05, volume_decline_fraction: float = 0.8, no_supply_lookback: int = 10) -> RetestResult | None`.

**Definición (acordada)**:
1. **Retest**: una vela, dentro de `window` días tras `breakout_index`, cuyo rango toca la banda `[ar_high × (1-tolerance), ar_high × (1+tolerance)]`.
2. **Volumen descendente**: al menos `volume_decline_fraction` (80%) de las velas consecutivas desde `breakout_index+1` hasta la vela del retest tienen menor volumen que la vela inmediatamente anterior.
3. **Vela "no supply"** (alternativa a 2, no ambas obligatorias): la vela del retest es bajista, de rango menor que la media de las `no_supply_lookback` velas previas, cierra en la mitad superior o más de su propio rango (`≥0.5`, mismo criterio que el Spring del Plan 2), y su volumen es menor que la media de las 2 velas previas.
4. Se dispara si se cumple **al menos una** de (2) o (3).

- [ ] **Step 1: Añadir los tests que fallan**

Añadir a `tests/test_ict.py`:

```python
from weinstein_screener.ict import find_retest


def test_find_retest_locates_the_retest_with_declining_volume():
    rows = [
        {"Open": 118, "High": 122, "Low": 117, "Close": 121, "Volume": 900_000},   # ruptura, índice 0
        {"Open": 128, "High": 130, "Low": 127, "Close": 129, "Volume": 700_000},   # aún no toca la banda, índice 1
        {"Open": 127, "High": 127, "Low": 118, "Close": 119, "Volume": 500_000},   # retest, índice 2
        {"Open": 119, "High": 120, "Low": 116, "Close": 117, "Volume": 300_000},
        {"Open": 117, "High": 118, "Low": 115, "Close": 116, "Volume": 200_000},
    ]
    df = _daily_df(rows)

    result = find_retest(df, ar_high=120, breakout_index=0, window=5, tolerance=0.05)

    assert result.retest_index == 2
    assert result.volume_declining is True


def test_find_retest_returns_none_without_touching_the_band():
    rows = [{"Open": 130, "High": 132, "Low": 129, "Close": 131, "Volume": 500_000} for _ in range(6)]
    df = _daily_df(rows)

    result = find_retest(df, ar_high=120, breakout_index=0, window=5, tolerance=0.05)

    assert result is None


def test_find_retest_triggers_on_the_first_candidate_day():
    # La comparación de volumen descendente incluye la propia vela de
    # ruptura como primer término -- si no, un retest en el primer día
    # tras la ruptura nunca tendría "vela anterior" con la que compararse.
    rows = [
        {"Open": 118, "High": 122, "Low": 117, "Close": 121, "Volume": 900_000},  # ruptura, índice 0
        {"Open": 121, "High": 122, "Low": 118, "Close": 119, "Volume": 500_000},  # retest el primer día, índice 1
    ]
    df = _daily_df(rows)

    result = find_retest(df, ar_high=120, breakout_index=0, window=5, tolerance=0.05)

    assert result is not None
    assert result.retest_index == 1
    assert result.volume_declining is True


def test_find_retest_triggers_via_no_supply_candle():
    rows = [
        {"Open": 118, "High": 122, "Low": 110, "Close": 121, "Volume": 500_000},     # ruptura, índice 0 (rango 12)
        {"Open": 128, "High": 130, "Low": 127, "Close": 129, "Volume": 600_000},     # no toca la banda, índice 1
        {"Open": 119.3, "High": 119.5, "Low": 117, "Close": 119, "Volume": 200_000}, # vela no-supply, índice 2
    ]
    df = _daily_df(rows)

    result = find_retest(df, ar_high=120, breakout_index=0, window=5, tolerance=0.05)

    assert result is not None
    assert result.retest_index == 2
    assert result.no_supply is True
    assert result.volume_declining is False
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_ict.py -v -k find_retest
```

Esperado: FAIL — `ImportError: cannot import name 'find_retest'`.

- [ ] **Step 3: Implementar `RetestResult`, `_is_no_supply_candle` y `find_retest`**

Añadir a `weinstein_screener/ict.py`:

```python
@dataclass
class RetestResult:
    retest_index: int
    volume_declining: bool
    no_supply: bool


def _is_no_supply_candle(df: pd.DataFrame, index: int, range_lookback: int = 10) -> bool:
    is_bearish = df["Close"].iloc[index] < df["Open"].iloc[index]
    low = df["Low"].iloc[index]
    high = df["High"].iloc[index]
    candle_range = high - low

    prior_ranges = (df["High"] - df["Low"]).iloc[max(0, index - range_lookback) : index]
    avg_range = prior_ranges.mean()
    small_range = not pd.isna(avg_range) and candle_range < avg_range

    close_position = (df["Close"].iloc[index] - low) / candle_range if candle_range > 0 else 0
    upper_half_close = close_position >= 0.5

    if index >= 2:
        avg_volume_prev2 = df["Volume"].iloc[index - 2 : index].mean()
        low_volume = df["Volume"].iloc[index] < avg_volume_prev2
    else:
        low_volume = False

    return bool(is_bearish and small_range and upper_half_close and low_volume)


def find_retest(
    df: pd.DataFrame,
    ar_high: float,
    breakout_index: int,
    window: int = 5,
    tolerance: float = 0.05,
    volume_decline_fraction: float = 0.8,
    no_supply_lookback: int = 10,
) -> RetestResult | None:
    """Primera vela, dentro de `window` días tras `breakout_index`, que toca
    la banda `±tolerance` alrededor de `ar_high` con volumen descendente o
    una vela "no supply".

    La comparación de volumen descendente incluye la propia vela de ruptura
    (`breakout_index`) como primer término — si no se incluyera, una vela
    de retest que ocurre justo en el primer día tras la ruptura nunca
    tendría una "vela anterior" con la que compararse y el criterio de
    volumen descendente no podría dispararse nunca en ese caso.
    """
    band_low = ar_high * (1 - tolerance)
    band_high = ar_high * (1 + tolerance)
    end = min(len(df), breakout_index + 1 + window)
    candidates = list(range(breakout_index + 1, end))

    for position, i in enumerate(candidates):
        low = df["Low"].iloc[i]
        high = df["High"].iloc[i]
        touches_band = high >= band_low and low <= band_high
        if not touches_band:
            continue

        segment = [breakout_index] + candidates[: position + 1]
        declines = sum(
            1
            for k in range(1, len(segment))
            if df["Volume"].iloc[segment[k]] < df["Volume"].iloc[segment[k - 1]]
        )
        volume_declining = (declines / (len(segment) - 1)) >= volume_decline_fraction

        no_supply = _is_no_supply_candle(df, i, no_supply_lookback)

        if volume_declining or no_supply:
            return RetestResult(retest_index=i, volume_declining=volume_declining, no_supply=no_supply)

    return None
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_ict.py -v
```

Esperado: `12 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/ict.py tests/test_ict.py
git commit -m "feat: add retest detection (declining volume / no-supply) for Entrada 3"
```

---

### Task 5: Orquestador de la Entrada 1

**Files:**
- Modify: `weinstein_screener/ict.py`
- Test: `tests/test_ict.py`

**Interfaces:**
- Consumes: `find_spring_reentry_mss` (Task 3), `find_order_block` (Task 1), `find_fair_value_gap` (Task 2).
- Produces:
  - `EntrySignal` (dataclass): `trigger_index: int`, `order_block_index: int | None`, `fvg_index: int | None`, `entry_price: float | None`, `stop_loss: float | None`, `high_confidence: bool`.
  - `find_entry_1_signal(df_daily: pd.DataFrame, sc_low: float, search_start: int, atr: pd.Series, window: int = 5, ob_lookback: int = 10, sl_buffer_atr: float = 0.25, fvg_body_multiplier: float = 1.5, fvg_body_lookback: int = 20, fvg_gap_range_fraction: float = 0.2) -> EntrySignal | None`.

**Composición**: el disparador es `find_spring_reentry_mss`. Si se encuentra, se busca el Order Block (última vela bajista antes del reingreso) — si no hay Order Block, no hay señal (`None`). El FVG se busca dentro del mismo tramo (ancla→reingreso) como refuerzo opcional, no bloqueante. `entry_price` = máximo de la vela del Order Block (límite superior del bloque). `stop_loss` = mínimo de la vela ancla del Spring, menos `sl_buffer_atr × ATR` de ese día.

- [ ] **Step 1: Añadir los tests que fallan**

Añadir a `tests/test_ict.py`:

```python
from weinstein_screener.ict import find_entry_1_signal


def test_find_entry_1_signal_composes_mss_order_block_and_stop_loss():
    rows = [{"Open": 105, "High": 107, "Low": 103, "Close": 104, "Volume": 500_000} for _ in range(4)]
    rows.append({"Open": 102, "High": 103, "Low": 97, "Close": 98, "Volume": 900_000})    # ancla, índice 4
    rows.append({"Open": 98, "High": 99, "Low": 96, "Close": 97, "Volume": 400_000})      # OB, índice 5
    rows.append({"Open": 97, "High": 106, "Low": 96.5, "Close": 105, "Volume": 800_000})  # reingreso, índice 6
    df = _daily_df(rows)
    atr = pd.Series([1.0] * len(df), index=df.index)

    result = find_entry_1_signal(df, sc_low=100, search_start=0, atr=atr, window=5)

    assert result is not None
    assert result.trigger_index == 6
    assert result.order_block_index == 5
    assert result.entry_price == pytest.approx(99)
    assert result.stop_loss == pytest.approx(96.75)
    assert result.high_confidence is False


def test_find_entry_1_signal_returns_none_without_a_reentry():
    rows = [{"Open": 105, "High": 107, "Low": 103, "Close": 104, "Volume": 500_000} for _ in range(10)]
    df = _daily_df(rows)
    atr = pd.Series([1.0] * len(df), index=df.index)

    result = find_entry_1_signal(df, sc_low=100, search_start=0, atr=atr, window=5)

    assert result is None
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_ict.py -v -k find_entry_1_signal
```

Esperado: FAIL — `ImportError: cannot import name 'find_entry_1_signal'`.

- [ ] **Step 3: Implementar `EntrySignal` y `find_entry_1_signal`**

Añadir a `weinstein_screener/ict.py`:

```python
@dataclass
class EntrySignal:
    trigger_index: int
    order_block_index: int | None
    fvg_index: int | None
    entry_price: float | None
    stop_loss: float | None
    high_confidence: bool


def find_entry_1_signal(
    df_daily: pd.DataFrame,
    sc_low: float,
    search_start: int,
    atr: pd.Series,
    window: int = 5,
    ob_lookback: int = 10,
    sl_buffer_atr: float = 0.25,
    fvg_body_multiplier: float = 1.5,
    fvg_body_lookback: int = 20,
    fvg_gap_range_fraction: float = 0.2,
) -> EntrySignal | None:
    """Compone el disparador de la Entrada 1 (Spring): reingreso al rango,
    Order Block, y FVG opcional como refuerzo. None si no hay reingreso, no
    hay Order Block, o si el precio de entrada resultante no queda por
    encima del stop-loss (el Order Block se acota con `min_index` al ancla
    del Spring para que esto no pueda ocurrir en el caso normal, pero la
    comprobación final es la garantía explícita).
    """
    reentry = find_spring_reentry_mss(df_daily, sc_low, search_start, window)
    if reentry is None:
        return None

    order_block_index = find_order_block(
        df_daily, reentry.reentry_index, ob_lookback, min_index=reentry.anchor_index
    )
    if order_block_index is None:
        return None

    fvg_index = None
    if reentry.reentry_index - reentry.anchor_index >= 2:
        fvg_index = find_fair_value_gap(
            df_daily,
            reentry.anchor_index,
            reentry.reentry_index,
            atr,
            fvg_body_multiplier,
            fvg_body_lookback,
            fvg_gap_range_fraction,
        )

    entry_price = df_daily["High"].iloc[order_block_index]
    stop_loss = df_daily["Low"].iloc[reentry.anchor_index] - sl_buffer_atr * atr.iloc[reentry.anchor_index]

    if entry_price <= stop_loss:
        return None

    return EntrySignal(
        trigger_index=reentry.reentry_index,
        order_block_index=order_block_index,
        fvg_index=fvg_index,
        entry_price=entry_price,
        stop_loss=stop_loss,
        high_confidence=reentry.high_confidence,
    )
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_ict.py -v
```

Esperado: `14 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/ict.py tests/test_ict.py
git commit -m "feat: add find_entry_1_signal orchestrator"
```

---

### Task 6: Orquestador de la Entrada 3

**Files:**
- Modify: `weinstein_screener/ict.py`
- Test: `tests/test_ict.py`

**Interfaces:**
- Consumes: `find_retest` (Task 4), `find_order_block` (Task 1), `find_fair_value_gap` (Task 2), `EntrySignal` (Task 5).
- Produces: `find_entry_3_signal(df_daily: pd.DataFrame, ar_high: float, breakout_index: int, atr: pd.Series, window: int = 5, tolerance: float = 0.05, ob_lookback: int = 10, volume_decline_fraction: float = 0.8, no_supply_lookback: int = 10, fvg_body_multiplier: float = 1.5, fvg_body_lookback: int = 20, fvg_gap_range_fraction: float = 0.2) -> EntrySignal | None`.

**Composición**: el disparador es `find_retest`. El Order Block se busca inmediatamente después de la vela del retest (la reacción alcista que sigue al retest define el impulso). El FVG se busca en el mismo tramo, como refuerzo. `entry_price` = máximo de la vela del Order Block. `stop_loss` = mínimo de la vela del retest (estructural, sin buffer de ATR — a diferencia de la Entrada 1, aquí el propio retest ya es la zona de invalidación). `high_confidence` en el `EntrySignal` resultante se reutiliza para indicar si el retest fue por vela "no supply" (`no_supply=True` del `RetestResult`) además de o en vez de volumen descendente.

- [ ] **Step 1: Añadir los tests que fallan**

Añadir a `tests/test_ict.py`:

```python
from weinstein_screener.ict import find_entry_3_signal


def test_find_entry_3_signal_composes_retest_order_block_and_stop_loss():
    rows = [
        {"Open": 118, "High": 122, "Low": 117, "Close": 121, "Volume": 900_000},    # ruptura, índice 0
        {"Open": 128, "High": 130, "Low": 127, "Close": 129, "Volume": 700_000},    # aún no toca la banda, índice 1
        {"Open": 122, "High": 122.5, "Low": 118, "Close": 119, "Volume": 500_000},   # retest, índice 2 (bajista)
        {"Open": 119, "High": 125, "Low": 118.5, "Close": 124, "Volume": 600_000},   # impulso alcista
    ]
    df = _daily_df(rows)
    atr = pd.Series([1.0] * len(df), index=df.index)

    result = find_entry_3_signal(df, ar_high=120, breakout_index=0, atr=atr, window=5, tolerance=0.05)

    assert result is not None
    assert result.trigger_index == 2
    assert result.order_block_index == 2
    assert result.entry_price == pytest.approx(122.5)
    assert result.stop_loss == pytest.approx(118)


def test_find_entry_3_signal_returns_none_without_a_retest():
    rows = [{"Open": 130, "High": 132, "Low": 129, "Close": 131, "Volume": 500_000} for _ in range(6)]
    df = _daily_df(rows)
    atr = pd.Series([1.0] * len(df), index=df.index)

    result = find_entry_3_signal(df, ar_high=120, breakout_index=0, atr=atr, window=5, tolerance=0.05)

    assert result is None


def test_find_entry_3_signal_can_find_a_reinforcing_fvg_after_the_retest():
    # El FVG se busca en los días SIGUIENTES al retest (el impulso de
    # reacción), no en el tramo hacia el Order Block -- ver la nota en la
    # implementación. `fvg_body_lookback=3` porque con solo 6 filas no hay
    # suficiente historial para el valor por defecto (20).
    rows = [
        {"Open": 118, "High": 122, "Low": 117, "Close": 121, "Volume": 900_000},     # ruptura, índice 0
        {"Open": 128, "High": 130, "Low": 127, "Close": 129, "Volume": 700_000},     # no toca la banda, índice 1
        {"Open": 122, "High": 122.5, "Low": 118, "Close": 119, "Volume": 500_000},   # retest, índice 2
        {"Open": 119, "High": 119.5, "Low": 118.5, "Close": 119, "Volume": 300_000}, # vela1 del FVG, índice 3
        {"Open": 119, "High": 135, "Low": 118.8, "Close": 133, "Volume": 900_000},   # vela2 impulso, índice 4
        {"Open": 133, "High": 137, "Low": 131, "Close": 136, "Volume": 500_000},     # vela3, índice 5
    ]
    df = _daily_df(rows)
    atr = pd.Series([1.0] * len(df), index=df.index)

    result = find_entry_3_signal(
        df, ar_high=120, breakout_index=0, atr=atr, window=5, tolerance=0.05, fvg_body_lookback=3
    )

    assert result is not None
    assert result.fvg_index == 4
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_ict.py -v -k find_entry_3_signal
```

Esperado: FAIL — `ImportError: cannot import name 'find_entry_3_signal'`.

- [ ] **Step 3: Implementar `find_entry_3_signal`**

Añadir a `weinstein_screener/ict.py`:

```python
def find_entry_3_signal(
    df_daily: pd.DataFrame,
    ar_high: float,
    breakout_index: int,
    atr: pd.Series,
    window: int = 5,
    tolerance: float = 0.05,
    ob_lookback: int = 10,
    volume_decline_fraction: float = 0.8,
    no_supply_lookback: int = 10,
    fvg_body_multiplier: float = 1.5,
    fvg_body_lookback: int = 20,
    fvg_gap_range_fraction: float = 0.2,
) -> EntrySignal | None:
    """Compone el disparador de la Entrada 3 (retest): retest de `ar_high`
    con volumen descendente o vela no-supply, Order Block, y FVG opcional
    como refuerzo. None si no hay retest, no hay Order Block, o si el
    precio de entrada resultante no queda por encima del stop-loss (ver
    nota equivalente en `find_entry_1_signal`).

    El FVG se busca en los días SIGUIENTES al retest (el posible impulso de
    reacción), no en el tramo hacia el Order Block — el Order Block nunca
    puede quedar después del propio retest, así que buscar el FVG hacia
    "adelante" del Order Block dejaría el rango de búsqueda vacío.
    """
    retest = find_retest(
        df_daily, ar_high, breakout_index, window, tolerance, volume_decline_fraction, no_supply_lookback
    )
    if retest is None:
        return None

    order_block_index = find_order_block(
        df_daily, retest.retest_index + 1, ob_lookback, min_index=retest.retest_index
    )
    if order_block_index is None:
        return None

    fvg_index = None
    fvg_start = retest.retest_index
    fvg_end = min(len(df_daily) - 1, retest.retest_index + window)
    if fvg_end - fvg_start >= 2:
        fvg_index = find_fair_value_gap(
            df_daily, fvg_start, fvg_end, atr, fvg_body_multiplier, fvg_body_lookback, fvg_gap_range_fraction
        )

    entry_price = df_daily["High"].iloc[order_block_index]
    stop_loss = df_daily["Low"].iloc[retest.retest_index]

    if entry_price <= stop_loss:
        return None

    return EntrySignal(
        trigger_index=retest.retest_index,
        order_block_index=order_block_index,
        fvg_index=fvg_index,
        entry_price=entry_price,
        stop_loss=stop_loss,
        high_confidence=retest.no_supply,
    )
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_ict.py -v
```

Esperado: `17 passed`.

- [ ] **Step 5: Ejecutar toda la suite de tests del proyecto**

```bash
pytest -v
```

Esperado: `58 passed` (41 de los Planes 1-2 + 17 de este plan).

- [ ] **Step 6: Commit**

```bash
git add weinstein_screener/ict.py tests/test_ict.py
git commit -m "feat: add find_entry_3_signal orchestrator"
```

---

## Siguiente paso

Con este plan completado, el sistema puede tomar `sc_low`/`ar_high` (del Plan 2) y un DataFrame diario, y determinar si hay una señal de Entrada 1 o Entrada 3 lista, con precio de entrada y stop-loss concretos. El **Plan 4** cubrirá la Entrada 2 (sin ICT, solo la confirmación semanal ya detectada), la gestión de las 3 entradas en conjunto (mover SL a breakeven, redimensionar si el Spring falla), y la proyección PO3 para la salida.
