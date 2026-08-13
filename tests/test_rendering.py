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
