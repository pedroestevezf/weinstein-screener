# Revisión — JAC/BUEC y objetivo por amplitud de rango — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corregir terminología mal aplicada en código ya mergeado de los Planes 2 y 3 (JAC en vez de "Distribution", BUEC en vez de "retest" genérico), y sustituir la Task 3 original del Plan 4 (techo PO3 sobre timeframe superior — mezcla indebida con terminología ICT) por un objetivo de toma de beneficios basado en la amplitud del propio rango de acumulación semanal ya detectado por el Plan 2.

**Architecture:** Dos refactors de nombres sobre módulos existentes (`weinstein_screener/wyckoff.py`, `weinstein_screener/ict.py`) sin cambio de lógica, seguidos de la implementación completa (revisada) de `weinstein_screener/management.py` — el Plan 4 original nunca llegó a implementarse (solo se escribió y confirmó el documento de plan), así que aquí se implementa directamente la versión corregida, no se revierte código.

**Tech Stack:** Python 3.9+, pandas. Sin dependencias nuevas.

## Global Constraints

- Python 3.9+, entorno virtual local en `.venv/` (ya existente).
- Dependencias pinneadas en `requirements.txt` con cota superior — no se añade ninguna dependencia nueva.
- Los renombrados (Tasks 1 y 2) son refactors puros — **cero cambio de comportamiento**. Cualquier test que cambie de valor esperado (no solo de nombre) en estas dos tareas es una señal de que algo se ha hecho mal.
- `project_range_target` (Task 4) no tiene parámetros opcionales, no hace I/O, y sigue la misma garantía de invariante que el resto del proyecto: datos inconsistentes (`range_high <= range_low`) devuelven `None` en vez de un resultado inválido.

## Alcance de esta revisión

Cubre:
- Task 1: renombrar `distribution_index` → `jac_index` y `find_distribution` → `find_jac` en el Plan 2 (`wyckoff.py`).
- Task 2: renombrar `RetestResult` → `BuecResult`, `find_retest` → `find_buec`, `retest_index` → `buec_index` en el Plan 3 (`ict.py`) — **solo** en el contexto de la Entrada 3; `retest_tolerance`/`high_confidence` dentro de `find_spring_reentry_mss` (Entrada 1) es un concepto distinto (el retest post-reingreso del Spring, no un BUEC) y no se toca.
- Task 3: Entrada 2 (usa `jac_index`) + gestión conjunta (sin cambio de lógica) en `management.py`.
- Task 4: `project_range_target` — sustituye por completo a la `project_po3_ceiling` del plan original. Sin timeframes superiores, sin parámetros recalibrados, sin fallback — aritmética pura sobre `range_high`/`range_low` del ciclo semanal ya detectado.
- Task 5: señal de salida, con el parámetro renombrado de `po3_ceiling` a `range_target` (misma lógica).

**Nota de precisión terminológica**: `project_range_target` implementa una **proyección vertical por amplitud del rango** (`entry_price + (range_high - range_low)`), inspirada en el principio Cause→Effect de Wyckoff, pero **no es el conteo clásico de Point & Figure** (que cuenta la anchura horizontal de la congestión en un gráfico P&F y la proyecta con el tamaño de caja). Se documenta así explícitamente en el código para no reclamar más precisión de la que tiene.

**Fuera de alcance**: el importador de la Etapa 1 (Plan 5) y la app Streamlit (Plan 6).

---

### Task 1: Renombrar `distribution_index` → `jac_index` en el Plan 2

**Files:**
- Modify: `weinstein_screener/wyckoff.py`
- Modify: `tests/test_wyckoff.py`

**Alcance exacto (verificado con `git grep -n "distribution_index\|Distribution" -- weinstein_screener/ tests/` antes de escribir esta tarea):**
- `weinstein_screener/wyckoff.py`: la función `find_distribution` (línea ~146) pasa a llamarse `find_jac`; el campo `distribution_index: int | None` del dataclass `WyckoffStructure` pasa a `jac_index: int | None`; la variable local `distribution_index = find_distribution(...)` pasa a `jac_index = find_jac(...)`; el comentario que menciona "el Spring y la Distribution" pasa a "el Spring y el JAC".
- `tests/test_wyckoff.py`: el comentario del escenario sintético ("...Spring en 35, Distribution en 39") y la aserción `result.distribution_index == 39` pasan a referenciar JAC / `jac_index`.

