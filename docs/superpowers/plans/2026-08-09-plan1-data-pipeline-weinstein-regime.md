# Plan 1 de 6 — Pipeline de datos y régimen Weinstein — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir la base del sistema — descarga y cacheo de datos OHLCV vía yfinance, indicadores técnicos (media móvil, pendiente, ATR) y la detección del régimen Weinstein Stage 2 (media móvil de 30 semanas ascendente).

**Architecture:** Paquete Python plano (`weinstein_screener/`) con módulos independientes: `data.py` (descarga/caché), `indicators.py` (funciones puras sobre DataFrames de pandas), `regime.py` (lógica de negocio de Weinstein sobre los indicadores). Cada módulo es testeable de forma aislada sin red ni disco real (inyección de dependencias para `downloader` en `data.py`, `tmp_path` de pytest para el caché).

**Tech Stack:** Python 3.9+, pandas, yfinance, pyarrow (caché en parquet), pytest.

## Global Constraints

- Python 3.9+, entorno virtual local en `.venv/`. (Ajustado durante la implementación: la máquina de desarrollo solo tiene Python 3.9.6 disponible, sin Homebrew/pyenv instalados; instalar 3.11+ habría requerido cambios a nivel de sistema que se han evitado deliberadamente. El código no usa ninguna sintaxis específica de 3.11.)
- Dependencias fijadas en `requirements.txt`, con cota superior (ej. `pandas>=2.0,<3.0`) — nunca solo un mínimo sin acotar.
- Ninguna llamada de red en los tests unitarios — toda función que llame a yfinance debe aceptar un `downloader` inyectable.
- Los parámetros de ventana/lookback (MA30, slope_lookback, ventana ATR) son argumentos de función con valor por defecto, nunca constantes hardcodeadas sin parámetro — varios están marcados como "a validar en backtest" en el documento de diseño (`2026-08-09-estrategia-weinstein-wyckoff-crt-ict-design.md`, sección 8) y deben poder variarse sin tocar el código interno.

## Alcance de este plan (1 de 6)

Este es el primero de una serie de planes para implementar el sistema completo descrito en el documento de diseño. Cubre únicamente:
- Descarga y caché local de datos OHLCV (diario y semanal).
- Indicadores: media móvil, pendiente de la media, ATR.
- Detección de "Weinstein Stage 2 activo" (cierre semanal sobre la MA30w + MA30w ascendente).

**Fuera de alcance de este plan** (planes siguientes): detección de estructura Wyckoff (Fases A/B, Selling Climax, Spring), CRT, entradas ICT (MSS/Order Block/FVG), proyección PO3 y salidas, importación del shortlist de la Etapa 1 (TradingView), y la app Streamlit.

---

### Task 1: Scaffolding del proyecto y descarga de datos (`fetch_ohlcv`)

**Files:**
- Create: `requirements.txt`
- Create: `pyproject.toml`
- Create: `weinstein_screener/__init__.py`
- Create: `weinstein_screener/data.py`
- Test: `tests/test_data.py`

**Interfaces:**
- Consumes: nada (primer módulo).
- Produces: `fetch_ohlcv(ticker: str, interval: str, period: str = "10y", downloader=None) -> pd.DataFrame` — DataFrame con columnas `["Open", "High", "Low", "Close", "Volume"]`, índice `DatetimeIndex` llamado `"Date"`. `interval` debe ser `"1d"` o `"1wk"`. `downloader` es una función inyectable con la misma firma que `yfinance.download` (por defecto `yf.download`); se usa para poder testear sin red.

- [ ] **Step 1: Crear el entorno virtual e instalar dependencias**

```bash
cd "/Users/pedroestevezf/Claude/screener weinstein"
python3 -m venv .venv
source .venv/bin/activate
```

Crear `requirements.txt`:

```
pandas>=2.0
yfinance>=0.2.40
pyarrow>=14.0
pytest>=7.4
```

Instalar:

```bash
pip install -r requirements.txt
```

- [ ] **Step 2: Crear la configuración de pytest**

Crear `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 3: Crear el paquete vacío**

Crear `weinstein_screener/__init__.py` (archivo vacío).

- [ ] **Step 4: Escribir los tests que fallan para `fetch_ohlcv`**

Crear `tests/test_data.py`:

```python
import pandas as pd
import pytest

from weinstein_screener.data import fetch_ohlcv


