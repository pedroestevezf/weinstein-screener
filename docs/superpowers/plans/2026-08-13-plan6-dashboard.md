# Plan 6 de 6 — Dashboard (Streamlit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the two-screen Streamlit dashboard (Screener Filtrado + Detalle de ticker) specified in `docs/superpowers/specs/2026-08-12-plan6-dashboard-design.md`, on top of the already-implemented pipeline (Plans 1-5).

**Architecture:** Pure, independently-testable modules for every piece of new logic (fundamentals fetch, relative volume, "recorrido avanzado" check, chart-data assembly, chart rendering), consumed by two thin orchestration scripts (`scripts/enrich_shortlist.py`, `scripts/dashboard_app.py`) that follow the same "thin script, tested logic lives elsewhere" convention already established by `scripts/run_etapa1.py` (Plan 5).

**Tech Stack:** Python 3.9, pandas, `yfinance`, Streamlit 1.50 (`st.dataframe` with `on_select`/`selection_mode` for row selection — verified present in the installed version), Altair 5.5 (bundled with Streamlit, used for the candlestick+MA+volume chart via layered marks — verified working in this environment; no new heavy dependency needed).

## Global Constraints

- Python 3.9.6 is the only interpreter available in this environment (`.venv`) — no `match` statements, no `X | Y` union syntax outside of `from __future__ import annotations` contexts (already the project-wide convention; every existing module starts with that import — do the same in every new file).
- Run tests with `.venv/bin/python -m pytest -q` from the repo root, never plain `python`/`python3` (no pytest installed there).
- Every function that performs I/O (network, filesystem) must accept an injectable dependency (`downloader`, `info_getter`, etc.) defaulting to the real implementation, so tests never hit the network — this is the established pattern in `data.py::fetch_ohlcv`, `universe.py::get_us_universe`, and `etapa1.py::run_etapa1_screen`. Follow it exactly, do not invent a different DI style.
- Functions that can fail per-item in a batch (fundamentals fetch, per-ticker enrichment) must be tolerant of individual failures and continue, never abort the whole batch — same convention as `run_etapa1_screen`.
- `from __future__ import annotations` at the top of every new module (project-wide convention).
- Docstrings only where something is non-obvious (in Spanish, matching the rest of the project) — do not restate the signature.
- Commit after every task with a terse, imperative message matching the style visible in `git log --oneline -10`.
- The dashboard is read-only/alerts-only — it must never place an order or suggest position sizing beyond what the existing `management.py` alerts already compute. Do not add anything beyond what's specified below.
- `Etapa1ScreenResult`, `WyckoffStructure`, `EntrySignal`, `Entry2Signal`, `ManagementAlert`, `ExitSignal`, `BuecResult` and every function signature referenced below are the CURRENT, already-merged state of this codebase (verified by reading the source directly before writing this plan on 2026-08-13) — do not "improve" or rename them as part of this plan.

---

## Task 1: Ticker fundamentals (`weinstein_screener/fundamentals.py`)

**Files:**
- Create: `weinstein_screener/fundamentals.py`
- Test: `tests/test_fundamentals.py`

**Interfaces:**
- Consumes: nothing from other Plan 6 tasks.
- Produces: `TickerFundamentals` dataclass (`ticker: str`, `sector: str | None`, `market_cap: float | None`, `trailing_pe: float | None`, `ev_to_fcf: float | None`) and `fetch_fundamentals_for_candidates(tickers: list[str], info_getter=None) -> list[TickerFundamentals]`, consumed by Task 5 (`scripts/enrich_shortlist.py`).

Verified with real data during the design brainstorming (`yf.Ticker(t).get_info()` for `WM`/`AAPL`/`NGVC`/`BCML`): `sector`, `marketCap`, `trailingPE`, `enterpriseValue`, `freeCashflow` are all present in the SAME `get_info()` call — no incremental cost for fetching all four. `get_info()` has **no batch equivalent** (~0.4-0.85s per ticker, one HTTP call each) — this module must never be called against the full universe, only the pre-filtered Etapa 1 candidates (enforced by the caller, Task 5, not by this module itself).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fundamentals.py
import pytest

from weinstein_screener.fundamentals import TickerFundamentals, fetch_fundamentals_for_candidates


def test_fetch_fundamentals_for_candidates_maps_known_fields():
    def fake_info_getter(ticker):
        return {
            "sector": "Industrials",
            "marketCap": 90771324928,
            "trailingPE": 59.918205,
            "enterpriseValue": 113475387392,
            "freeCashflow": 2348375040,
        }

    result = fetch_fundamentals_for_candidates(["WM"], info_getter=fake_info_getter)

    assert result == [
        TickerFundamentals(
            ticker="WM",
            sector="Industrials",
            market_cap=90771324928,
            trailing_pe=59.918205,
            ev_to_fcf=pytest.approx(113475387392 / 2348375040),
        )
    ]


def test_fetch_fundamentals_for_candidates_handles_missing_free_cashflow():
    def fake_info_getter(ticker):
        return {
            "sector": "Financial Services",
            "marketCap": 339178816,
            "trailingPE": 25.883331,
            "enterpriseValue": 208148560,
            "freeCashflow": None,
        }

    result = fetch_fundamentals_for_candidates(["BCML"], info_getter=fake_info_getter)

    assert result[0].ev_to_fcf is None
    assert result[0].market_cap == 339178816


def test_fetch_fundamentals_for_candidates_handles_zero_free_cashflow():
    def fake_info_getter(ticker):
        return {"sector": "X", "marketCap": 1.0, "trailingPE": 1.0, "enterpriseValue": 500.0, "freeCashflow": 0}

    result = fetch_fundamentals_for_candidates(["ZZZ"], info_getter=fake_info_getter)

    assert result[0].ev_to_fcf is None


def test_fetch_fundamentals_for_candidates_handles_missing_info_keys():
    def fake_info_getter(ticker):
        return {}  # a ticker with no usable fundamentals data at all

    result = fetch_fundamentals_for_candidates(["NODATA"], info_getter=fake_info_getter)

    assert result[0] == TickerFundamentals(
        ticker="NODATA", sector=None, market_cap=None, trailing_pe=None, ev_to_fcf=None
    )


def test_fetch_fundamentals_for_candidates_tolerates_a_failing_ticker():
    def fake_info_getter(ticker):
        if ticker == "BAD":
            raise ValueError("simulated network failure")
        return {"sector": "Technology", "marketCap": 1.0, "trailingPE": 2.0, "enterpriseValue": 10.0, "freeCashflow": 5.0}

    result = fetch_fundamentals_for_candidates(["GOOD", "BAD", "GOOD2"], info_getter=fake_info_getter)

    assert [r.ticker for r in result] == ["GOOD", "BAD", "GOOD2"]
    assert result[1] == TickerFundamentals(ticker="BAD", sector=None, market_cap=None, trailing_pe=None, ev_to_fcf=None)
    assert result[0].sector == "Technology"
    assert result[2].sector == "Technology"