- [ ] **Step 1: Aplicar el renombrado en `weinstein_screener/wyckoff.py`**

Cambiar la definición de la función (línea ~146):
```python
def find_distribution(df: pd.DataFrame, phase_b_start: int, as_of: int, ar_high: float) -> int | None:
    """Primera semana cuyo cierre rompe al alza `ar_high` (el máximo del
    Automatic Rally, la resistencia de toda la estructura) con volumen por
    encima de la media de la Fase B hasta ese punto (sin look-ahead).
    """
```
por:
```python
def find_jac(df: pd.DataFrame, phase_b_start: int, as_of: int, ar_high: float) -> int | None:
    """Primera semana cuyo cierre rompe al alza `ar_high` (el máximo del
    Automatic Rally, la resistencia de toda la estructura) con volumen por
    encima de la media de la Fase B hasta ese punto (sin look-ahead).

    Este evento es el JAC (Jump Across the Creek) de Wyckoff clásico: el
    "salto" alcista fuera del rango de acumulación con volumen, Fase D.
    No confundir con "Distribution" — en Wyckoff clásico ese término
    designa una estructura de techo bajista, lo opuesto a lo que se
    detecta aquí.
    """
```

Cambiar el campo del dataclass `WyckoffStructure`:
```python
    distribution_index: int | None
```
por:
```python
    jac_index: int | None  # = JAC (Jump Across the Creek): ruptura de range_high con volumen, Fase D
```

Cambiar el comentario que precede a `spring_index = find_spring(...)`:
```python
    # El rango de referencia es el de TODA la estructura (SC=soporte, AR=resistencia),
    # no un rango más local observado solo dentro de la Fase B — ver la nota en la
    # Task 4 y la Task 5 sobre por qué esto importa para el Spring y la Distribution.
```
por:
```python
    # El rango de referencia es el de TODA la estructura (SC=soporte, AR=resistencia),
    # no un rango más local observado solo dentro de la Fase B — ver la nota en la
    # Task 4 y la Task 5 sobre por qué esto importa para el Spring y el JAC.
```

Cambiar la asignación y el `return`:
```python
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
por:
```python
    jac_index = find_jac(df_weekly, st_index, as_of, range_high)

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
        jac_index=jac_index,
    )
```

- [ ] **Step 2: Aplicar el renombrado en `tests/test_wyckoff.py`**

Verificado con `git grep -n "distribution\|Distribution" tests/test_wyckoff.py` — estos son TODOS los sitios a cambiar, no una muestra:

1. El import al inicio del archivo: `find_distribution,` → `find_jac,`.
2. Docstring de `_wyckoff_scenario_rows`: `SC en índice 15, AR en 20, ST en 24, Spring en 35, Distribution en 39.` → `..., Spring en 35, JAC en 39.`
3. Nombre de test `test_find_distribution_locates_the_breakout_week` → `test_find_jac_locates_the_breakout_week`; dentro, `find_distribution(df, phase_b_start=24, as_of=39, ar_high=138.5)` → `find_jac(df, phase_b_start=24, as_of=39, ar_high=138.5)`.
4. Nombre de test `test_find_distribution_returns_none_without_a_breakout` → `test_find_jac_returns_none_without_a_breakout`; dentro, `find_distribution(df, phase_b_start=0, as_of=14, ar_high=110.0)` → `find_jac(df, phase_b_start=0, as_of=14, ar_high=110.0)`.
5. Nombre de test `test_find_distribution_ignores_a_close_that_does_not_reach_the_rally_high` → `test_find_jac_ignores_a_close_that_does_not_reach_the_rally_high`; el comentario `# -- no debe contar como Distribution, aunque el volumen sea alto.` → `# -- no debe contar como JAC, aunque el volumen sea alto.`; dentro, `find_distribution(df, phase_b_start=0, as_of=5, ar_high=110.0)` → `find_jac(df, phase_b_start=0, as_of=5, ar_high=110.0)`.
6. `assert result.distribution_index == 39` → `assert result.jac_index == 39`.

Confirmar con `grep -n "distribution\|Distribution" tests/test_wyckoff.py` (insensible a mayúsculas) que no queda ninguna ocurrencia tras el cambio.