def _fake_downloader(rows: int = 5):
    def _download(ticker, period, interval, progress, auto_adjust):
        dates = pd.date_range("2024-01-01", periods=rows, freq="D")
        return pd.DataFrame(
            {
                "Open": range(rows),
                "High": range(rows),
                "Low": range(rows),
                "Close": range(rows),
                "Volume": range(rows),
            },
            index=dates,
        )

    return _download


def test_fetch_ohlcv_returns_expected_columns():
    df = fetch_ohlcv("FAKE", "1d", downloader=_fake_downloader())

    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df.index.name == "Date"
    assert len(df) == 5


def test_fetch_ohlcv_rejects_invalid_interval():
    with pytest.raises(ValueError, match="interval"):
        fetch_ohlcv("FAKE", "1h")


def test_fetch_ohlcv_raises_on_empty_result():
    def empty_downloader(ticker, period, interval, progress, auto_adjust):
        return pd.DataFrame()

    with pytest.raises(ValueError, match="No data"):
        fetch_ohlcv("FAKE", "1d", downloader=empty_downloader)
```

- [ ] **Step 5: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_data.py -v
```

Esperado: FAIL — `ModuleNotFoundError: No module named 'weinstein_screener.data'` (el módulo aún no existe).

- [ ] **Step 6: Implementar `fetch_ohlcv`**

Crear `weinstein_screener/data.py`:

```python
from __future__ import annotations

import pandas as pd
import yfinance as yf

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def fetch_ohlcv(
    ticker: str,
    interval: str,
    period: str = "10y",
    downloader=None,
) -> pd.DataFrame:
    """Descarga datos OHLCV de un ticker desde Yahoo Finance.

    `interval` debe ser "1d" o "1wk".
    """
    if interval not in ("1d", "1wk"):
        raise ValueError(f"interval must be '1d' or '1wk', got {interval!r}")

    download = downloader or yf.download
    raw = download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)

    if raw.empty:
        raise ValueError(f"No data returned for ticker {ticker!r}")

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw[OHLCV_COLUMNS].copy()
    df.index.name = "Date"
    return df
```

- [ ] **Step 7: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_data.py -v
```

Esperado: `3 passed`.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt pyproject.toml weinstein_screener/__init__.py weinstein_screener/data.py tests/test_data.py
git commit -m "feat: add fetch_ohlcv data download with injectable downloader"
```

---

### Task 2: Caché local en parquet (`get_cached_ohlcv`)

**Files:**
- Modify: `weinstein_screener/data.py`
- Test: `tests/test_data.py`

**Interfaces:**
- Consumes: `fetch_ohlcv(ticker, interval, period="10y", downloader=None) -> pd.DataFrame` (Task 1).
- Produces: `get_cached_ohlcv(ticker: str, interval: str, cache_dir: Path, max_age_days: int = 1, downloader=None) -> pd.DataFrame`.

- [ ] **Step 1: Añadir los tests que fallan para el caché**

Añadir a `tests/test_data.py`:

```python
import os
from pathlib import Path

from weinstein_screener.data import get_cached_ohlcv


def _counting_downloader(calls: list):
    def _download(ticker, period, interval, progress, auto_adjust):
        calls.append(ticker)
        dates = pd.date_range("2024-01-01", periods=3, freq="D")
        return pd.DataFrame(
            {"Open": [1, 2, 3], "High": [1, 2, 3], "Low": [1, 2, 3], "Close": [1, 2, 3], "Volume": [1, 2, 3]},
            index=dates,
        )

    return _download


def test_get_cached_ohlcv_downloads_when_no_cache(tmp_path: Path):
    calls: list = []

    df = get_cached_ohlcv("FAKE", "1d", cache_dir=tmp_path, downloader=_counting_downloader(calls))

    assert len(calls) == 1
    assert len(df) == 3
    assert (tmp_path / "FAKE_1d.parquet").exists()


def test_get_cached_ohlcv_uses_fresh_cache_without_downloading(tmp_path: Path):
    calls: list = []
    downloader = _counting_downloader(calls)

    get_cached_ohlcv("FAKE", "1d", cache_dir=tmp_path, downloader=downloader)
    get_cached_ohlcv("FAKE", "1d", cache_dir=tmp_path, downloader=downloader)

    assert len(calls) == 1


def test_get_cached_ohlcv_redownloads_when_cache_is_stale(tmp_path: Path):
    calls: list = []
    downloader = _counting_downloader(calls)

    get_cached_ohlcv("FAKE", "1d", cache_dir=tmp_path, max_age_days=1, downloader=downloader)

    cache_path = tmp_path / "FAKE_1d.parquet"
    old_time = cache_path.stat().st_mtime - (2 * 86400)
    os.utime(cache_path, (old_time, old_time))

    get_cached_ohlcv("FAKE", "1d", cache_dir=tmp_path, max_age_days=1, downloader=downloader)

    assert len(calls) == 2
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_data.py -v -k cached
```

