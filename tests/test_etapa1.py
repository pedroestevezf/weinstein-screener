import pandas as pd
import pytest

import weinstein_screener.etapa1 as etapa1
from weinstein_screener.etapa1 import run_etapa1_screen, screen_ticker


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


def _rising_candidate_closes(n=40):
    # Sube de forma constante y termina cerca de la MA -> candidato.
    return [100.0 + i * 2 for i in range(n)]


def _flat_non_candidate_closes(n=40):
    # Precio plano -> MA plana -> pendiente no ascendente -> no candidato.
    return [100.0] * n


def _multiindex_batch_result(ticker_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Construye un DataFrame con columnas MultiIndex (nivel 0 = ticker),
    igual a lo que devuelve yfinance.download para varios tickers con
    group_by="ticker"."""
    frames = []
    for ticker, df in ticker_frames.items():
        renamed = df.copy()
        renamed.columns = pd.MultiIndex.from_product([[ticker], renamed.columns])
        frames.append(renamed)
    return pd.concat(frames, axis=1)


def test_screen_ticker_is_a_candidate_when_close_and_rising():
    closes = [100.0 + i * 2 for i in range(40)]
    df = _weekly_df(closes)

    result = screen_ticker("AAA", df, distance_pct_threshold=7.5, ma_window=10, slope_lookback=4)

    assert result is not None
    assert result.ma_rising is True
    assert result.distance_pct <= 7.5
    assert result.is_candidate is True


def test_screen_ticker_rejects_when_ma_is_not_rising():
    closes = [100.0] * 40  # precio plano -> MA plana -> pendiente no ascendente
    df = _weekly_df(closes)

    result = screen_ticker("BBB", df, distance_pct_threshold=7.5, ma_window=10, slope_lookback=4)

    assert result is not None
    assert result.ma_rising is False
    assert result.is_candidate is False


def test_screen_ticker_rejects_when_too_far_from_a_rising_ma():
    rising = [100.0 + i * 2 for i in range(19)]
    # Salto grande en la última semana para alejar el precio de la MA
    closes = rising + [400.0]
    df = _weekly_df(closes)

    result = screen_ticker("CCC", df, distance_pct_threshold=7.5, ma_window=10, slope_lookback=4)

    assert result is not None
    assert result.ma_rising is True
    assert result.distance_pct > 7.5
    assert result.is_candidate is False


def test_screen_ticker_returns_none_with_insufficient_history():
    closes = [100.0 + i for i in range(5)]
    df = _weekly_df(closes)

    result = screen_ticker("DDD", df, ma_window=30, slope_lookback=4)

    assert result is None


def test_screen_ticker_excludes_in_progress_current_week():
    # yf.download con interval="1wk" devuelve la semana en curso (parcial)
    # como última fila cuando se ejecuta a mitad de semana. screen_ticker
    # debe evaluar sobre la última semana CERRADA, no sobre esa fila.
    now = pd.Timestamp.now().normalize()
    this_monday = now - pd.Timedelta(days=now.weekday())
    dates = pd.date_range(end=this_monday, periods=41, freq="W-MON")
    # Las primeras 40 semanas suben de forma constante; la última (semana en
    # curso, todavía no cerrada) tiene un salto brutal que, si se incluyera,
    # cambiaría claramente distance_pct/ma_rising respecto a excluirla.
    closes = [100.0 + i * 2 for i in range(40)] + [5000.0]
    df = pd.DataFrame(
        {
            "Open": closes,
            "High": [c + 1 for c in closes],
            "Low": [c - 1 for c in closes],
            "Close": closes,
            "Volume": [1000] * len(closes),
        },
        index=dates,
    )

    result = screen_ticker("ZZZ", df, distance_pct_threshold=7.5, ma_window=10, slope_lookback=4)
    expected = screen_ticker(
        "ZZZ", df.iloc[:-1], distance_pct_threshold=7.5, ma_window=10, slope_lookback=4
    )

    assert result is not None
    assert expected is not None
    assert result.distance_pct == pytest.approx(expected.distance_pct)
    assert result.ma_rising == expected.ma_rising
    assert result.distance_pct < 1000  # sanity: el salto de la última fila no se usó


def test_screen_ticker_distance_pct_is_numerically_correct():
    # 9 semanas planas en 100 + última semana en 121 -> MA(10) = (9*100 + 121)/10 = 102.1
    # distance = |121 - 102.1| / 102.1 * 100
    closes = [100.0] * 9 + [121.0]
    df = _weekly_df(closes)

    result = screen_ticker("EEE", df, ma_window=10, slope_lookback=4, distance_pct_threshold=100)

    ma_last = (9 * 100.0 + 121.0) / 10
    expected_distance = abs(121.0 - ma_last) / ma_last * 100
    assert result is not None
    assert result.distance_pct == pytest.approx(expected_distance)


# ---------------------------------------------------------------------------
# run_etapa1_screen
# ---------------------------------------------------------------------------


def test_run_etapa1_screen_batches_and_combines_results_across_calls():
    tickers = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    closes = _rising_candidate_closes()
    calls = []

    def fake_downloader(chunk, period, interval):
        calls.append(list(chunk))
        assert interval == "1wk"
        frames = {t: _weekly_df(closes) for t in chunk}
        if len(chunk) == 1:
            return frames[chunk[0]]  # forma plana, sin MultiIndex
        return _multiindex_batch_result(frames)

    result = run_etapa1_screen(tickers, batch_size=2, ma_window=10, downloader=fake_downloader)

    # 5 tickers en lotes de 2 -> 3 llamadas: [2, 2, 1]
    assert len(calls) == 3
    assert calls[0] == ["AAA", "BBB"]
    assert calls[1] == ["CCC", "DDD"]
    assert calls[2] == ["EEE"]

    result_tickers = {c.ticker for c in result.candidates}
    assert result_tickers == set(tickers)
    assert result.tickers_attempted == 5
    assert result.tickers_screened == 5
    assert result.batches_failed == 0


def test_run_etapa1_screen_skips_ticker_missing_from_batch_result():
    closes = _rising_candidate_closes()

    def fake_downloader(chunk, period, interval):
        # "YYY" nunca aparece en la respuesta (deslistado / símbolo inválido)
        frames = {t: _weekly_df(closes) for t in chunk if t != "YYY"}
        return _multiindex_batch_result(frames)

    result = run_etapa1_screen(
        ["XXX", "YYY"], batch_size=2, ma_window=10, downloader=fake_downloader
    )

    result_tickers = {c.ticker for c in result.candidates}
    assert "YYY" not in result_tickers
    assert "XXX" in result_tickers
    assert result.tickers_attempted == 2
    assert result.tickers_screened == 1  # solo XXX llega a screen_ticker
    assert result.batches_failed == 0


def test_run_etapa1_screen_skips_whole_batch_on_downloader_exception():
    closes = _rising_candidate_closes()

    def fake_downloader(chunk, period, interval):
        if "BAD" in chunk:
            raise RuntimeError("network error")
        frames = {t: _weekly_df(closes) for t in chunk}
        return _multiindex_batch_result(frames)

    result = run_etapa1_screen(
        ["BAD", "GOOD1", "GOOD2"], batch_size=1, ma_window=10, downloader=fake_downloader
    )

    result_tickers = {c.ticker for c in result.candidates}
    assert result_tickers == {"GOOD1", "GOOD2"}
    assert result.tickers_attempted == 3
    assert result.tickers_screened == 2
    assert result.batches_failed == 1  # batch_size=1 -> el lote de "BAD" es el único fallido


def test_run_etapa1_screen_handles_multiindex_and_flat_column_shapes():
    closes = _rising_candidate_closes()

    def fake_downloader(chunk, period, interval):
        if len(chunk) == 1:
            return _weekly_df(closes)  # columnas planas
        return _multiindex_batch_result({t: _weekly_df(closes) for t in chunk})

    multi_result = run_etapa1_screen(
        ["AAA", "BBB"], batch_size=2, ma_window=10, downloader=fake_downloader
    )
    single_result = run_etapa1_screen(
        ["CCC"], batch_size=1, ma_window=10, downloader=fake_downloader
    )

    assert {c.ticker for c in multi_result.candidates} == {"AAA", "BBB"}
    assert {c.ticker for c in single_result.candidates} == {"CCC"}


def test_run_etapa1_screen_treats_flat_columns_as_failed_batch_when_chunk_has_multiple_tickers():
    # FIX 1: si un lote de >1 ticker devuelve columnas PLANAS (no MultiIndex),
    # la forma de la respuesta no coincide con el pedido -> no hay manera
    # segura de saber a qué ticker pertenece cada fila. Antes esto atribuía
    # silenciosamente el MISMO frame a todos los tickers del lote. Debe
    # tratarse como lote fallido (se omite entero), no como candidatos válidos.
    closes = _rising_candidate_closes()

    def fake_downloader(chunk, period, interval):
        # Respuesta malformada: columnas planas pese a pedir 2 tickers.
        return _weekly_df(closes)

    result = run_etapa1_screen(
        ["AAA", "BBB"], batch_size=2, ma_window=10, downloader=fake_downloader
    )

    assert result.candidates == []
    assert result.tickers_screened == 0
    assert result.tickers_attempted == 2
    assert result.batches_failed == 1


def test_run_etapa1_screen_sorts_candidates_by_distance_pct_ascending():
    # Misma tendencia ascendente para las tres, pero cada una termina con un
    # salto final distinto -> distancias a la MA distintas, todas candidatas.
    rising = [100.0 + i * 2 for i in range(19)]
    near = rising + [rising[-1] + 2]
    mid = rising + [rising[-1] + 20]
    far = rising + [rising[-1] + 60]

    def fake_downloader(chunk, period, interval):
        data = {"FAR": far, "NEAR": near, "MID": mid}
        frames = {t: _weekly_df(data[t]) for t in chunk}
        return _multiindex_batch_result(frames)

    result = run_etapa1_screen(
        ["FAR", "NEAR", "MID"],
        batch_size=3,
        ma_window=10,
        distance_pct_threshold=100,
        downloader=fake_downloader,
    )

    assert [c.ticker for c in result.candidates] == ["NEAR", "MID", "FAR"]
    distances = [c.distance_pct for c in result.candidates]
    assert distances == sorted(distances)


def test_run_etapa1_screen_isolates_ticker_when_screen_ticker_raises(monkeypatch):
    # A ticker that reaches screen_ticker (non-empty extracted frame) but
    # blows up inside it must not abort the run: other tickers in the same
    # batch should still be screened and returned normally.
    closes = _rising_candidate_closes()
    original_screen_ticker = etapa1.screen_ticker

    def flaky_screen_ticker(ticker, df, **kwargs):
        if ticker == "BAD":
            raise ValueError("boom")
        return original_screen_ticker(ticker, df, **kwargs)

    monkeypatch.setattr(etapa1, "screen_ticker", flaky_screen_ticker)

    def fake_downloader(chunk, period, interval):
        frames = {t: _weekly_df(closes) for t in chunk}
        return _multiindex_batch_result(frames)

    result = run_etapa1_screen(
        ["BAD", "GOOD1", "GOOD2"], batch_size=3, ma_window=10, downloader=fake_downloader
    )

    result_tickers = {c.ticker for c in result.candidates}
    assert "BAD" not in result_tickers
    assert {"GOOD1", "GOOD2"} <= result_tickers
    assert result.tickers_attempted == 3
    assert result.tickers_screened == 2  # BAD lanza excepción antes de contarse
    assert result.batches_failed == 0


def test_run_etapa1_screen_excludes_non_candidates():
    candidate_closes = _rising_candidate_closes()
    non_candidate_closes = _flat_non_candidate_closes()

    def fake_downloader(chunk, period, interval):
        data = {"YES": candidate_closes, "NO": non_candidate_closes}
        frames = {t: _weekly_df(data[t]) for t in chunk}
        return _multiindex_batch_result(frames)

    result = run_etapa1_screen(
        ["YES", "NO"], batch_size=2, ma_window=10, downloader=fake_downloader
    )

    result_tickers = {c.ticker for c in result.candidates}
    assert "YES" in result_tickers
    assert "NO" not in result_tickers
    # "NO" sí se screenea con éxito (no es un fallo), simplemente no es candidato.
    assert result.tickers_screened == 2