Revisar el resto del archivo por cualquier otra ocurrencia de `find_distribution`, `distribution_index` o `Distribution` que no se haya cubierto arriba (usar `grep -n "distribution\|Distribution" tests/test_wyckoff.py` para confirmar que no queda ninguna tras el cambio).

- [ ] **Step 3: Ejecutar toda la suite y comprobar que pasa con el mismo número de tests que antes**

```bash
source .venv/bin/activate
pytest -v
```

Esperado: `58 passed` (el mismo número que antes del renombrado — esto es un refactor puro, no debe cambiar cuántos tests hay ni su resultado).

- [ ] **Step 4: Commit**

```bash
git add weinstein_screener/wyckoff.py tests/test_wyckoff.py
git commit -m "refactor: rename distribution_index/find_distribution to jac_index/find_jac (JAC, not a top structure)"
```

---

### Task 2: Renombrar el retest de la Entrada 3 a BUEC en el Plan 3

**Files:**
- Modify: `weinstein_screener/ict.py`
- Modify: `tests/test_ict.py`

**Alcance exacto (verificado con `git grep -n "retest\|Retest" -- weinstein_screener/ict.py tests/test_ict.py` antes de escribir esta tarea) — solo el retest de la Entrada 3, NO el de `find_spring_reentry_mss` (Entrada 1, concepto distinto):**
- `RetestResult` (dataclass) → `BuecResult`.
- `find_retest` (función) → `find_buec`.
- El campo `retest_index` del dataclass y su uso en `find_entry_3_signal` → `buec_index`.
- La variable local `retest` dentro de `find_entry_3_signal` (que guarda el resultado de `find_retest`/`find_buec`) → `buec`.
- **No tocar**: `retest_tolerance`, `high_confidence`, ni ninguna mención de "retest" dentro de `find_spring_reentry_mss` — ese es el retest post-reingreso del Spring de la Entrada 1, un concepto distinto al BUEC.

- [ ] **Step 1: Aplicar el renombrado en `weinstein_screener/ict.py`**

Cambiar el dataclass:
```python
@dataclass
class RetestResult:
    retest_index: int
    volume_declining: bool
    no_supply: bool
```
por:
```python
@dataclass
class BuecResult:
    buec_index: int
    volume_declining: bool
    no_supply: bool
```

Cambiar la firma y el cuerpo de `find_retest` (incluyendo el docstring y el `return`):
```python
def find_retest(
    df: pd.DataFrame,
    ar_high: float,
    breakout_index: int,
    window: int = 5,
    tolerance: float = 0.05,
    volume_decline_fraction: float = 0.8,
    no_supply_lookback: int = 10,
) -> RetestResult | None:
```
por:
```python
def find_buec(
    df: pd.DataFrame,
    ar_high: float,
    breakout_index: int,
    window: int = 5,
    tolerance: float = 0.05,
    volume_decline_fraction: float = 0.8,
    no_supply_lookback: int = 10,
) -> BuecResult | None:
```
(mantener el cuerpo de la función igual, solo actualizar el tipo de retorno en la firma y cambiar el nombre de la función que se llama a sí misma en el docstring si lo menciona explícitamente). Dentro del cuerpo, cambiar `return RetestResult(retest_index=i, volume_declining=volume_declining, no_supply=no_supply)` por `return BuecResult(buec_index=i, volume_declining=volume_declining, no_supply=no_supply)`.

Actualizar el docstring de `find_buec` para nombrar el evento correctamente (BUEC = Back Up to Edge of Creek — el reteste de la zona rota desde arriba, tras el JAC, antes de continuar el markup) en vez de "retest" genérico.