Esperado: FAIL — `ImportError: cannot import name 'get_cached_ohlcv'`.

- [ ] **Step 3: Implementar `get_cached_ohlcv`**

Añadir a `weinstein_screener/data.py`:

```python
import time
from pathlib import Path


def get_cached_ohlcv(
    ticker: str,
    interval: str,
    cache_dir: Path,
    max_age_days: int = 1,
    downloader=None,
) -> pd.DataFrame:
    """Devuelve OHLCV para un ticker, usando un caché local en parquet si está fresco."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{ticker}_{interval}.parquet"

    if cache_path.exists():
        age_seconds = time.time() - cache_path.stat().st_mtime
        if age_seconds <= max_age_days * 86400:
            return pd.read_parquet(cache_path)

    df = fetch_ohlcv(ticker, interval, downloader=downloader)
    df.to_parquet(cache_path)
    return df
```

(Añadir `import time` y `from pathlib import Path` a las importaciones al inicio del archivo, junto a las ya existentes.)

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_data.py -v
```

Esperado: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/data.py tests/test_data.py
git commit -m "feat: add local parquet cache layer for OHLCV data"
```

---

### Task 3: Indicadores técnicos (media móvil, pendiente, ATR)

**Files:**
- Create: `weinstein_screener/indicators.py`
- Test: `tests/test_indicators.py`

**Interfaces:**
- Consumes: nada (opera sobre cualquier DataFrame con columnas OHLCV, como el que produce `fetch_ohlcv`/`get_cached_ohlcv`).
- Produces:
  - `moving_average(df: pd.DataFrame, window: int, column: str = "Close") -> pd.Series`
  - `ma_slope(ma: pd.Series, lookback: int) -> pd.Series` (positivo = ascendente)
  - `average_true_range(df: pd.DataFrame, window: int = 14) -> pd.Series`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_indicators.py`:

```python
import pandas as pd
import pytest

from weinstein_screener.indicators import average_true_range, ma_slope, moving_average


def _sample_df():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    return pd.DataFrame(
        {
            "Open": [10, 11, 12, 13, 14, 15],
            "High": [11, 12, 13, 14, 15, 16],
            "Low": [9, 10, 11, 12, 13, 14],
            "Close": [10, 11, 12, 13, 14, 15],
            "Volume": [100, 100, 100, 100, 100, 100],
        },
        index=dates,
    )


def test_moving_average_computes_rolling_mean():
    df = _sample_df()
    ma = moving_average(df, window=3)

    assert pd.isna(ma.iloc[0])
    assert pd.isna(ma.iloc[1])
    assert ma.iloc[2] == pytest.approx(11.0)
    assert ma.iloc[5] == pytest.approx(14.0)


def test_ma_slope_is_positive_for_rising_series():
    df = _sample_df()
    ma = moving_average(df, window=3)
    slope = ma_slope(ma, lookback=2)

    assert slope.iloc[4] == pytest.approx(ma.iloc[4] - ma.iloc[2])
    assert slope.iloc[4] > 0


def test_average_true_range_matches_manual_calculation():
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    df = pd.DataFrame(
        {
            "Open": [10, 12, 11, 15],
            "High": [11, 14, 13, 18],
            "Low": [9, 10, 10, 12],
            "Close": [10, 12, 12, 16],
            "Volume": [100, 100, 100, 100],
        },
        index=dates,
    )

    atr = average_true_range(df, window=2)

    # True Range: día0=2 (sin prevClose), día1=max(4,4,0)=4, día2=max(3,1,2)=3, día3=max(6,6,0)=6
    # ATR (media móvil de ventana 2 sobre True Range):
    # día1=mean(2,4)=3.0, día2=mean(4,3)=3.5, día3=mean(3,6)=4.5
    assert atr.iloc[1] == pytest.approx(3.0)
    assert atr.iloc[2] == pytest.approx(3.5)
    assert atr.iloc[3] == pytest.approx(4.5)
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_indicators.py -v
```

Esperado: FAIL — `ModuleNotFoundError: No module named 'weinstein_screener.indicators'`.

- [ ] **Step 3: Implementar los indicadores**

Crear `weinstein_screener/indicators.py`:

```python
from __future__ import annotations

import pandas as pd


