import pandas as pd
import pytest

from weinstein_screener.ict import (
    _is_low_volume_candle,
    find_buec,
    find_entry_1_signal,
    find_entry_3_signal,
    find_fair_value_gap,
    find_order_block,
    find_spring_reentry_mss,
)


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
    rows = [
        {"Open": 100, "High": 102, "Low": 99, "Close": 98, "Volume": 500_000},   # bearish, but before min_index
        {"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 500_000},
        {"Open": 101, "High": 103, "Low": 100, "Close": 102, "Volume": 500_000},
        {"Open": 102, "High": 104, "Low": 101, "Close": 103, "Volume": 500_000},
    ]
    df = _daily_df(rows)

    result = find_order_block(df, impulse_end_index=4, lookback=10, min_index=1)

    assert result is None


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


def test_find_buec_locates_the_buec_with_declining_volume():
    rows = [
        {"Open": 118, "High": 122, "Low": 117, "Close": 121, "Volume": 900_000},   # ruptura, índice 0
        {"Open": 128, "High": 130, "Low": 127, "Close": 129, "Volume": 700_000},   # aún no toca la banda, índice 1
        {"Open": 127, "High": 127, "Low": 118, "Close": 119, "Volume": 500_000},   # BUEC, índice 2
        {"Open": 119, "High": 120, "Low": 116, "Close": 117, "Volume": 300_000},
        {"Open": 117, "High": 118, "Low": 115, "Close": 116, "Volume": 200_000},
    ]
    df = _daily_df(rows)

    result = find_buec(df, ar_high=120, breakout_index=0, window=5, tolerance=0.05)

    assert result.buec_index == 2
    assert result.volume_declining is True


def test_find_buec_triggers_on_the_first_candidate_day():
    rows = [
        {"Open": 118, "High": 122, "Low": 117, "Close": 121, "Volume": 900_000},  # ruptura, índice 0
        {"Open": 121, "High": 122, "Low": 118, "Close": 119, "Volume": 500_000},  # BUEC el primer día, índice 1
    ]
    df = _daily_df(rows)

    result = find_buec(df, ar_high=120, breakout_index=0, window=5, tolerance=0.05)

    assert result is not None
    assert result.buec_index == 1
    assert result.volume_declining is True


def test_find_buec_returns_none_without_touching_the_band():
    rows = [{"Open": 130, "High": 132, "Low": 129, "Close": 131, "Volume": 500_000} for _ in range(6)]
    df = _daily_df(rows)

    result = find_buec(df, ar_high=120, breakout_index=0, window=5, tolerance=0.05)

    assert result is None


def test_find_buec_triggers_via_no_supply_candle():
    rows = [
        {"Open": 118, "High": 122, "Low": 110, "Close": 121, "Volume": 500_000},    # ruptura, índice 0 (rango 12)
        {"Open": 128, "High": 130, "Low": 127, "Close": 129, "Volume": 600_000},    # no toca la banda, índice 1
        {"Open": 119.3, "High": 119.5, "Low": 117, "Close": 119, "Volume": 200_000},  # vela no-supply, índice 2
    ]
    df = _daily_df(rows)

    result = find_buec(df, ar_high=120, breakout_index=0, window=5, tolerance=0.05)

    assert result is not None
    assert result.buec_index == 2
    assert result.no_supply is True
    assert result.volume_declining is False


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


def test_find_entry_3_signal_composes_buec_order_block_and_stop_loss():
    rows = [
        {"Open": 118, "High": 122, "Low": 117, "Close": 121, "Volume": 900_000},    # ruptura, índice 0
        {"Open": 128, "High": 130, "Low": 127, "Close": 129, "Volume": 700_000},    # aún no toca la banda, índice 1
        {"Open": 122, "High": 122.5, "Low": 118, "Close": 119, "Volume": 500_000},   # BUEC, índice 2 (bajista)
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


def test_find_entry_3_signal_can_find_a_reinforcing_fvg_after_the_buec():
    rows = [
        {"Open": 118, "High": 122, "Low": 117, "Close": 121, "Volume": 900_000},    # ruptura, índice 0
        {"Open": 128, "High": 130, "Low": 127, "Close": 129, "Volume": 700_000},    # no toca la banda, índice 1
        {"Open": 122, "High": 122.5, "Low": 118, "Close": 119, "Volume": 500_000},   # BUEC, índice 2
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


def test_find_entry_3_signal_returns_none_without_a_buec():
    rows = [{"Open": 130, "High": 132, "Low": 129, "Close": 131, "Volume": 500_000} for _ in range(6)]
    df = _daily_df(rows)
    atr = pd.Series([1.0] * len(df), index=df.index)

    result = find_entry_3_signal(df, ar_high=120, breakout_index=0, atr=atr, window=5, tolerance=0.05)

    assert result is None


def test_find_buec_triggers_via_low_volume_candle():
    # 9 velas de relleno con volumen alto (para inflar la mediana de la ventana de
    # lookback), seguidas de la ruptura con volumen bajo. La mediana de las 10
    # velas previas al candidato (9 x 2,000,000 + 1 x 100,000) es 2,000,000.
    rows = [{"Open": 110, "High": 111, "Low": 109, "Close": 110, "Volume": 2_000_000} for _ in range(9)]
    rows.append({"Open": 118, "High": 122, "Low": 117, "Close": 121, "Volume": 100_000})  # ruptura, índice 9
    rows.append(
        # candidato, índice 10: alcista (no bajista) y de rango amplio (no estrecho),
        # así que no cumple no_supply. Volumen (500,000) > volumen de ruptura (100,000),
        # así que tampoco hay descenso de volumen en el segmento comparado.
        # 500,000 <= 0.5 * 2,000,000 (mediana) -> low_volume.
        {"Open": 119, "High": 121, "Low": 118, "Close": 120, "Volume": 500_000}
    )
    df = _daily_df(rows)

    result = find_buec(df, ar_high=120, breakout_index=9, window=5, tolerance=0.05)

    assert result is not None
    assert result.buec_index == 10
    assert result.low_volume is True
    assert result.no_supply is False
    assert result.volume_declining is False


def test_find_buec_does_not_trigger_low_volume_just_above_the_threshold():
    rows = [{"Open": 110, "High": 111, "Low": 109, "Close": 110, "Volume": 2_000_000} for _ in range(9)]
    rows.append({"Open": 118, "High": 122, "Low": 117, "Close": 121, "Volume": 100_000})  # ruptura, índice 9
    rows.append(
        # candidato, índice 10: mismo perfil que el test anterior, pero con
        # volumen al 65% de la mediana (1,300,000), por encima del umbral del 50%.
        {"Open": 119, "High": 121, "Low": 118, "Close": 120, "Volume": 1_300_000}
    )
    df = _daily_df(rows)

    result = find_buec(df, ar_high=120, breakout_index=9, window=5, tolerance=0.05)

    assert result is None


def test_is_low_volume_candle_uses_median_not_mean():
    # Escenario numérico del documento de diseño: un pico de 2,300,000 mezclado
    # en la ventana de 10 velas previas. mediana=502,500 (umbral=251,250),
    # media=681,500 (umbral=340,750).
    prior_volumes = [500_000, 520_000, 480_000, 510_000, 495_000, 2_300_000, 505_000, 490_000, 515_000, 500_000]

    # Caso positivo claro: 230,000 <= 251,250 (mediana) y también <= 340,750
    # (media) -> True bajo cualquiera de las dos implementaciones. Sirve como
    # verificación básica de que la función detecta bajo volumen.
    rows_low = [{"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": v} for v in prior_volumes]
    rows_low.append({"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 230_000})
    df_low = _daily_df(rows_low)

    assert _is_low_volume_candle(df_low, index=10) is True

    # Caso discriminante: 300,000 está ESTRICTAMENTE ENTRE los dos umbrales.
    # 300,000 <= 251,250 (mediana) -> False (comportamiento correcto).
    # 300,000 <= 340,750 (media) -> True (lo que devolvería una implementación
    # incorrecta basada en la media). Este caso es el que realmente distingue
    # una implementación de mediana de una de media.
    rows_mid = [{"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": v} for v in prior_volumes]
    rows_mid.append({"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 300_000})
    df_mid = _daily_df(rows_mid)

    assert _is_low_volume_candle(df_mid, index=10) is False


def test_find_entry_3_signal_is_high_confidence_when_buec_confirmed_only_by_low_volume():
    rows = [{"Open": 110, "High": 111, "Low": 109, "Close": 110, "Volume": 2_000_000} for _ in range(9)]
    rows.append({"Open": 118, "High": 122, "Low": 117, "Close": 121, "Volume": 100_000})  # ruptura, índice 9
    rows.append(
        # BUEC, índice 10: bajista (para que find_order_block lo identifique
        # como su propio Order Block) pero de rango amplio y volumen bajo vs.
        # las 2 velas previas altas, así que no cumple no_supply (rango no
        # estrecho). Sí cumple low_volume: 500,000 <= 0.5 * 2,000,000 (mediana).
        {"Open": 121, "High": 124, "Low": 117, "Close": 119, "Volume": 500_000}
    )
    df = _daily_df(rows)
    atr = pd.Series([1.0] * len(df), index=df.index)

    result = find_entry_3_signal(df, ar_high=120, breakout_index=9, atr=atr, window=5, tolerance=0.05)

    assert result is not None
    assert result.trigger_index == 10
    assert result.high_confidence is True
