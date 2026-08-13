import altair as alt
import pandas as pd

from weinstein_screener.chart_data import ChartData, ChartMarker
from weinstein_screener.rendering import render_price_chart


_DEFAULT_SC_DATE = object()  # sentinel: "use the fixture's default SC date" -- distinct from an explicit None


def _sample_chart_data(sc_date=_DEFAULT_SC_DATE, jac_date=None):
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
    return ChartData(
        df_visible=df,
        ma=ma,
        markers=markers,
        range_low=95.0,
        range_high=115.0,
        range_target=120.0,
        sc_date=dates[3] if sc_date is _DEFAULT_SC_DATE else sc_date,
        jac_date=jac_date,
    )


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
    # range_band(0), solid range line(1), wicks(2), bodies(3), ma_line(4)
    # -- the sample fixture has no jac_date, so range_lines is a single layer
    wicks_layer_dict = price_panel_dict["layer"][2]

    assert wicks_layer_dict["encoding"]["y"]["axis"]["orient"] == "right"


def _layer_values(chart_dict, layer_index):
    layer = chart_dict["layer"][layer_index]
    return chart_dict["datasets"][layer["data"]["name"]]


def test_render_price_chart_omits_range_lines_when_sc_date_is_none():
    chart_data = _sample_chart_data(sc_date=None)
    chart_data.markers = []
    chart_data.range_target = None

    result = render_price_chart(chart_data)
    price_panel = result.vconcat[0]

    # range_band, wicks, bodies, ma_line -- no SC date means no range line
    # layers at all (the accumulation range doesn't exist before the SC).
    assert len(price_panel.layer) == 4


def test_render_price_chart_range_line_is_one_solid_segment_from_sc_to_now_without_a_jac():
    dates = pd.date_range("2024-01-01", periods=10, freq="W-MON")
    chart_data = _sample_chart_data(sc_date=dates[2], jac_date=None)

    result = render_price_chart(chart_data)
    price_panel_dict = result.vconcat[0].to_dict()
    solid_layer = price_panel_dict["layer"][1]
    values = _layer_values(price_panel_dict, 1)

    assert "strokeDash" not in solid_layer["mark"]
    assert {v["level"] for v in values} == {95.0, 115.0}
    assert all(v["start"] == dates[2].isoformat() for v in values)
    assert all(v["end"] == dates[-1].isoformat() for v in values)


def test_render_price_chart_range_line_splits_solid_and_dotted_at_the_jac():
    dates = pd.date_range("2024-01-01", periods=10, freq="W-MON")
    chart_data = _sample_chart_data(sc_date=dates[2], jac_date=dates[6])

    result = render_price_chart(chart_data)
    price_panel_dict = result.vconcat[0].to_dict()
    solid_layer, dotted_layer = price_panel_dict["layer"][1], price_panel_dict["layer"][2]
    solid_values = _layer_values(price_panel_dict, 1)
    dotted_values = _layer_values(price_panel_dict, 2)

    # solid: both levels, from SC to the JAC
    assert "strokeDash" not in solid_layer["mark"]
    assert {v["level"] for v in solid_values} == {95.0, 115.0}
    assert all(v["start"] == dates[2].isoformat() and v["end"] == dates[6].isoformat() for v in solid_values)

    # dotted: only the top level (range_high) continues past the JAC to the last visible date
    assert dotted_layer["mark"]["strokeDash"] == [2, 2]
    assert len(dotted_values) == 1
    assert dotted_values[0]["level"] == 115.0
    assert dotted_values[0]["start"] == dates[6].isoformat()
    assert dotted_values[0]["end"] == dates[-1].isoformat()