def moving_average(df: pd.DataFrame, window: int, column: str = "Close") -> pd.Series:
    return df[column].rolling(window=window).mean()


def ma_slope(ma: pd.Series, lookback: int) -> pd.Series:
    """Diferencia entre la media móvil actual y `lookback` periodos atrás.

    Positivo = ascendente.
    """
    return ma - ma.shift(lookback)


def average_true_range(df: pd.DataFrame, window: int = 14) -> pd.Series:
    prev_close = df["Close"].shift(1)
    true_range = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window=window).mean()
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_indicators.py -v
```

Esperado: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add weinstein_screener/indicators.py tests/test_indicators.py
git commit -m "feat: add moving average, slope and ATR indicators"
```

---

### Task 4: Detección de régimen Weinstein Stage 2

**Files:**
- Create: `weinstein_screener/regime.py`
- Test: `tests/test_regime.py`

**Interfaces:**
- Consumes: `moving_average(df, window, column="Close") -> pd.Series` y `ma_slope(ma, lookback) -> pd.Series` (Task 3).
- Produces: `weinstein_stage2_active(df_weekly: pd.DataFrame, ma_window: int = 30, slope_lookback: int = 4) -> pd.Series` — serie booleana, `True` en las semanas donde el cierre está por encima de la MA y la MA es ascendente.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_regime.py`:

```python
import pandas as pd

from weinstein_screener.regime import weinstein_stage2_active


def _weekly_df(closes):
    dates = pd.date_range("2020-01-06", periods=len(closes), freq="W-MON")
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c + 1 for c in closes],
            "Low": [c - 1 for c in closes],
            "Close": closes,
            "Volume": [1000] * len(closes),
        },
        index=dates,
    )


def test_stage2_is_false_while_price_stays_flat():
    closes = [100.0] * 40
    df = _weekly_df(closes)

    result = weinstein_stage2_active(df, ma_window=30, slope_lookback=4)

    assert not result.any()


def test_stage2_becomes_true_once_price_breaks_above_a_rising_average():
    flat = [100.0] * 30
    rising = [100.0 + i * 2 for i in range(1, 15)]
    closes = flat + rising
    df = _weekly_df(closes)

    result = weinstein_stage2_active(df, ma_window=30, slope_lookback=4)

    assert not result.iloc[29]
    assert result.iloc[-1]
```

- [ ] **Step 2: Ejecutar los tests y comprobar que fallan**

```bash
pytest tests/test_regime.py -v
```

Esperado: FAIL — `ModuleNotFoundError: No module named 'weinstein_screener.regime'`.

- [ ] **Step 3: Implementar `weinstein_stage2_active`**

Crear `weinstein_screener/regime.py`:

```python
from __future__ import annotations

import pandas as pd

from weinstein_screener.indicators import ma_slope, moving_average


def weinstein_stage2_active(
    df_weekly: pd.DataFrame,
    ma_window: int = 30,
    slope_lookback: int = 4,
) -> pd.Series:
    """Serie booleana por semana: True cuando se confirma Weinstein Stage 2.

    Stage 2 requiere: cierre semanal por encima de la media móvil, y la
    media con pendiente ascendente (valor actual mayor que hace
    `slope_lookback` semanas).
    """
    ma = moving_average(df_weekly, window=ma_window)
    slope = ma_slope(ma, lookback=slope_lookback)

    close_above_ma = df_weekly["Close"] > ma
    ascending_ma = slope > 0

    return close_above_ma & ascending_ma
```

- [ ] **Step 4: Ejecutar los tests y comprobar que pasan**

```bash
pytest tests/test_regime.py -v
```

Esperado: `2 passed`.

- [ ] **Step 5: Ejecutar toda la suite de tests del plan**

```bash
pytest -v
```

Esperado: `11 passed` (6 en `tests/test_data.py` + 3 en `tests/test_indicators.py` + 2 en `tests/test_regime.py`).

- [ ] **Step 6: Commit**

```bash
git add weinstein_screener/regime.py tests/test_regime.py
git commit -m "feat: add Weinstein Stage 2 regime detection"
```

---

## Siguiente paso

Con este plan completado, el sistema puede: descargar/cachear datos OHLCV de cualquier ticker, calcular MA/pendiente/ATR, y saber si un ticker está en Weinstein Stage 2 en un momento dado. El **Plan 2** cubrirá la detección de estructura Wyckoff (Fase A/B, Selling Climax, Spring) y el modelo CRT sobre los tickers que este plan identifique como candidatos.
