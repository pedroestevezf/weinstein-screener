# Plan 4 de 6 — Entrada 2, gestión conjunta y salida PO3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completar el ciclo de las 3 entradas (Entrada 2 — ruptura semanal, sin ICT), la gestión conjunta (mover SL a breakeven, redimensionar si el Spring falla), y la salida (techo de referencia PO3 en timeframe superior + invalidación de la MA30w).

**Architecture:** Un nuevo módulo `weinstein_screener/management.py` con funciones puras: `find_entry_2_signal` (reutiliza `WyckoffStructure.distribution_index` del Plan 2 y `average_true_range` del Plan 1), `evaluate_position_management` (lógica de gestión sin estado, recibe el estado actual y devuelve una alerta), `project_po3_ceiling` (reutiliza `detect_wyckoff_structure` del Plan 2 pero aplicado a datos de timeframe superior, con parámetros recalibrados), y `evaluate_exit_signal` (compone el techo PO3 con `close_above_ma` del Plan 1).

**Tech Stack:** Python 3.9+, pandas (ya en requirements.txt). Reutiliza `weinstein_screener.wyckoff.detect_wyckoff_structure`/`WyckoffStructure` (Plan 2) y `weinstein_screener.indicators.average_true_range` (Plan 1) — primera vez que un plan importa directamente de otro módulo del proyecto en vez de recibir todo por parámetro, porque aquí sí tiene sentido: no hay conflicto de fechas/timeframes que resolver (a diferencia del Plan 3, que deliberadamente no se conectó al Plan 2 por la desalineación semanal/diaria).

## Global Constraints

- Python 3.9+, entorno virtual local en `.venv/` (ya existente).
- Dependencias pinneadas en `requirements.txt` con cota superior — no se añade ninguna dependencia nueva.
- Todos los umbrales/ventanas son argumentos de función con valor por defecto, nunca constantes hardcodeadas.
- Ninguna función de este plan hace I/O — funciones puras sobre DataFrames ya cargados en memoria.
- Todo cálculo de invariantes (ej. `entry_price > stop_loss`) sigue el mismo patrón que los Planes 2 y 3: si no se cumple, la función devuelve `None` en vez de un resultado inválido.

## Alcance de este plan (4 de 6)

Cubre:
- Entrada 2 (ruptura semanal, sin ICT — usa directamente `distribution_index` del Plan 2).
- Gestión conjunta de las 3 entradas: mover SL de la Entrada 1 a breakeven cuando se activa la Entrada 2; redimensionar Entradas 2 y 3 (~43%/57%) si la Entrada 1 salta por su SL.
- Proyección del techo PO3 sobre datos de timeframe superior (mensual por defecto, trimestral si el rango de la Fase B semanal supera el rango mensual típico de 24 meses), reutilizando `detect_wyckoff_structure` con parámetros recalibrados para esa escala, con un máximo móvil de 24 periodos como respaldo si no se encuentra estructura.
- Señal de salida: parcial (25-30%) al tocar el techo PO3, total al perder la MA30w (usa `close_above_ma` del Plan 1).

**Fuera de alcance** (planes siguientes): el importador de la Etapa 1 (TradingView), y la app Streamlit que junta todo lo anterior y genera las alertas de forma visible.

## Parámetros de este plan y sus valores por defecto (todos "a validar en backtest")

| Parámetro | Valor por defecto | Qué controla |
|---|---|---|
| `sl_atr_multiplier` (Entrada 2) | 1.5 | Stop-loss = cierre de la ruptura − 1.5x ATR semanal |
| `base_entry2_pct` / `base_entry3_pct` | 30.0 / 40.0 | Pesos base para el redimensionamiento tras un Spring fallido |
| `fallback_lookback` (PO3) | 24 periodos | Ventana del máximo móvil de respaldo y del "rango mensual típico" |
| `sc_search_window` (PO3, recalibrado) | 26 | Ventana de búsqueda del SC en la escala mensual/trimestral |
| `ar_window` / `st_window` (PO3, recalibrado) | 6 / 6 | Ventanas de AR/ST en la escala mensual/trimestral |
| `range_lookback` / `volume_lookback` / `new_low_lookback` (PO3, recalibrado) | 6 / 6 / 6 | Ventanas de línea base del SC en la escala mensual/trimestral |
| `phase_a_recency_weeks` (PO3, recalibrado) | 24 | Vigencia del ST en la escala mensual/trimestral |
| `partial_take_profit_pct` | 25-30 (informativo, no aplicado como número fijo en el código — ver Task 4) | Porcentaje de la posición a cerrar al tocar el techo PO3 |

