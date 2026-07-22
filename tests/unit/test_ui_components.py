"""Presentation helpers: body-style mapping and the silhouette markup.

The mapping is the part worth testing. Segment alone is not enough — the EV segment
covers both crossovers and sedans — so a wrong shape is silently plausible, which is
exactly the kind of thing that survives a code review and gets noticed in a demo.
"""

from __future__ import annotations

import pytest

import ui_components as ui


@pytest.mark.parametrize(
    ("segment", "model", "expected"),
    [
        ("SUV", "RAV4", "SUV"),
        ("SEDAN", "Accord", "SEDAN"),
        ("TRUCK", "F-150", "TRUCK"),
        ("VAN", "Sienna", "VAN"),
        # Luxury is a price tier, not a shape.
        ("LUXURY", "540i", "SEDAN"),
        # The EV segment spans both shapes, so the model decides.
        ("EV", "Bolt EUV", "SUV"),
        ("EV", "Model 3", "SEDAN"),
        ("EV", "Leaf", "SEDAN"),
        # Unknown or missing segment must still produce something renderable.
        ("UNKNOWN", None, "SEDAN"),
        (None, None, "SEDAN"),
    ],
)
def test_body_style_mapping(segment, model, expected):
    assert ui.body_style(segment, model) == expected


@pytest.mark.parametrize("style", ["SEDAN", "SUV", "TRUCK", "VAN"])
def test_every_body_style_has_complete_artwork(style):
    """A missing path or wheel set would render as a partial car rather than an error."""
    assert style in ui._BODIES
    assert style in ui._WHEELS
    assert style in ui._WINDOWS
    assert len(ui._WHEELS[style]) == 3


@pytest.mark.parametrize(
    ("segment", "model"), [("SEDAN", "Accord"), ("SUV", "RAV4"), ("TRUCK", "F-150"), ("VAN", "Sienna")]
)
def test_silhouette_is_a_self_contained_document(segment, model):
    """It is rendered through components.html, which needs a full document.

    st.html and st.markdown both strip <svg> and leave the wrapper behind, which shows up
    as an empty bar rather than an obvious failure — so the markup must stay iframe-ready.
    """
    svg = ui.vehicle_silhouette_svg(segment, model)
    assert svg.startswith("<!DOCTYPE html>")
    assert "<svg" in svg and "viewBox" in svg
    assert svg.count("<circle") == 4, "two wheels, each with a hub"
    assert "background:transparent" in svg, "must not punch a white box into a dark theme"
    assert "aria-label" in svg


def test_aging_timeline_stacks_elapsed_and_projected():
    figure = ui.aging_timeline(days_in_inventory=37, additional_p50=30.0, additional_p90=65.0)

    assert len(figure.data) == 2
    elapsed, projected = figure.data
    assert elapsed.x[0] == 37
    # Plotly keeps a scalar `base` scalar rather than broadcasting it to a list.
    assert projected.base == 37, "the projection must start where the elapsed bar ends"
    assert projected.x[0] == 30.0
    # The whisker carries the P90 tail, which is the exposure the median hides.
    assert projected.error_x.array[0] == pytest.approx(35.0)


def test_aging_timeline_handles_a_p90_below_p50():
    """Percentiles come from draws and are ordered, but a degenerate distribution should
    not produce a negative error bar."""
    figure = ui.aging_timeline(days_in_inventory=10, additional_p50=20.0, additional_p90=15.0)
    assert figure.data[1].error_x.array[0] == 0.0