En `find_entry_3_signal`, cambiar:
```python
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
por:
```python
    buec = find_buec(
        df_daily, ar_high, breakout_index, window, tolerance, volume_decline_fraction, no_supply_lookback
    )
    if buec is None:
        return None

    order_block_index = find_order_block(
        df_daily, buec.buec_index + 1, ob_lookback, min_index=buec.buec_index
    )
    if order_block_index is None:
        return None

    fvg_index = None
    fvg_start = buec.buec_index
    fvg_end = min(len(df_daily) - 1, buec.buec_index + window)
    if fvg_end - fvg_start >= 2:
        fvg_index = find_fair_value_gap(
            df_daily, fvg_start, fvg_end, atr, fvg_body_multiplier, fvg_body_lookback, fvg_gap_range_fraction
        )

    entry_price = df_daily["High"].iloc[order_block_index]
    stop_loss = df_daily["Low"].iloc[buec.buec_index]

    if entry_price <= stop_loss:
        return None

    return EntrySignal(
        trigger_index=buec.buec_index,
        order_block_index=order_block_index,
        fvg_index=fvg_index,
        entry_price=entry_price,
        stop_loss=stop_loss,
        high_confidence=buec.no_supply,
    )
```

Actualizar también el docstring de `find_entry_3_signal` (menciona "retest de `ar_high`" y "no hay retest") para decir "BUEC" en vez de "retest" donde corresponda.

- [ ] **Step 2: Aplicar el renombrado en `tests/test_ict.py`**

Actualizar el bloque de import al inicio del archivo: `find_retest` → `find_buec`.

En cada test que use `find_retest(...)`, `.retest_index`, o mencione "retest"/"Retest" en el **contexto de la Entrada 3** (nombres de función de test como `test_find_retest_...`, comentarios de filas como `# retest, índice 2`), renombrar a `find_buec`, `.buec_index`, y `test_find_buec_...` / `# BUEC, índice 2` respectivamente. Esto incluye (verificar con `grep -n "retest\|Retest" tests/test_ict.py` antes y después del cambio):
- `test_find_retest_locates_the_retest_with_declining_volume` → `test_find_buec_locates_the_buec_with_declining_volume`
- `test_find_retest_triggers_on_the_first_candidate_day` → `test_find_buec_triggers_on_the_first_candidate_day`
- `test_find_retest_returns_none_without_touching_the_band` → `test_find_buec_returns_none_without_touching_the_band`
- `test_find_retest_triggers_via_no_supply_candle` → `test_find_buec_triggers_via_no_supply_candle`
- `test_find_entry_3_signal_composes_retest_order_block_and_stop_loss` → `test_find_entry_3_signal_composes_buec_order_block_and_stop_loss`
- `test_find_entry_3_signal_can_find_a_reinforcing_fvg_after_the_retest` → `test_find_entry_3_signal_can_find_a_reinforcing_fvg_after_the_buec`
- `test_find_entry_3_signal_returns_none_without_a_retest` → `test_find_entry_3_signal_returns_none_without_a_buec`

**No renombrar** `test_find_spring_reentry_mss_flags_high_confidence_on_a_post_reentry_retest` ni su comentario `# retest tras reingreso, índice 7` — pertenece a la Entrada 1, no a la Entrada 3.

- [ ] **Step 3: Ejecutar toda la suite y comprobar que pasa con el mismo número de tests que antes**

```bash
pytest -v
```

Esperado: `58 passed` (refactor puro, mismo número de tests, mismo resultado).

- [ ] **Step 4: Commit**

```bash
git add weinstein_screener/ict.py tests/test_ict.py
git commit -m "refactor: rename Entrada 3 retest concepts to BUEC (Back Up to Edge of Creek)"
```

---

### Task 3: Entrada 2 (JAC) y gestión conjunta

**Files:**
- Create: `weinstein_screener/management.py`
- Test: `tests/test_management.py`

**Interfaces:**
- `Entry2Signal` (dataclass): `trigger_index: int`, `entry_price: float`, `stop_loss: float`.
- `find_entry_2_signal(df_weekly: pd.DataFrame, jac_index: int | None, atr_weekly: pd.Series, sl_atr_multiplier: float = 1.5) -> Entry2Signal | None`. Precio de entrada = cierre de la semana del JAC (`WyckoffStructure.jac_index`, Task 1). Stop-loss = entrada − `sl_atr_multiplier` × ATR semanal de esa semana. `None` si `jac_index` es `None` o si `entry_price <= stop_loss`.
- `ManagementAlert` (dataclass): `move_entry1_to_breakeven: bool`, `resize_entry2_pct: float | None`, `resize_entry3_pct: float | None`.
- `evaluate_position_management(entry1_triggered: bool, entry1_stopped_out: bool, entry2_triggered: bool, base_entry2_pct: float = 30.0, base_entry3_pct: float = 40.0) -> ManagementAlert`. Sin cambios de lógica respecto al diseño original: `move_entry1_to_breakeven` es `True` cuando la Entrada 1 sigue viva (activada y no detenida por su SL) y se activa la Entrada 2 (JAC); el redimensionamiento (a ~43%/57% con los valores por defecto) solo se calcula si la Entrada 1 saltó por su SL.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_management.py`:

```python
import pandas as pd
import pytest