---

### Task 1: Entrada 2 (ruptura semanal)

**Files:**
- Create: `weinstein_screener/management.py`
- Test: `tests/test_management.py`

**Interfaces:**
- Consumes: `distribution_index` (de `WyckoffStructure`, Plan 2), una serie de ATR semanal ya calculada (`average_true_range` del Plan 1, recibida como parámetro, no importada dentro de esta función).
- Produces:
  - `Entry2Signal` (dataclass): `trigger_index: int`, `entry_price: float`, `stop_loss: float`.
  - `find_entry_2_signal(df_weekly: pd.DataFrame, distribution_index: int | None, atr_weekly: pd.Series, sl_atr_multiplier: float = 1.5) -> Entry2Signal | None`. Devuelve `None` si `distribution_index` es `None`, o si `entry_price <= stop_loss` (no debería ocurrir con un ATR positivo, pero se mantiene la misma garantía explícita que en el Plan 3).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_management.py`:

```python
import pandas as pd
import pytest

from weinstein_screener.management import find_entry_2_signal


def _weekly_df(rows):
    dates = pd.date_range("2020-01-06", periods=len(rows), freq="W-MON")
    return pd.DataFrame(rows, index=dates)


def test_find_entry_2_signal_composes_price_and_stop_loss():
    rows = [{"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 500_000} for _ in range(7)]
    rows.append({"Open": 118, "High": 125, "Low": 117, "Close": 124, "Volume": 900_000})  # ruptura, índice 7
    rows.append({"Open": 124, "High": 128, "Low": 123, "Close": 126, "Volume": 700_000})
    df = _weekly_df(rows)
    atr = pd.Series([2.0] * len(df), index=df.index)

    result = find_entry_2_signal(df, distribution_index=7, atr_weekly=atr, sl_atr_multiplier=1.5)

    assert result is not None
    assert result.trigger_index == 7
    assert result.entry_price == pytest.approx(124)
    assert result.stop_loss == pytest.approx(121.0)


def test_find_entry_2_signal_returns_none_without_a_distribution():
    rows = [{"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 500_000} for _ in range(5)]
    df = _weekly_df(rows)
    atr = pd.Series([2.0] * len(df), index=df.index)

    result = find_entry_2_signal(df, distribution_index=None, atr_weekly=atr)

    assert result is None
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
source .venv/bin/activate
pytest tests/test_management.py -v
```

Esperado: FAIL — `ModuleNotFoundError: No module named 'weinstein_screener.management'`.

- [ ] **Step 3: Implementar `Entry2Signal` y `find_entry_2_signal`**

Crear `weinstein_screener/management.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from weinstein_screener.wyckoff import WyckoffStructure, detect_wyckoff_structure


@dataclass
class Entry2Signal:
    trigger_index: int
    entry_price: float
    stop_loss: float


def find_entry_2_signal(
    df_weekly: pd.DataFrame,
    distribution_index: int | None,
    atr_weekly: pd.Series,
    sl_atr_multiplier: float = 1.5,
) -> Entry2Signal | None:
    """Compone el disparador de la Entrada 2 (ruptura): cierre de la semana
    de Distribution como precio de entrada, stop-loss basado en ATR
    semanal. None si no hay Distribution o si el precio de entrada no
    queda por encima del stop-loss.
    """
    if distribution_index is None:
        return None

    entry_price = df_weekly["Close"].iloc[distribution_index]
    stop_loss = entry_price - sl_atr_multiplier * atr_weekly.iloc[distribution_index]

    if entry_price <= stop_loss:
        return None

    return Entry2Signal(trigger_index=distribution_index, entry_price=entry_price, stop_loss=stop_loss)
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_management.py -v
```

Esperado: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/management.py tests/test_management.py
git commit -m "feat: add Entrada 2 (breakout) signal"
```

---

### Task 2: Gestión conjunta (breakeven y redimensionamiento)

**Files:**
- Modify: `weinstein_screener/management.py`
- Test: `tests/test_management.py`

**Interfaces:**
- Consumes: nada de otros módulos — recibe el estado actual de las entradas como booleanos.
- Produces:
  - `ManagementAlert` (dataclass): `move_entry1_to_breakeven: bool`, `resize_entry2_pct: float | None`, `resize_entry3_pct: float | None`.
  - `evaluate_position_management(entry1_triggered: bool, entry1_stopped_out: bool, entry2_triggered: bool, base_entry2_pct: float = 30.0, base_entry3_pct: float = 40.0) -> ManagementAlert`.

**Definición (acordada en el diseño original)**:
- `move_entry1_to_breakeven`: `True` solo cuando la Entrada 1 se activó, no ha saltado por su SL, y se activa la Entrada 2.
- Redimensionamiento: solo cuando la Entrada 1 saltó por su SL (`entry1_stopped_out=True`) — se recalculan los pesos de las Entradas 2 y 3 manteniendo su ratio relativo (`base_entry2_pct : base_entry3_pct`) pero sumando el 100% en vez del 70% original. Con los valores por defecto (30/40), esto da ~42.86%/57.14%.

- [ ] **Step 1: Añadir los tests que fallan**

Añadir a `tests/test_management.py`:

```python
from weinstein_screener.management import evaluate_position_management


def test_evaluate_position_management_flags_breakeven_when_entry2_triggers():
    result = evaluate_position_management(entry1_triggered=True, entry1_stopped_out=False, entry2_triggered=True)

    assert result.move_entry1_to_breakeven is True
    assert result.resize_entry2_pct is None
    assert result.resize_entry3_pct is None


def test_evaluate_position_management_resizes_after_a_failed_spring():
    result = evaluate_position_management(entry1_triggered=True, entry1_stopped_out=True, entry2_triggered=False)

    assert result.move_entry1_to_breakeven is False
    assert result.resize_entry2_pct == pytest.approx(42.857, abs=0.01)
    assert result.resize_entry3_pct == pytest.approx(57.143, abs=0.01)
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_management.py -v -k evaluate_position_management
```

Esperado: FAIL — `ImportError: cannot import name 'evaluate_position_management'`.

- [ ] **Step 3: Implementar `ManagementAlert` y `evaluate_position_management`**

Añadir a `weinstein_screener/management.py`:

```python
@dataclass
class ManagementAlert:
    move_entry1_to_breakeven: bool
    resize_entry2_pct: float | None
    resize_entry3_pct: float | None


def evaluate_position_management(
    entry1_triggered: bool,
    entry1_stopped_out: bool,
    entry2_triggered: bool,
    base_entry2_pct: float = 30.0,
    base_entry3_pct: float = 40.0,
) -> ManagementAlert:
    """Alerta de gestión conjunta de las 3 entradas.

    `move_entry1_to_breakeven`: True cuando la Entrada 1 sigue viva y se
    activa la Entrada 2. Redimensionamiento: solo si la Entrada 1 saltó
    por su SL, manteniendo el ratio relativo de las Entradas 2 y 3 pero
    sumando el 100% en vez del 70% original.
    """
    move_to_breakeven = entry1_triggered and not entry1_stopped_out and entry2_triggered

    resize_entry2_pct = None
    resize_entry3_pct = None
    if entry1_stopped_out:
        total = base_entry2_pct + base_entry3_pct
        resize_entry2_pct = base_entry2_pct / total * 100
        resize_entry3_pct = base_entry3_pct / total * 100

    return ManagementAlert(
        move_entry1_to_breakeven=move_to_breakeven,
        resize_entry2_pct=resize_entry2_pct,
        resize_entry3_pct=resize_entry3_pct,
    )
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_management.py -v
```

Esperado: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/management.py tests/test_management.py
git commit -m "feat: add joint position management alerts (breakeven, resize)"
```

---

### Task 3: Proyección del techo PO3

**Files:**
- Modify: `weinstein_screener/management.py`
- Test: `tests/test_management.py`

**Interfaces:**
- Consumes: `detect_wyckoff_structure` (Plan 2), aplicado a datos de timeframe superior (mensual o trimestral) en vez de semanal.
- Produces: `project_po3_ceiling(df_monthly: pd.DataFrame, df_quarterly: pd.DataFrame, weekly_phase_b_range: float, fallback_lookback: int = 24, sc_search_window: int = 26, ar_window: int = 6, st_window: int = 6, range_lookback: int = 6, volume_lookback: int = 6, new_low_lookback: int = 6, phase_a_recency_weeks: int = 24) -> float`.

**Definición (acordada)**:
1. Se calcula el "rango mensual típico" = rango medio (`High - Low`) de los últimos `fallback_lookback` (24) meses.
2. Si el rango de la Fase B semanal (`weekly_phase_b_range`, ya calculado por quien orqueste a partir de `WyckoffStructure.range_high - WyckoffStructure.range_low`) es mayor que ese rango mensual típico, se usa `df_quarterly` como referencia; si no, se usa `df_monthly`.
3. Sobre el DataFrame de referencia, se llama a `detect_wyckoff_structure` con parámetros recalibrados para esa escala (mucho más pequeños que los valores por defecto semanales, que asumían datos semanales) y se toma `range_high` (el máximo del AR de ese ciclo) como techo.
4. Si no se encuentra estructura en el DataFrame de referencia, se usa como respaldo el máximo móvil de los últimos `fallback_lookback` periodos.

- [ ] **Step 1: Añadir los tests que fallan**

Añadir a `tests/test_management.py`:

```python
import math

from weinstein_screener.management import project_po3_ceiling


def _monthly_df(rows, start="2015-01-01", freq="MS"):
    dates = pd.date_range(start, periods=len(rows), freq=freq)
    return pd.DataFrame(rows, index=dates)


def _wyckoff_scenario_rows():
    """Mismo escenario sintético verificado del Plan 2 (Task 1), reutilizado
    aquí a escala mensual: SC en índice 15, AR en 20, ST en 24, Spring en
    35, Distribution en 39 (range_high=138.5)."""
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


def test_project_po3_ceiling_uses_monthly_structure_when_weekly_range_is_small():
    df_monthly = _monthly_df(_wyckoff_scenario_rows())
    df_quarterly = _monthly_df(
        [{"Open": 100, "High": 102, "Low": 98, "Close": 101, "Volume": 500_000} for _ in range(20)],
        start="2010-01-01",
        freq="QS",
    )

    result = project_po3_ceiling(df_monthly, df_quarterly, weekly_phase_b_range=5.0)

    assert result == pytest.approx(138.5)


def test_project_po3_ceiling_falls_back_to_rolling_high_without_a_structure():
    df_monthly_flat = _monthly_df(
        [{"Open": 100, "High": 105, "Low": 95, "Close": 102, "Volume": 500_000} for _ in range(30)]
    )
    df_quarterly = _monthly_df(
        [{"Open": 100, "High": 102, "Low": 98, "Close": 101, "Volume": 500_000} for _ in range(20)],
        start="2010-01-01",
        freq="QS",
    )

    result = project_po3_ceiling(df_monthly_flat, df_quarterly, weekly_phase_b_range=5.0)

    assert result == pytest.approx(105)


def test_project_po3_ceiling_switches_to_quarterly_when_weekly_range_is_large():
    df_monthly = _monthly_df(_wyckoff_scenario_rows())
    df_quarterly_flat = _monthly_df(
        [{"Open": 100, "High": 102, "Low": 98, "Close": 101, "Volume": 500_000} for _ in range(20)],
        start="2010-01-01",
        freq="QS",
    )

    result = project_po3_ceiling(df_monthly, df_quarterly_flat, weekly_phase_b_range=1000.0)

    assert result == pytest.approx(102)
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_management.py -v -k project_po3_ceiling
```

Esperado: FAIL — `ImportError: cannot import name 'project_po3_ceiling'`.

- [ ] **Step 3: Implementar `project_po3_ceiling`**

Añadir a `weinstein_screener/management.py`:

```python
def project_po3_ceiling(
    df_monthly: pd.DataFrame,
    df_quarterly: pd.DataFrame,
    weekly_phase_b_range: float,
    fallback_lookback: int = 24,
    sc_search_window: int = 26,
    ar_window: int = 6,
    st_window: int = 6,
    range_lookback: int = 6,
    volume_lookback: int = 6,
    new_low_lookback: int = 6,
    phase_a_recency_weeks: int = 24,
) -> float:
    """Proyecta el techo de referencia PO3 sobre datos de timeframe
    superior. Por defecto usa datos mensuales; pasa a trimestrales si
    `weekly_phase_b_range` supera el rango mensual típico (medio, de los
    últimos `fallback_lookback` meses). Reutiliza `detect_wyckoff_structure`
    con parámetros recalibrados para esta escala (mucho más pequeños que
    los valores por defecto semanales). Si no se encuentra estructura,
    usa como respaldo el máximo móvil de `fallback_lookback` periodos.
    """
    monthly_ranges = (df_monthly["High"] - df_monthly["Low"]).iloc[-fallback_lookback:]
    monthly_typical_range = monthly_ranges.mean()

    df_reference = df_quarterly if weekly_phase_b_range > monthly_typical_range else df_monthly

    structure = detect_wyckoff_structure(
        df_reference,
        range_lookback=range_lookback,
        volume_lookback=volume_lookback,
        new_low_lookback=new_low_lookback,
        sc_search_window=sc_search_window,
        ar_window=ar_window,
        st_window=st_window,
        phase_a_recency_weeks=phase_a_recency_weeks,
    )
    if structure is not None:
        return structure.range_high

    return df_reference["High"].iloc[-fallback_lookback:].max()
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_management.py -v
```

Esperado: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/management.py tests/test_management.py
git commit -m "feat: add PO3 ceiling projection on higher-timeframe data"
```

---

### Task 4: Señal de salida (parcial + total)

**Files:**
- Modify: `weinstein_screener/management.py`
- Test: `tests/test_management.py`

**Interfaces:**
- Consumes: `project_po3_ceiling` (Task 3), `close_above_ma` (Plan 1, `weinstein_screener.regime` — recibido como valor booleano ya calculado, no importado dentro de esta función).
- Produces:
  - `ExitSignal` (dataclass): `partial_take_profit: bool`, `full_exit: bool`.
  - `evaluate_exit_signal(current_close: float, po3_ceiling: float, current_week_close_above_ma: bool) -> ExitSignal`.

**Definición (acordada)**: `partial_take_profit` es `True` cuando el precio actual alcanza o supera el techo PO3 — la alerta indica cerrar un 25-30% de la posición (este porcentaje es una decisión operativa del usuario al recibir la alerta, no un valor que la función devuelva, ya que el tamaño de posición no está automatizado — ver documento de diseño, sección 3). `full_exit` es `True` cuando la semana actual cierra por debajo de la MA30w (`current_week_close_above_ma=False`), independientemente de si se ha alcanzado o no el techo PO3.

- [ ] **Step 1: Añadir los tests que fallan**

Añadir a `tests/test_management.py`:

```python
from weinstein_screener.management import evaluate_exit_signal


def test_evaluate_exit_signal_flags_partial_at_the_po3_ceiling():
    result = evaluate_exit_signal(current_close=140.0, po3_ceiling=138.5, current_week_close_above_ma=True)

    assert result.partial_take_profit is True
    assert result.full_exit is False


def test_evaluate_exit_signal_flags_full_exit_below_the_ma30w():
    result = evaluate_exit_signal(current_close=120.0, po3_ceiling=138.5, current_week_close_above_ma=False)

    assert result.partial_take_profit is False
    assert result.full_exit is True
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_management.py -v -k evaluate_exit_signal
```

Esperado: FAIL — `ImportError: cannot import name 'evaluate_exit_signal'`.

- [ ] **Step 3: Implementar `ExitSignal` y `evaluate_exit_signal`**

Añadir a `weinstein_screener/management.py`:

```python
@dataclass
class ExitSignal:
    partial_take_profit: bool
    full_exit: bool


def evaluate_exit_signal(
    current_close: float,
    po3_ceiling: float,
    current_week_close_above_ma: bool,
) -> ExitSignal:
    """Señal de salida: parcial al tocar el techo PO3, total al perder la
    MA30w (independientemente de si se ha tocado o no el techo).
    """
    return ExitSignal(
        partial_take_profit=current_close >= po3_ceiling,
        full_exit=not current_week_close_above_ma,
    )
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_management.py -v
```

Esperado: `9 passed`.

- [ ] **Step 5: Ejecutar toda la suite de tests del proyecto**

```bash
pytest -v
```

Esperado: `67 passed` (58 de los Planes 1-3 + 9 de este plan).

- [ ] **Step 6: Commit**

```bash
git add weinstein_screener/management.py tests/test_management.py
git commit -m "feat: add exit signal (partial at PO3 ceiling, full below MA30w)"
```

---

## Siguiente paso

Con este plan completado, el sistema tiene todas las piezas de detección: régimen Weinstein (Plan 1), estructura Wyckoff/CRT (Plan 2), entradas ICT (Plan 3), y ahora la Entrada 2, la gestión conjunta, y la salida (Plan 4). El **Plan 5** cubrirá el importador de la Etapa 1 (script Pine para TradingView + parseo del CSV exportado), y el **Plan 6** la app Streamlit que junta todo en un dashboard visible.
