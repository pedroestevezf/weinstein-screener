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


def test_build_chart_data_excludes_a_marker_date_before_the_visible_window():
    # a marker date that IS present in df_weekly_full.index but falls
    # before df_visible's start (outside the fixed visible window) must
    # be excluded from result.markers -- an out-of-window marker with no
    # bound stretches the chart's inferred x-domain across the whole gap.
    df = _weekly_df(40)  # visible window is df.index[8:40] for visible_weeks=32

    result = build_chart_data(
        df,
        marker_dates={"SC": df.index[2]},
        range_low=90.0, range_high=140.0, range_target=None,
        visible_weeks=32, ma_window=30,
    )

    assert result.markers == []


def test_build_chart_data_default_visible_window_is_52_weeks():
    # fixed at 52 weeks by default -- chosen to cover the SC in
    # practically every real case (see docstring): phase_a_recency_weeks
    # (26) bounds how old the ST can be, and ar_window + st_window (24)
    # bounds how far the SC can precede the ST, so a "vigente" structure's
    # SC lands within roughly 50 weeks of today.
    df = _weekly_df(80)

    result = build_chart_data(
        df, marker_dates={}, range_low=90.0, range_high=140.0, range_target=None,
    )

    assert len(result.df_visible) == 52
    assert result.df_visible.index[0] == df.index[-52]


def test_build_chart_data_carries_range_and_target_through_unchanged():
    df = _weekly_df(40)

    result = build_chart_data(
        df, marker_dates={}, range_low=172.0, range_high=205.0, range_target=245.0,
        visible_weeks=32, ma_window=30,
    )

    assert result.range_low == 172.0
    assert result.range_high == 205.0
    assert result.range_target == 245.0