from weinstein_screener.management import find_entry_2_signal, evaluate_position_management


def _weekly_df(rows):
    dates = pd.date_range("2020-01-06", periods=len(rows), freq="W-MON")
    return pd.DataFrame(rows, index=dates)


def test_find_entry_2_signal_composes_price_and_stop_loss():
    rows = [{"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 500_000} for _ in range(7)]
    rows.append({"Open": 118, "High": 125, "Low": 117, "Close": 124, "Volume": 900_000})  # JAC, índice 7
    rows.append({"Open": 124, "High": 128, "Low": 123, "Close": 126, "Volume": 700_000})
    df = _weekly_df(rows)
    atr = pd.Series([2.0] * len(df), index=df.index)

    result = find_entry_2_signal(df, jac_index=7, atr_weekly=atr, sl_atr_multiplier=1.5)

    assert result is not None
    assert result.trigger_index == 7
    assert result.entry_price == pytest.approx(124)
    assert result.stop_loss == pytest.approx(121.0)


def test_find_entry_2_signal_returns_none_without_a_jac():
    rows = [{"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 500_000} for _ in range(5)]
    df = _weekly_df(rows)
    atr = pd.Series([2.0] * len(df), index=df.index)

    result = find_entry_2_signal(df, jac_index=None, atr_weekly=atr)

    assert result is None


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
pytest tests/test_management.py -v
```

Esperado: FAIL — `ModuleNotFoundError: No module named 'weinstein_screener.management'`.

- [ ] **Step 3: Implementar `Entry2Signal`, `find_entry_2_signal`, `ManagementAlert`, `evaluate_position_management`**

Crear `weinstein_screener/management.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Entry2Signal:
    trigger_index: int
    entry_price: float
    stop_loss: float


def find_entry_2_signal(
    df_weekly: pd.DataFrame,
    jac_index: int | None,
    atr_weekly: pd.Series,
    sl_atr_multiplier: float = 1.5,
) -> Entry2Signal | None:
    """Compone el disparador de la Entrada 2: cierre de la semana del JAC
    (Jump Across the Creek — ruptura de `range_high` con volumen, Fase D
    de Wyckoff, ver `weinstein_screener.wyckoff.find_jac`) como precio de
    entrada, stop-loss basado en ATR semanal. None si no hay JAC o si el
    precio de entrada no queda por encima del stop-loss.
    """
    if jac_index is None:
        return None

    entry_price = df_weekly["Close"].iloc[jac_index]
    stop_loss = entry_price - sl_atr_multiplier * atr_weekly.iloc[jac_index]

    if entry_price <= stop_loss:
        return None

    return Entry2Signal(trigger_index=jac_index, entry_price=entry_price, stop_loss=stop_loss)


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
    activa la Entrada 2 (JAC). Redimensionamiento: solo si la Entrada 1
    saltó por su SL (Spring fallido), manteniendo el ratio relativo de
    las Entradas 2 y 3 (JAC / BUEC) pero sumando el 100% en vez del 70%
    original.
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
git commit -m "feat: add Entrada 2 (JAC) signal and joint position management alerts"
```

---

### Task 4: Objetivo por amplitud de rango (sustituye al techo PO3)

**Files:**
- Modify: `weinstein_screener/management.py`
- Test: `tests/test_management.py`

**Interfaces:**
- `project_range_target(entry_price: float, range_high: float, range_low: float) -> float | None`. Proyecta `entry_price + (range_high - range_low)` — una proyección vertical por amplitud del rango, inspirada en el principio Cause→Effect de Wyckoff pero **no** el conteo clásico de Point & Figure (ver nota de precisión terminológica en la cabecera de este documento). `None` si `range_high <= range_low` (dato inconsistente).

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_management.py`:

```python
from weinstein_screener.management import project_range_target


def test_project_range_target_projects_the_range_amplitude_from_entry():
    result = project_range_target(entry_price=124.0, range_high=124.0, range_low=108.0)

    assert result == pytest.approx(140.0)


def test_project_range_target_returns_none_with_inconsistent_range():
    result = project_range_target(entry_price=124.0, range_high=100.0, range_low=108.0)

    assert result is None
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_management.py -v -k project_range_target
```

Esperado: FAIL — `ImportError: cannot import name 'project_range_target'`.

- [ ] **Step 3: Implementar `project_range_target`**

Añadir a `weinstein_screener/management.py`:

```python
def project_range_target(entry_price: float, range_high: float, range_low: float) -> float | None:
    """Proyecta el objetivo de toma de beneficios parcial como la
    amplitud del propio rango de acumulación semanal (Cause) sumada al
    precio de entrada.

    Es una proyección VERTICAL (altura del rango en el gráfico de
    barras), inspirada en el principio Cause→Effect de Wyckoff, pero no
    es el conteo clásico de Point & Figure (que cuenta la anchura
    horizontal de la congestión en un gráfico P&F y la proyecta con el
    tamaño de caja) — no reclamar esa precisión al consumir este valor.

    None si el rango es inconsistente (range_high <= range_low).
    """
    if range_high <= range_low:
        return None
    return entry_price + (range_high - range_low)
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_management.py -v
```

Esperado: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/management.py tests/test_management.py
git commit -m "feat: add range-amplitude profit target (replaces PO3 ceiling)"
```

---

### Task 5: Señal de salida (parcial por amplitud + total por MA30w)

**Files:**
- Modify: `weinstein_screener/management.py`
- Test: `tests/test_management.py`

**Interfaces:**
- `ExitSignal` (dataclass): `partial_take_profit: bool`, `full_exit: bool`.
- `evaluate_exit_signal(current_close: float, range_target: float, current_week_close_above_ma: bool) -> ExitSignal`. `partial_take_profit` es `True` cuando el precio actual alcanza o supera `range_target` (Task 4). `full_exit` es `True` cuando la semana actual cierra por debajo de la MA30w (`current_week_close_above_ma=False`, `weinstein_screener.regime.close_above_ma` del Plan 1) — la invalidación de régimen manda sobre la gestión táctica de beneficios, independientemente de si se alcanzó o no el objetivo de amplitud.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_management.py`:

```python
from weinstein_screener.management import evaluate_exit_signal


def test_evaluate_exit_signal_flags_partial_at_the_range_target():
    result = evaluate_exit_signal(current_close=140.0, range_target=138.5, current_week_close_above_ma=True)

    assert result.partial_take_profit is True
    assert result.full_exit is False


def test_evaluate_exit_signal_flags_full_exit_below_the_ma30w():
    result = evaluate_exit_signal(current_close=120.0, range_target=138.5, current_week_close_above_ma=False)

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
    range_target: float,
    current_week_close_above_ma: bool,
) -> ExitSignal:
    """Señal de salida: parcial al alcanzar el objetivo de amplitud de
    rango, total al perder la MA30w (independientemente de si se ha
    alcanzado o no el objetivo — la invalidación de régimen manda).
    """
    return ExitSignal(
        partial_take_profit=current_close >= range_target,
        full_exit=not current_week_close_above_ma,
    )
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_management.py -v
```

Esperado: `8 passed`.

- [ ] **Step 5: Ejecutar toda la suite de tests del proyecto**

```bash
pytest -v
```

Esperado: `66 passed` (58 de los Planes 1-3 + 8 de este plan).

- [ ] **Step 6: Commit**

```bash
git add weinstein_screener/management.py tests/test_management.py
git commit -m "feat: add exit signal (partial at range target, full below MA30w)"
```

---

## Siguiente paso

Con esta revisión, el ciclo completo de las 3 entradas y la salida queda con terminología Wyckoff clásica coherente (JAC, BUEC, objetivo por amplitud de rango) y sin mezcla indebida con ICT (PO3). El documento de diseño original (`2026-08-09-estrategia-weinstein-wyckoff-crt-ict-design.md`) debería actualizarse también con esta terminología antes de empezar el Plan 6 (dashboard), para que herede los nombres correctos desde el origen — pendiente como tarea de documentación, no de código.