def test_fetch_fundamentals_for_candidates_preserves_order_and_count():
    def fake_info_getter(ticker):
        return {"sector": ticker, "marketCap": 1.0, "trailingPE": 1.0, "enterpriseValue": 1.0, "freeCashflow": 1.0}

    result = fetch_fundamentals_for_candidates(["A", "B", "C"], info_getter=fake_info_getter)

    assert [r.ticker for r in result] == ["A", "B", "C"]
    assert [r.sector for r in result] == ["A", "B", "C"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_fundamentals.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'weinstein_screener.fundamentals'`

- [ ] **Step 3: Write the implementation**

```python
# weinstein_screener/fundamentals.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TickerFundamentals:
    ticker: str
    sector: str | None
    market_cap: float | None
    trailing_pe: float | None
    ev_to_fcf: float | None


def _default_info_getter(ticker: str) -> dict:
    import yfinance as yf

    return yf.Ticker(ticker).get_info()


def _compute_ev_to_fcf(info: dict) -> float | None:
    enterprise_value = info.get("enterpriseValue")
    free_cashflow = info.get("freeCashflow")
    if enterprise_value is None or not free_cashflow:
        return None
    return enterprise_value / free_cashflow


def fetch_fundamentals_for_candidates(
    tickers: list[str],
    info_getter=None,
) -> list[TickerFundamentals]:
    """Fundamentales (sector, cap. mercado, PER, EV/FCF) por ticker, vía
    `yfinance.Ticker.get_info()`. SOLO llamar sobre listas ya filtradas
    (los candidatos de Etapa 1, no el universo completo) -- `get_info()`
    no tiene equivalente en lote, ~0.4-0.85s por ticker verificado con
    datos reales.

    Tolerante a fallos por ticker: uno que falle no aborta el resto, se
    devuelve con todos los campos a None en la misma posición de la lista
    de salida (mismo orden y cuenta que la entrada).
    """
    info_getter = info_getter or _default_info_getter

    results: list[TickerFundamentals] = []
    for ticker in tickers:
        try:
            info = info_getter(ticker)
        except Exception:
            results.append(
                TickerFundamentals(ticker=ticker, sector=None, market_cap=None, trailing_pe=None, ev_to_fcf=None)
            )
            continue

        results.append(
            TickerFundamentals(
                ticker=ticker,
                sector=info.get("sector"),
                market_cap=info.get("marketCap"),
                trailing_pe=info.get("trailingPE"),
                ev_to_fcf=_compute_ev_to_fcf(info),
            )
        )
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_fundamentals.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (121 pre-existing + 6 new = 127)

- [ ] **Step 6: Commit**

```bash
git add weinstein_screener/fundamentals.py tests/test_fundamentals.py
git commit -m "feat: add per-ticker fundamentals fetch (sector, market cap, PER, EV/FCF)"
```

---

## Task 2: Relative volume (`weinstein_screener/indicators.py`)

**Files:**
- Modify: `weinstein_screener/indicators.py` (add one function at the end of the existing file — do not touch `moving_average`, `ma_slope`, `pct_distance_from_ma`, or `average_true_range`)
- Test: `tests/test_indicators.py` (add new test functions — do not modify existing ones)

**Interfaces:**
- Consumes: nothing from other Plan 6 tasks.
- Produces: `relative_volume(df_weekly: pd.DataFrame, recent_weeks: int = 3, baseline_weeks: int = 20) -> float | None`, consumed by Task 5 (`scripts/enrich_shortlist.py`).

Definition, decided explicitly with the user during brainstorming: mean volume of the last `recent_weeks` CLOSED weeks, divided by the mean volume of the `baseline_weeks` weeks immediately before those — NOT a single-week comparison (too noisy), and NOT the raw `averageVolume`/`averageDailyVolume10Day` fields from `yfinance.get_info()` (those are DAILY averages, not weekly, and the user specifically asked for weekly). Computed entirely from the weekly OHLCV DataFrame Etapa 1 already downloads — no extra network call.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_indicators.py
from weinstein_screener.indicators import relative_volume


def test_relative_volume_computes_recent_vs_baseline_ratio():
    # 20 baseline weeks at volume 1,000,000, then 3 recent weeks at 2,000,000
    # each -> relative_volume should be exactly 2.0
    rows = [{"Volume": 1_000_000} for _ in range(20)] + [{"Volume": 2_000_000} for _ in range(3)]
    df = pd.DataFrame(rows, index=pd.date_range("2020-01-06", periods=len(rows), freq="W-MON"))

    result = relative_volume(df, recent_weeks=3, baseline_weeks=20)

    assert result == pytest.approx(2.0)


def test_relative_volume_returns_none_with_insufficient_history():
    rows = [{"Volume": 1_000_000} for _ in range(10)]  # needs 3 + 20 = 23
    df = pd.DataFrame(rows, index=pd.date_range("2020-01-06", periods=len(rows), freq="W-MON"))

    result = relative_volume(df, recent_weeks=3, baseline_weeks=20)

    assert result is None


def test_relative_volume_returns_none_when_baseline_mean_is_zero():
    rows = [{"Volume": 0} for _ in range(20)] + [{"Volume": 500_000} for _ in range(3)]
    df = pd.DataFrame(rows, index=pd.date_range("2020-01-06", periods=len(rows), freq="W-MON"))

    result = relative_volume(df, recent_weeks=3, baseline_weeks=20)

    assert result is None


def test_relative_volume_uses_only_the_immediately_preceding_baseline_window():
    # An old spike far outside the 20-week baseline window must NOT affect
    # the result -- only the 20 weeks immediately before the 3 recent ones count.
    rows = (
        [{"Volume": 9_000_000}]  # old spike, outside the baseline window
        + [{"Volume": 1_000_000} for _ in range(20)]  # baseline window
        + [{"Volume": 1_000_000} for _ in range(3)]  # recent window, matches baseline
    )
    df = pd.DataFrame(rows, index=pd.date_range("2020-01-06", periods=len(rows), freq="W-MON"))

    result = relative_volume(df, recent_weeks=3, baseline_weeks=20)

    assert result == pytest.approx(1.0)
```

(`pytest` and `pandas as pd` are already imported at the top of `tests/test_indicators.py` — reuse them, do not re-import.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_indicators.py -v -k relative_volume`
Expected: FAIL with `ImportError: cannot import name 'relative_volume'`

- [ ] **Step 3: Write the implementation**

```python
# append to weinstein_screener/indicators.py
def relative_volume(df_weekly: pd.DataFrame, recent_weeks: int = 3, baseline_weeks: int = 20) -> float | None:
    """Volumen medio de las últimas `recent_weeks` semanas cerradas ÷ volumen
    medio de las `baseline_weeks` semanas inmediatamente anteriores a esas.

    Un valor alto sugiere actividad reciente por encima de lo habitual en
    ese valor (posible interés institucional) -- se compara contra una
    media de varias semanas, no una sola vela, para no reaccionar a ruido
    de una única semana atípica.

    None si no hay histórico suficiente, o si la media de la ventana base
    es cero (evita división por cero / ratio sin sentido).
    """
    total_needed = recent_weeks + baseline_weeks
    if len(df_weekly) < total_needed:
        return None

    volumes = df_weekly["Volume"]
    recent = volumes.iloc[-recent_weeks:]
    baseline = volumes.iloc[-total_needed:-recent_weeks]

    baseline_mean = baseline.mean()
    if baseline_mean == 0:
        return None

    return float(recent.mean() / baseline_mean)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_indicators.py -v -k relative_volume`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (127 pre-existing + 4 new = 131)

- [ ] **Step 6: Commit**

```bash
git add weinstein_screener/indicators.py tests/test_indicators.py
git commit -m "feat: add relative_volume (recent vs baseline weekly volume ratio)"
```

---

## Task 3: "Recorrido avanzado" warning (`weinstein_screener/management.py`)

**Files:**
- Modify: `weinstein_screener/management.py` (add one dataclass + one function at the end of the file — do not touch `Entry2Signal`, `find_entry_2_signal`, `ManagementAlert`, `evaluate_position_management`, `project_range_target`, `ExitSignal`, or `evaluate_exit_signal`)
- Test: `tests/test_management.py` (add new test functions)

**Interfaces:**
- Consumes: the `float | None` returned by the EXISTING `project_range_target(entry_price, range_high, range_low) -> float | None` (do not reimplement its logic).
- Produces: `ExtendedMoveWarning` dataclass (`progress_pct: float | None`, `is_extended: bool`) and `evaluate_extended_move(current_close: float, entry_price: float, range_target: float | None, threshold: float = 0.5) -> ExtendedMoveWarning`, consumed by Task 7 (the Streamlit app).

Formula, decided explicitly with the user: `progreso = (precio_actual - precio_entrada_JAC) / (objetivo_proyectado - precio_entrada_JAC)`. Verified against the mockup's worked example: `entry_price=212, range_target=245, current_close=231` → `progress = (231-212)/(245-212) = 19/33 ≈ 0.576` (58%), `is_extended=True` at the default 0.5 threshold.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_management.py
from weinstein_screener.management import ExtendedMoveWarning, evaluate_extended_move


def test_evaluate_extended_move_matches_the_worked_mockup_example():
    result = evaluate_extended_move(current_close=231.0, entry_price=212.0, range_target=245.0)

    assert result.progress_pct == pytest.approx(19 / 33)
    assert result.is_extended is True


def test_evaluate_extended_move_is_not_extended_below_threshold():
    result = evaluate_extended_move(current_close=215.0, entry_price=212.0, range_target=245.0)

    assert result.progress_pct == pytest.approx(3 / 33)
    assert result.is_extended is False


def test_evaluate_extended_move_boundary_at_exactly_the_threshold_is_extended():
    # entry=200, target=300 -> progress exactly 0.5 at current_close=250
    result = evaluate_extended_move(current_close=250.0, entry_price=200.0, range_target=300.0, threshold=0.5)

    assert result.progress_pct == pytest.approx(0.5)
    assert result.is_extended is True


def test_evaluate_extended_move_handles_a_missing_range_target():
    result = evaluate_extended_move(current_close=231.0, entry_price=212.0, range_target=None)

    assert result.progress_pct is None
    assert result.is_extended is False


def test_evaluate_extended_move_guards_a_target_at_or_below_entry():
    # defensive guard: a target that isn't strictly above entry can't yield
    # a meaningful progress ratio (would divide by zero or go negative)
    result = evaluate_extended_move(current_close=231.0, entry_price=212.0, range_target=212.0)

    assert result.progress_pct is None
    assert result.is_extended is False


def test_evaluate_extended_move_composes_with_project_range_target_end_to_end():
    # end-to-end with the real function this task must reuse, not reimplement
    from weinstein_screener.management import project_range_target

    target = project_range_target(entry_price=212.0, range_high=205.0, range_low=172.0)
    result = evaluate_extended_move(current_close=231.0, entry_price=212.0, range_target=target)

    assert target == pytest.approx(245.0)
    assert result.is_extended is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_management.py -v -k extended_move`
Expected: FAIL with `ImportError: cannot import name 'ExtendedMoveWarning'`

- [ ] **Step 3: Write the implementation**

```python
# append to weinstein_screener/management.py
@dataclass
class ExtendedMoveWarning:
    progress_pct: float | None
    is_extended: bool


def evaluate_extended_move(
    current_close: float,
    entry_price: float,
    range_target: float | None,
    threshold: float = 0.5,
) -> ExtendedMoveWarning:
    """Progreso hacia el objetivo proyectado desde la entrada del JAC:
    (precio_actual - precio_entrada) / (objetivo - precio_entrada).

    `is_extended=True` cuando el progreso ya alcanza `threshold` (0.5 por
    defecto -- a validar en backtest, igual que el resto de umbrales del
    proyecto): el ratio riesgo/beneficio de una entrada nueva a partir de
    ahí es pobre, así que se avisa en el detalle del ticker (no se filtra
    en la lista de Etapa 1 -- eso exigiría la Etapa 2 completa para los
    943 candidatos, justo lo que la arquitectura bajo demanda evita).

    None/False si `range_target` es None (`project_range_target` lo
    devuelve así con un rango inconsistente) o si el objetivo no queda
    estrictamente por encima del precio de entrada.
    """
    if range_target is None or range_target <= entry_price:
        return ExtendedMoveWarning(progress_pct=None, is_extended=False)

    progress = (current_close - entry_price) / (range_target - entry_price)
    return ExtendedMoveWarning(progress_pct=float(progress), is_extended=progress >= threshold)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_management.py -v -k extended_move`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (131 pre-existing + 6 new = 137)

- [ ] **Step 6: Commit**

```bash
git add weinstein_screener/management.py tests/test_management.py
git commit -m "feat: add evaluate_extended_move (recorrido avanzado warning)"
```

---

## Task 4: Chart data assembly (`weinstein_screener/chart_data.py`)

**Files:**
- Create: `weinstein_screener/chart_data.py`
- Test: `tests/test_chart_data.py`

**Interfaces:**
- Consumes: `moving_average` from `weinstein_screener/indicators.py` (already implemented — do not recompute a moving average by hand).
- Produces: `ChartMarker` dataclass (`date: pd.Timestamp`, `label: str`, `price: float`), `ChartData` dataclass (`df_visible: pd.DataFrame`, `ma: pd.Series`, `markers: list[ChartMarker]`, `range_low: float`, `range_high: float`, `range_target: float | None`), and `build_chart_data(df_weekly_full, marker_dates, range_low, range_high, range_target, visible_weeks=32, ma_window=30) -> ChartData`, consumed by Task 6 (`weinstein_screener/rendering.py`) and Task 7 (the Streamlit app).

**Design decision, made explicit here rather than left implicit**: this module does NOT take a `WyckoffStructure` or a `BuecResult` directly, and does NOT know about `wyckoff.py`'s or `ict.py`'s positional-index conventions. It takes a plain `dict[str, pd.Timestamp | None]` of marker dates instead (`{"SC": ts, "AR": ts, "ST": ts, "Spring": ts_or_None, "JAC": ts_or_None, "BUEC": ts_or_None}`). The caller (Task 7) is responsible for converting `structure.sc_index` etc. into dates using whichever DataFrame `detect_wyckoff_structure` actually ran on — this module stays decoupled from that indexing scheme entirely, and is fully testable with a synthetic DataFrame and plain dates, no dependency on `wyckoff.py`/`ict.py` at all.

**Spec requirement being implemented** (`docs/superpowers/specs/2026-08-12-plan6-dashboard-design.md`, §4.1): the moving average must be computed using AT LEAST `visible_weeks + ma_window` weeks of history so it is fully defined across the entire visible window — this is why `build_chart_data` takes `df_weekly_full` (the full fetched history) separately from what ends up in `df_visible` (the trimmed display window), and computes the MA on the full series before trimming.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_chart_data.py
import pandas as pd
import pytest

from weinstein_screener.chart_data import ChartData, ChartMarker, build_chart_data
from weinstein_screener.indicators import moving_average


def _weekly_df(n, start_price=100.0):
    dates = pd.date_range("2020-01-06", periods=n, freq="W-MON")
    rows = []
    price = start_price
    for i in range(n):
        price += 1.0
        rows.append({"Open": price - 0.5, "High": price + 1.0, "Low": price - 1.5, "Close": price, "Volume": 1_000_000})
    return pd.DataFrame(rows, index=dates)


def test_build_chart_data_trims_to_the_visible_window():
    df = _weekly_df(70)

    result = build_chart_data(
        df, marker_dates={}, range_low=90.0, range_high=140.0, range_target=None,
        visible_weeks=32, ma_window=30,
    )

    assert len(result.df_visible) == 32
    assert result.df_visible.index[-1] == df.index[-1]
    assert result.df_visible.index[0] == df.index[-32]


def test_build_chart_data_ma_is_fully_defined_across_the_visible_window_with_enough_lookback():
    # 32 visible + 30 lookback = 62 rows minimum for the MA to be fully
    # defined at every point of the visible window
    df = _weekly_df(62)

    result = build_chart_data(
        df, marker_dates={}, range_low=90.0, range_high=140.0, range_target=None,
        visible_weeks=32, ma_window=30,
    )

    assert result.ma.notna().all()
    assert len(result.ma) == 32


def test_build_chart_data_ma_has_leading_nans_with_insufficient_lookback():
    # only 40 rows total: the first (40 - 30) = 10 visible weeks can't have
    # a fully-defined 30-week MA yet -- this documents the real risk the
    # spec calls out, it must not be silently hidden
    df = _weekly_df(40)

    result = build_chart_data(
        df, marker_dates={}, range_low=90.0, range_high=140.0, range_target=None,
        visible_weeks=32, ma_window=30,
    )

    assert result.ma.iloc[:8].isna().all()
    assert result.ma.iloc[-1:].notna().all()


def test_build_chart_data_ma_values_match_moving_average_directly():
    df = _weekly_df(62)
    expected = moving_average(df, window=30).iloc[-32:]

    result = build_chart_data(
        df, marker_dates={}, range_low=90.0, range_high=140.0, range_target=None,
        visible_weeks=32, ma_window=30,
    )

    pd.testing.assert_series_equal(result.ma, expected, check_names=False)


def test_build_chart_data_maps_each_marker_label_to_its_correct_price_field():
    df = _weekly_df(40)
    sc_date, ar_date, jac_date = df.index[10], df.index[15], df.index[20]

    result = build_chart_data(
        df,
        marker_dates={"SC": sc_date, "AR": ar_date, "JAC": jac_date},
        range_low=90.0, range_high=140.0, range_target=None,
        visible_weeks=32, ma_window=30,
    )

    by_label = {m.label: m for m in result.markers}
    assert by_label["SC"].price == pytest.approx(df.loc[sc_date, "Low"])
    assert by_label["AR"].price == pytest.approx(df.loc[ar_date, "High"])
    assert by_label["JAC"].price == pytest.approx(df.loc[jac_date, "Close"])


def test_build_chart_data_excludes_none_marker_dates():
    df = _weekly_df(40)

    result = build_chart_data(
        df,
        marker_dates={"SC": df.index[10], "Spring": None, "JAC": None},
        range_low=90.0, range_high=140.0, range_target=None,
        visible_weeks=32, ma_window=30,
    )

    labels = {m.label for m in result.markers}
    assert labels == {"SC"}


def test_build_chart_data_excludes_a_marker_date_outside_the_dataframe():
    df = _weekly_df(40)
    outside_date = pd.Timestamp("1999-01-01")

    result = build_chart_data(
        df,
        marker_dates={"SC": outside_date},
        range_low=90.0, range_high=140.0, range_target=None,
        visible_weeks=32, ma_window=30,
    )

    assert result.markers == []


def test_build_chart_data_carries_range_and_target_through_unchanged():
    df = _weekly_df(40)

    result = build_chart_data(
        df, marker_dates={}, range_low=172.0, range_high=205.0, range_target=245.0,
        visible_weeks=32, ma_window=30,
    )

    assert result.range_low == 172.0
    assert result.range_high == 205.0
    assert result.range_target == 245.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_chart_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'weinstein_screener.chart_data'`

- [ ] **Step 3: Write the implementation**

```python
# weinstein_screener/chart_data.py
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from weinstein_screener.indicators import moving_average

_MARKER_PRICE_FIELD = {
    "SC": "Low",
    "AR": "High",
    "ST": "Low",
    "Spring": "Low",
    "JAC": "Close",
    "BUEC": "Low",
}


@dataclass
class ChartMarker:
    date: pd.Timestamp
    label: str
    price: float


@dataclass
class ChartData:
    df_visible: pd.DataFrame
    ma: pd.Series
    markers: list[ChartMarker]
    range_low: float
    range_high: float
    range_target: float | None


def build_chart_data(
    df_weekly_full: pd.DataFrame,
    marker_dates: dict[str, pd.Timestamp | None],
    range_low: float,
    range_high: float,
    range_target: float | None,
    visible_weeks: int = 32,
    ma_window: int = 30,
) -> ChartData:
    """Ensambla los datos listos para pintar el gráfico anotado de un ticker.

    `df_weekly_full` debe traer AL MENOS `visible_weeks + ma_window`
    semanas de histórico -- la MA se calcula sobre toda esa serie antes de
    recortar, para que esté bien definida en toda la ventana visible (ver
    spec, sección 4.1). Si trae menos, la MA sale con NaN al principio del
    tramo visible -- comportamiento honesto de `rolling()`, no se oculta.

    `marker_dates` no depende de los índices posicionales internos de
    `wyckoff.py`/`ict.py` a propósito -- el llamador convierte
    `structure.sc_index` etc. a fechas antes de invocar esta función, así
    este módulo no necesita conocer esas convenciones de indexado.
    """
    ma_full = moving_average(df_weekly_full, window=ma_window)
    df_visible = df_weekly_full.iloc[-visible_weeks:]
    ma_visible = ma_full.reindex(df_visible.index)

    markers: list[ChartMarker] = []
    for label, date in marker_dates.items():
        if date is None or date not in df_weekly_full.index:
            continue
        field = _MARKER_PRICE_FIELD[label]
        price = float(df_weekly_full.loc[date, field])
        markers.append(ChartMarker(date=date, label=label, price=price))

    return ChartData(
        df_visible=df_visible,
        ma=ma_visible,
        markers=markers,
        range_low=range_low,
        range_high=range_high,
        range_target=range_target,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_chart_data.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (137 pre-existing + 8 new = 145)

- [ ] **Step 6: Commit**

```bash
git add weinstein_screener/chart_data.py tests/test_chart_data.py
git commit -m "feat: add build_chart_data (candles/MA/markers assembly for the chart)"
```

---

## Task 5: Shortlist enrichment script (`scripts/enrich_shortlist.py`)

**Files:**
- Create: `scripts/enrich_shortlist.py`
- Test: `tests/test_enrich_shortlist.py` (tests the pure CSV read/write and row-building helpers only — not the network-touching `main()`, same split as `scripts/run_etapa1.py`)

**Interfaces:**
- Consumes: `fetch_fundamentals_for_candidates` (Task 1), `relative_volume` (Task 2), `get_cached_ohlcv` from `weinstein_screener/data.py` (already implemented — signature: `get_cached_ohlcv(ticker: str, interval: str, cache_dir: Path, period: str = "10y", max_age_days: int = 1, downloader=None) -> pd.DataFrame`), and the plain shortlist CSV written by `scripts/run_etapa1.py` (Plan 5) with columns `ticker,distance_pct,ma_rising`.
- Produces: an enriched CSV (default `data_cache/etapa1_shortlist_enriched.csv`) with columns `ticker,distance_pct,ma_rising,sector,market_cap,trailing_pe,ev_to_fcf,relative_volume` — consumed by Task 7 (the Streamlit app's Screener Filtrado screen).

**Design decision, explicit per the spec (§3.1)**: this enrichment runs **only over the Etapa 1 shortlist** (943 tickers, not the ~5395-ticker universe), and is a **separate step from `run_etapa1_screen`**, run right after it (same weekly cadence) — never triggered live from the dashboard. `get_info()`'s per-ticker cost (~9-10 min for 943 tickers) makes it unsuitable for anything triggered by a page load.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_enrich_shortlist.py
import csv
import io

import pandas as pd
import pytest

from scripts.enrich_shortlist import build_enriched_rows, read_shortlist_csv


def test_read_shortlist_csv_parses_ticker_distance_and_ma_rising():
    csv_text = "ticker,distance_pct,ma_rising\nWM,0.0484,True\nAAPL,3.5,True\n"

    result = read_shortlist_csv(io.StringIO(csv_text))

    assert result == [
        {"ticker": "WM", "distance_pct": 0.0484, "ma_rising": True},
        {"ticker": "AAPL", "distance_pct": 3.5, "ma_rising": True},
    ]


def test_build_enriched_rows_merges_fundamentals_and_relative_volume():
    from weinstein_screener.fundamentals import TickerFundamentals

    shortlist_rows = [{"ticker": "WM", "distance_pct": 0.0484, "ma_rising": True}]
    fundamentals_by_ticker = {
        "WM": TickerFundamentals(
            ticker="WM", sector="Industrials", market_cap=9.08e10, trailing_pe=59.9, ev_to_fcf=48.3
        )
    }
    relative_volume_by_ticker = {"WM": 1.9}

    result = build_enriched_rows(shortlist_rows, fundamentals_by_ticker, relative_volume_by_ticker)

    assert result == [
        {
            "ticker": "WM",
            "distance_pct": 0.0484,
            "ma_rising": True,
            "sector": "Industrials",
            "market_cap": 9.08e10,
            "trailing_pe": 59.9,
            "ev_to_fcf": 48.3,
            "relative_volume": 1.9,
        }
    ]


def test_build_enriched_rows_fills_missing_ticker_data_with_none():
    # a ticker present in the shortlist but missing from both lookup dicts
    # (e.g. its OHLCV fetch or fundamentals fetch failed) must not crash
    # the whole enrichment -- it gets None fields, not a KeyError
    shortlist_rows = [{"ticker": "MISSING", "distance_pct": 1.0, "ma_rising": True}]

    result = build_enriched_rows(shortlist_rows, fundamentals_by_ticker={}, relative_volume_by_ticker={})

    assert result == [
        {
            "ticker": "MISSING",
            "distance_pct": 1.0,
            "ma_rising": True,
            "sector": None,
            "market_cap": None,
            "trailing_pe": None,
            "ev_to_fcf": None,
            "relative_volume": None,
        }
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_enrich_shortlist.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.enrich_shortlist'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/enrich_shortlist.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_enrich_shortlist.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (145 pre-existing + 3 new = 148)

- [ ] **Step 6: Manual smoke test against a small real slice** (same pattern as `scripts/run_etapa1.py`'s Task 5 in Plan 5 — this script's `main()` touches the real network, verify it end-to-end by hand, not with a mocked unit test)

```bash
# Build a tiny 5-row shortlist CSV by hand, run the real script against it,
# inspect the output.
mkdir -p /tmp/enrich-smoke
printf 'ticker,distance_pct,ma_rising\nAAPL,3.5,True\nWM,0.05,True\n' > /tmp/enrich-smoke/shortlist.csv
.venv/bin/python scripts/enrich_shortlist.py --input /tmp/enrich-smoke/shortlist.csv --output /tmp/enrich-smoke/enriched.csv --cache-dir /tmp/enrich-smoke/ohlcv_cache
cat /tmp/enrich-smoke/enriched.csv
```

Expected: a CSV with the 8 enriched columns, real sector/market_cap/trailing_pe/ev_to_fcf/relative_volume values for AAPL and WM (not blank/None, given both are large, well-covered tickers).

- [ ] **Step 7: Commit**

```bash
git add scripts/enrich_shortlist.py tests/test_enrich_shortlist.py
git commit -m "feat: add shortlist enrichment script (fundamentals + relative volume)"
```

---

## Task 6: Chart rendering (`weinstein_screener/rendering.py`)

**Files:**
- Create: `weinstein_screener/rendering.py`
- Test: `tests/test_rendering.py`
- Modify: `requirements.txt` (add `altair>=5.0,<6.0` — already installed transitively via `streamlit`, but this module imports it directly, so it must be declared explicitly, not relied upon as a transitive dependency)

**Interfaces:**
- Consumes: `ChartData`/`ChartMarker` from `weinstein_screener/chart_data.py` (Task 4).
- Produces: `render_price_chart(chart_data: ChartData) -> alt.VConcatChart`, consumed by Task 7 (the Streamlit app, via `st.altair_chart`).

Verified in this environment: Altair 5.5.0 (bundled with Streamlit 1.50) supports layered charts via `mark_rule` (wicks) + `mark_bar`/`mark_rect` (bodies) + `mark_line` (MA) — confirmed working with a synthetic OHLC frame before writing this task.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rendering.py
import altair as alt
import pandas as pd

from weinstein_screener.chart_data import ChartData, ChartMarker
from weinstein_screener.rendering import render_price_chart


def _sample_chart_data():
    dates = pd.date_range("2024-01-01", periods=10, freq="W-MON")
    df = pd.DataFrame(
        {
            "Open": [100 + i for i in range(10)],
            "High": [102 + i for i in range(10)],
            "Low": [98 + i for i in range(10)],
            "Close": [101 + i for i in range(10)],
            "Volume": [1_000_000] * 10,
        },
        index=dates,
    )
    ma = pd.Series([99 + i for i in range(10)], index=dates)
    markers = [ChartMarker(date=dates[3], label="SC", price=98.0)]
    return ChartData(df_visible=df, ma=ma, markers=markers, range_low=95.0, range_high=115.0, range_target=120.0)


def test_render_price_chart_returns_a_vconcat_of_price_and_volume_panels():
    # price (candles+MA+range+markers+target) and volume are SEPARATE
    # stacked panels (vconcat), not layered into the same plot area with an
    # independent scale -- overlaying them in one area would visually
    # collide candle bodies with volume bars in the same pixels.
    result = render_price_chart(_sample_chart_data())

    assert isinstance(result, alt.VConcatChart)
    assert len(result.vconcat) == 2


def test_render_price_chart_does_not_raise_with_no_markers_and_no_target():
    chart_data = _sample_chart_data()
    chart_data.markers = []
    chart_data.range_target = None

    result = render_price_chart(chart_data)  # must not raise

    assert isinstance(result, alt.VConcatChart)


def test_render_price_chart_price_panel_includes_a_layer_per_visual_element():
    # candle wicks, candle bodies, MA line, range band = at least 4 layers
    # in the price panel before markers/target lines are even added
    result = render_price_chart(_sample_chart_data())
    price_panel = result.vconcat[0]

    assert len(price_panel.layer) >= 4


def test_render_price_chart_price_axis_is_on_the_right():
    # matches the mockup's layout (price scale on the right edge, like a
    # real trading terminal). Altair's `.axis` attribute on an encoding
    # object is a `_PropertySetter`, not a plain accessor (verified in this
    # environment) -- inspect the serialized spec via `.to_dict()` instead
    # of attribute access, which is the reliable way to assert on it.
    result = render_price_chart(_sample_chart_data())
    price_panel_dict = result.vconcat[0].to_dict()
    wicks_layer_dict = price_panel_dict["layer"][1]  # range_band, wicks, bodies, ma_line -- wicks is index 1

    assert wicks_layer_dict["encoding"]["y"]["axis"]["orient"] == "right"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_rendering.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'weinstein_screener.rendering'`

- [ ] **Step 3: Write the implementation**

```python
# weinstein_screener/rendering.py
from __future__ import annotations

import altair as alt
import pandas as pd

from weinstein_screener.chart_data import ChartData

_UP_COLOR = "#2f9155"
_DOWN_COLOR = "#c14b56"


def _colored(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Direction"] = df.apply(lambda r: "up" if r["Close"] >= r["Open"] else "down", axis=1)
    return df


def render_price_chart(chart_data: ChartData) -> alt.VConcatChart:
    """Gráfico de velas semanales + MA + anotaciones de estructura Wyckoff
    (panel de precio) apilado sobre un panel de volumen SEPARADO, a partir
    de un `ChartData` ya ensamblado
    (`weinstein_screener.chart_data.build_chart_data`). Esta función es
    solo de renderizado -- no calcula nada, todos los datos ya vienen
    resueltos en `chart_data`.

    Precio y volumen son paneles apilados (`alt.vconcat`), NO capas
    superpuestas en la misma área de dibujo con escala independiente --
    superponerlos así colisionaría visualmente velas y barras de volumen
    en los mismos píxeles. Solo comparten el eje X (fechas).

    El eje de precios va a la derecha (`axis=alt.Axis(orient="right")`),
    igual que en el mockup -- se fija en cada capa de precio individual
    (no basta con fijarlo en una sola capa de un `layer()`, cada capa
    declara su propia codificación de eje).
    """
    df = _colored(chart_data.df_visible.reset_index(names="Date"))
    color_scale = alt.Scale(domain=["up", "down"], range=[_UP_COLOR, _DOWN_COLOR])

    range_band = (
        alt.Chart(pd.DataFrame({"low": [chart_data.range_low], "high": [chart_data.range_high]}))
        .mark_rect(opacity=0.12, color="#1c7c72")
        .encode(y=alt.Y("low:Q", axis=alt.Axis(orient="right", title="Precio")), y2="high:Q")
    )
    wicks = alt.Chart(df).mark_rule().encode(
        x="Date:T", y=alt.Y("Low:Q", axis=alt.Axis(orient="right")), y2="High:Q",
        color=alt.Color("Direction:N", scale=color_scale, legend=None),
    )
    bodies = alt.Chart(df).mark_bar(size=6).encode(
        x="Date:T", y=alt.Y("Open:Q", axis=alt.Axis(orient="right")), y2="Close:Q",
        color=alt.Color("Direction:N", scale=color_scale, legend=None),
    )

    ma_df = chart_data.ma.reset_index()
    ma_df.columns = ["Date", "MA"]
    ma_line = alt.Chart(ma_df).mark_line(color="#4c6f96").encode(
        x="Date:T", y=alt.Y("MA:Q", axis=alt.Axis(orient="right"))
    )

    price_layers = [range_band, wicks, bodies, ma_line]

    if chart_data.markers:
        markers_df = pd.DataFrame(
            {
                "Date": [m.date for m in chart_data.markers],
                "price": [m.price for m in chart_data.markers],
                "label": [m.label for m in chart_data.markers],
            }
        )
        marker_points = alt.Chart(markers_df).mark_point(filled=True, size=60, color="#b3811a").encode(
            x="Date:T", y=alt.Y("price:Q", axis=alt.Axis(orient="right"))
        )
        marker_labels = alt.Chart(markers_df).mark_text(dy=-10, color="#b3811a").encode(
            x="Date:T", y=alt.Y("price:Q", axis=alt.Axis(orient="right")), text="label:N"
        )
        price_layers += [marker_points, marker_labels]

    if chart_data.range_target is not None:
        target_df = pd.DataFrame({"target": [chart_data.range_target]})
        target_line = alt.Chart(target_df).mark_rule(strokeDash=[6, 4], color="#0f5d55").encode(
            y=alt.Y("target:Q", axis=alt.Axis(orient="right"))
        )
        price_layers.append(target_line)

    price_chart = alt.layer(*price_layers).properties(height=300)

    volume_chart = alt.Chart(df).mark_bar(opacity=0.5).encode(
        x="Date:T", y=alt.Y("Volume:Q", axis=alt.Axis(orient="right", title="Volumen")),
        color=alt.Color("Direction:N", scale=color_scale, legend=None),
    ).properties(height=100)

    return alt.vconcat(price_chart, volume_chart).resolve_scale(x="shared")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_rendering.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (148 pre-existing + 4 new = 152)

- [ ] **Step 6: Commit**

```bash
git add weinstein_screener/rendering.py tests/test_rendering.py requirements.txt
git commit -m "feat: add altair-based price chart rendering"
```

---

## Task 7: Streamlit app (`scripts/dashboard_app.py`)

**Files:**
- Create: `scripts/dashboard_app.py`
- Modify: `requirements.txt` (add `streamlit>=1.38,<1.51` — verified installed and working in this environment as 1.50.0)

**Interfaces:**
- Consumes: everything built in Tasks 1-6, plus the already-existing `weinstein_screener.data.get_cached_ohlcv`, `weinstein_screener.wyckoff.detect_wyckoff_structure`, `weinstein_screener.indicators.average_true_range`, `weinstein_screener.ict.find_entry_1_signal`, `weinstein_screener.ict.find_entry_3_signal`, `weinstein_screener.management.find_entry_2_signal`, `weinstein_screener.management.evaluate_position_management`, `weinstein_screener.management.project_range_target`, `weinstein_screener.management.evaluate_exit_signal`, `weinstein_screener.regime.weinstein_stage2_active`.
- Produces: nothing consumed by other tasks — this is the final integration point.

This task has no automated tests (Streamlit apps run as scripts, not as importable pytest-testable units, and this project has no Streamlit test harness — same situation `scripts/run_etapa1.py` was in for Plan 5). Verify with the manual smoke test in Step 2.

- [ ] **Step 1: Write the app**

```python
# scripts/dashboard_app.py
"""Dashboard Streamlit del weinstein_screener -- pantallas 'Screener
Filtrado' y 'Detalle de ticker'. Solo alertas, nunca ejecuta operaciones.

Uso:
    .venv/bin/streamlit run scripts/dashboard_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from weinstein_screener.chart_data import build_chart_data
from weinstein_screener.data import get_cached_ohlcv
from weinstein_screener.ict import find_entry_1_signal, find_entry_3_signal
from weinstein_screener.indicators import average_true_range
from weinstein_screener.management import (
    evaluate_exit_signal,
    evaluate_extended_move,
    evaluate_position_management,
    find_entry_2_signal,
    project_range_target,
)
from weinstein_screener.regime import weinstein_stage2_active
from weinstein_screener.rendering import render_price_chart
from weinstein_screener.wyckoff import detect_wyckoff_structure

ENRICHED_SHORTLIST_PATH = Path("data_cache/etapa1_shortlist_enriched.csv")
OHLCV_CACHE_DIR = Path("data_cache/ohlcv")
VISIBLE_WEEKS = 32
MA_WINDOW = 30


@st.cache_data(ttl=3600)
def load_shortlist() -> pd.DataFrame:
    return pd.read_csv(ENRICHED_SHORTLIST_PATH)


@st.cache_data(ttl=3600)
def load_weekly(ticker: str, min_weeks: int) -> pd.DataFrame:
    # `period="5y"` comfortably covers VISIBLE_WEEKS + MA_WINDOW (62 weeks
    # ~= 1.2 years) plus the longer Wyckoff structure lookback in
    # `detect_wyckoff_structure` (up to sc_search_window=52 weeks back from
    # the ST) -- verified against both defaults, not guessed.
    return get_cached_ohlcv(ticker, interval="1wk", cache_dir=OHLCV_CACHE_DIR, period="5y")


@st.cache_data(ttl=3600)
def load_daily(ticker: str) -> pd.DataFrame:
    return get_cached_ohlcv(ticker, interval="1d", cache_dir=OHLCV_CACHE_DIR, period="2y")


def _week_containing(df_weekly: pd.DataFrame, daily_date) -> pd.Timestamp | None:
    """Mapea una fecha DIARIA a la fecha de la vela SEMANAL (índice W-MON)
    que la contiene -- `DatetimeIndex.asof` devuelve la mayor fecha del
    índice <= `daily_date`, que para un índice semanal de inicio-lunes cae
    exactamente en el lunes de esa semana (verificado). Usado para colocar
    el marcador de BUEC en el gráfico semanal, aunque `find_entry_3_signal`
    lo detecta sobre velas diarias -- ver nota de alcance en el spec,
    sección 4.1: es una referencia visual aproximada, no la vela exacta.
    """
    candidate = df_weekly.index.asof(daily_date)
    if pd.isna(candidate):
        return None
    return candidate


def _marker_dates(df_weekly: pd.DataFrame, df_daily: pd.DataFrame, structure, entry3) -> dict:
    buec_date = None
    if entry3 is not None:
        daily_buec_date = df_daily.index[entry3.trigger_index]
        buec_date = _week_containing(df_weekly, daily_buec_date)

    return {
        "SC": df_weekly.index[structure.sc_index],
        "AR": df_weekly.index[structure.ar_index],
        "ST": df_weekly.index[structure.st_index],
        "Spring": df_weekly.index[structure.spring_index] if structure.spring_index is not None else None,
        "JAC": df_weekly.index[structure.jac_index] if structure.jac_index is not None else None,
        "BUEC": buec_date,
    }


def render_screener_screen():
    st.subheader("Screener Filtrado")
    if not ENRICHED_SHORTLIST_PATH.exists():
        st.warning(
            f"No se encuentra {ENRICHED_SHORTLIST_PATH}. Ejecuta "
            "`scripts/run_etapa1.py` y luego `scripts/enrich_shortlist.py` primero."
        )
        return

    df = load_shortlist()
    st.caption(f"{len(df)} candidatos de Etapa 1")

    event = st.dataframe(
        df,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="shortlist_table",
    )

    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows:
        selected_ticker = df.iloc[selected_rows[0]]["ticker"]
        st.session_state["selected_ticker"] = selected_ticker
        st.session_state["screen"] = "detail"
        st.rerun()


def render_detail_screen():
    ticker = st.session_state.get("selected_ticker")
    if ticker is None:
        st.info("Selecciona un ticker en Screener Filtrado.")
        return

    if st.button("← volver a la lista"):
        st.session_state["screen"] = "screener"
        st.rerun()

    with st.spinner(f"Analizando estructura Wyckoff/CRT/ICT de {ticker} (bajo demanda)…"):
        df_weekly = load_weekly(ticker, VISIBLE_WEEKS + MA_WINDOW)
        df_daily = load_daily(ticker)
        structure = detect_wyckoff_structure(df_weekly)

    st.markdown(f"## {ticker}  `${df_weekly['Close'].iloc[-1]:.2f}`")

    if structure is None:
        st.info("No se detecta una estructura Wyckoff de acumulación vigente para este ticker ahora mismo.")
        return

    stage2 = weinstein_stage2_active(df_weekly).iloc[-1]
    st.markdown(f"**Stage 2 activo**: {'sí' if stage2 else 'no'}")

    atr_weekly = average_true_range(df_weekly)
    atr_daily = average_true_range(df_daily)

    entry2 = find_entry_2_signal(df_weekly, structure.jac_index, atr_weekly)

    # `structure.spring_index`/`structure.jac_index` are positions in df_weekly
    # (weekly bars) -- find_entry_1_signal/find_entry_3_signal need a position
    # in df_daily instead. Map the weekly event's date to the first daily bar
    # on/after it (`searchsorted` on a DatetimeIndex), verified against a
    # synthetic date range before writing this task. Passing the weekly
    # position directly here would silently search the wrong days entirely.
    entry1 = None
    if structure.spring_index is not None:
        spring_week_date = df_weekly.index[structure.spring_index]
        daily_search_start = int(df_daily.index.searchsorted(spring_week_date))
        entry1 = find_entry_1_signal(df_daily, structure.range_low, daily_search_start, atr_daily)

    entry3 = None
    if structure.jac_index is not None:
        jac_week_date = df_weekly.index[structure.jac_index]
        daily_breakout_index = int(df_daily.index.searchsorted(jac_week_date))
        entry3 = find_entry_3_signal(df_daily, structure.range_high, daily_breakout_index, atr_daily)

    target = None
    extended = None
    if entry2 is not None:
        target = project_range_target(entry2.entry_price, structure.range_high, structure.range_low)
        extended = evaluate_extended_move(df_weekly["Close"].iloc[-1], entry2.entry_price, target)

    if extended is not None and extended.is_extended:
        st.warning(
            f"Recorrido ya avanzado desde la ruptura: ha cubierto el "
            f"{extended.progress_pct:.0%} de la distancia hacia el objetivo proyectado "
            "— el ratio riesgo/beneficio de una entrada nueva aquí es pobre."
        )

    marker_dates = _marker_dates(df_weekly, df_daily, structure, entry3)
    chart_data = build_chart_data(
        df_weekly,
        marker_dates,
        range_low=structure.range_low,
        range_high=structure.range_high,
        range_target=target,
        visible_weeks=VISIBLE_WEEKS,
        ma_window=MA_WINDOW,
    )
    st.altair_chart(render_price_chart(chart_data), use_container_width=True)
    if marker_dates.get("BUEC") is not None:
        st.caption(
            "El marcador BUEC es una referencia semanal aproximada — Entrada 3 se evalúa sobre velas diarias, "
            "no sobre la vela semanal marcada."
        )

    cols = st.columns(3)
    for col, label, signal in zip(cols, ["Entrada 1 (Spring)", "Entrada 2 (JAC)", "Entrada 3 (BUEC)"], [entry1, entry2, entry3]):
        with col:
            st.markdown(f"**{label}**")
            if signal is None:
                st.markdown("_Sin señal_")
            else:
                st.markdown(f"Precio: `${signal.entry_price:.2f}`")
                st.markdown(f"Stop loss: `${signal.stop_loss:.2f}`")

    if entry2 is not None:
        # `entry1_stopped_out` is hardcoded False -- deciding whether a
        # triggered Entry 1 was actually later stopped out requires walking
        # the daily price path after `entry1.trigger_index` looking for a
        # touch of `entry1.stop_loss`, which no existing function in this
        # codebase computes. Out of scope for this task: it under-reports
        # the "Spring fallido" resize alert (never fires) rather than
        # over-reporting it, which is the safer direction for an
        # alerts-only tool. Documented here explicitly, not left as a
        # silent gap -- a follow-up task should add that check properly.
        management = evaluate_position_management(
            entry1_triggered=entry1 is not None,
            entry1_stopped_out=False,
            entry2_triggered=True,
        )
        if management.move_entry1_to_breakeven:
            st.info("Alerta: mover el stop de la Entrada 1 a breakeven.")

    if target is not None:
        exit_signal = evaluate_exit_signal(
            df_weekly["Close"].iloc[-1], target, bool(weinstein_stage2_active(df_weekly).iloc[-1])
        )
        st.markdown(f"**Objetivo proyectado**: `${target:.2f}`")
        if exit_signal.full_exit:
            st.error("Salida total: cierre semanal bajo la MA30w.")
        elif exit_signal.partial_take_profit:
            st.success("Toma de parcial: objetivo alcanzado.")


def main():
    st.set_page_config(page_title="Weinstein Screener", layout="wide")
    st.title("Panel de señales")

    if "screen" not in st.session_state:
        st.session_state["screen"] = "screener"

    tab_screener, tab_detail = st.tabs(["Screener Filtrado", "Detalle de ticker"])
    with tab_screener:
        render_screener_screen()
    with tab_detail:
        render_detail_screen()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Manual smoke test**

```bash
# Requires an enriched shortlist to exist first -- build a tiny one for the smoke test:
mkdir -p data_cache
printf 'ticker,distance_pct,ma_rising\nAAPL,3.5,True\nWM,0.05,True\n' > /tmp/mini_shortlist.csv
.venv/bin/python scripts/enrich_shortlist.py --input /tmp/mini_shortlist.csv --output data_cache/etapa1_shortlist_enriched.csv
.venv/bin/streamlit run scripts/dashboard_app.py
```

Expected, verified by hand in the browser Streamlit opens:
- "Screener Filtrado" tab shows a 2-row sortable table (AAPL, WM) with all 8 columns.
- Clicking a row switches to "Detalle de ticker" and shows a spinner, then the ticker's price, a Stage 2 indicator, the annotated chart (or "no se detecta estructura" if that real ticker doesn't have a current Wyckoff structure — both are valid, correct outcomes, do not force a specific result), the 3 entry cards, and the target/exit panel if an Entry 2 was found.
- No exceptions in the terminal Streamlit is running in.

- [ ] **Step 3: Commit**

```bash
git add scripts/dashboard_app.py requirements.txt
git commit -m "feat: add the two-screen Streamlit dashboard"
```

---

## Addendum (2026-08-13) — final whole-branch review findings

The final review (most capable model, real-data verification) found 1 Critical + 5 Important findings, all traced to this plan's own code, not implementer transcription error:

1. **(Critical) Entry 3's BUEC search window is anchored to the FIRST daily bar of the JAC week, not the last.** `daily_breakout_index = int(df_daily.index.searchsorted(jac_week_date))` lands on the JAC week's Monday — but the JAC is confirmed at that week's CLOSE, so `find_buec` ends up scanning days *during* the breakout (when price is naturally sitting near `ar_high`) instead of after it, producing a spurious Entry 3 entry price/stop. **Fix**: anchor to the last daily bar on/before `jac_week_date + 6 days` instead: `int(df_daily.index.searchsorted(jac_week_date + pd.Timedelta(days=7))) - 1`, clamped to `[0, len(df_daily)-1]`.
2. **(Important) The dashboard never drops the unclosed current week before evaluating Wyckoff/exit logic**, unlike `etapa1.py::_drop_unclosed_current_week`, which exists specifically to avoid this (verified: `weinstein_stage2_active`/`close_above_ma`/`detect_wyckoff_structure` all ran on a real in-progress weekly bar in live testing). **Fix**: export the helper (drop the leading underscore) from `etapa1.py`, call it once in `dashboard_app.py::load_weekly` to produce a `df_weekly_closed` used for ALL signal computations, keeping the raw (unclosed-week-included) `df_weekly` only for the live price display line.
3. **(Important) `relative_volume` in `enrich_shortlist.py` is fed the same unclosed week**, measurably deflating the ratio (~8% low on a Thursday in real testing, worse earlier in the week). **Fix**: same shared helper, applied before calling `relative_volume`.
4. **(Important) The back button leaves stale selection state, so re-selecting the SAME ticker after going back does nothing** (the equality guard from the Critical-loop fix sees no change). **Fix**: on the back-button handler, also clear the dataframe widget's own state (`st.session_state.pop("shortlist_table", None)`) in addition to `selected_ticker`/`screen` — NOT just clearing `selected_ticker` alone, which would reintroduce the infinite-rerun loop.
5. **(Important) Markers older than the visible 32-week window silently stretch the whole chart** (reproduced with a real SC 50 weeks back). **Fix**: filter `marker_dates` to only those falling within `df_visible`'s actual date range inside `build_chart_data`, before constructing `ChartMarker`s — simplest correct fix, no `rendering.py` change needed (the x-domain is inferred from what's actually plotted).
6. **(Important) The `entry1_stopped_out=False` code comment is wrong for the one alert path the UI actually shows** — it claims the hardcode only under-reports (safe direction), but the breakeven `st.info(...)` alert the user sees can over-report (fire when Entry 1 was actually stopped out). **Fix**: correct the comment, add a short caveat in the alert text itself.

Also fixed in the same wave (originally Minor, but safety-relevant and cheap): the master "salida total" exit alert was gated behind `if target is not None`, hiding the most important risk alert whenever `project_range_target` returns `None` — restructured so `evaluate_exit_signal`'s `full_exit` is always evaluated when Entry 2 exists, independent of whether a target could be computed.

Remaining Minor findings (screener table presentation polish — `—` for missing values, guaranteed last-sort, `relative_volume≥1.5` highlight pill, Spanish column headers; chart range-band shape not pinned to the SC→JAC x-span with dotted boundary lines; a few unused test imports; no progress output during `enrich_shortlist.py`'s ~10-minute run) are parked, not fixed in this branch — see the ledger for the explicit ruling on each.

## Task 8: Final whole-branch review + finish branch

- [ ] **Step 1: Run the full suite one more time**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (152 total: 121 pre-existing + 31 new across Tasks 1-6)

- [ ] **Step 2: Dispatch the final whole-branch code review**

Use `superpowers:subagent-driven-development`'s Final Review process (`scripts/review-package PLAN_FILE MERGE_BASE HEAD`, dispatch on the most capable available model using `superpowers:requesting-code-review`'s `code-reviewer.md` template). Pay particular attention to:
- Whether `scripts/dashboard_app.py` composes the existing pipeline functions with the CORRECT arguments (this task's implementer read the signatures directly from source before writing the plan, but the plan's own code block is still worth an independent check against the live source — signatures can drift between plan-writing and implementation).
- Whether any new module reimplements logic that already exists elsewhere in the pipeline instead of importing it.
- Whether the "bajo demanda" architecture boundary is respected (no task should compute Wyckoff structure for more than one ticker at a time inside the Streamlit app).

- [ ] **Step 3: Address findings, then use `superpowers:finishing-a-development-branch`** to merge to `main` (or open a PR, per whichever integration option is chosen at that time).
