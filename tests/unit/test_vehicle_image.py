"""Image resolution and rendering for the vehicle card.

The fallback chain is the point: a fixture may name a file that is absent, unreadable, or
remote, and none of those may put a broken image in front of a customer.
"""

from __future__ import annotations

import base64

import pytest

import ui_components as ui
from pricing_agent.config.loader import REPO_ROOT

FIXTURE_PATH = "assets/vehicles/toyota_rav4_2022.jpg"


def test_the_demo_asset_is_actually_in_the_repository():
    """Guards against the fixture pointing at a file nobody committed."""
    path = ui.resolve_image(FIXTURE_PATH)
    assert path is not None, f"{FIXTURE_PATH} did not resolve"
    assert path.is_file()
    assert path.stat().st_size > 20_000, "suspiciously small for a photograph"


def test_v10001_fixture_points_at_that_asset():
    import json

    inventory = json.loads(
        (REPO_ROOT / "mocks" / "inventory" / "dealer-1001-inventory.json").read_text(
            encoding="utf-8"
        )
    )
    vehicle = next(
        v for v in inventory["data"]["vehicles"] if v["vehicle_id"] == "V-10001"
    )
    assert vehicle["image_url"] == FIXTURE_PATH
    assert ui.resolve_image(vehicle["image_url"]) is not None


def test_resolution_is_repo_relative_not_cwd_relative(tmp_path, monkeypatch):
    """Streamlit is usually launched from the repo root, but the page must not depend on
    it — and tests run from anywhere."""
    monkeypatch.chdir(tmp_path)
    assert ui.resolve_image(FIXTURE_PATH) is not None


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "assets/vehicles/does_not_exist.jpg",
        "https://example.com/car.jpg",
        "http://example.com/car.jpg",
        "//example.com/car.jpg",
    ],
)
def test_unusable_values_resolve_to_none(value):
    """Remote URLs are refused deliberately: the demo must work with no network, and a
    runtime fetch would put an unreachable host in front of a customer."""
    assert ui.resolve_image(value) is None


def test_paths_cannot_escape_the_repository():
    assert ui.resolve_image("../../../etc/passwd") is None


def test_photo_markup_embeds_the_image_rather_than_linking_it():
    path = ui.resolve_image(FIXTURE_PATH)
    markup = ui.vehicle_photo_html(path)

    assert markup.startswith("<!DOCTYPE html>")
    assert "data:image/jpeg;base64," in markup, "must be embedded, not fetched at runtime"
    assert "http://" not in markup and "https://" not in markup

    # The decoded payload must be a real JPEG.
    encoded = markup.split("base64,", 1)[1].split('"', 1)[0]
    assert base64.b64decode(encoded[:64] + "=" * (-len(encoded[:64]) % 4))[:3] == b"\xff\xd8\xff"


def test_photo_fills_the_card_without_distorting_the_vehicle():
    """object-fit: cover crops; it never stretches. A squashed car reads as a bug."""
    markup = ui.vehicle_photo_html(ui.resolve_image(FIXTURE_PATH))
    assert "object-fit:cover" in markup
    assert "border-radius:10px" in markup
    assert "width:100%" in markup
    assert f"height:{ui.CARD_HEIGHT}px" in markup
    assert "background:transparent" in markup


def test_photo_and_silhouette_share_a_card_height():
    """So the layout does not reflow as the user moves between vehicles."""
    photo = ui.vehicle_photo_html(ui.resolve_image(FIXTURE_PATH))
    silhouette = ui.vehicle_silhouette_svg("SUV", "RAV4")
    assert f"height:{ui.CARD_HEIGHT}px" in photo
    assert silhouette.startswith("<!DOCTYPE html>")


def test_other_vehicles_still_fall_back_to_a_silhouette():
    import json

    inventory = json.loads(
        (REPO_ROOT / "mocks" / "inventory" / "dealer-1001-inventory.json").read_text(
            encoding="utf-8"
        )
    )
    without = [
        v for v in inventory["data"]["vehicles"] if not v.get("image_url")
    ]
    assert len(without) == 11, "only V-10001 should carry a photo"
    for vehicle in without:
        assert ui.resolve_image(vehicle.get("image_url")) is None


def test_attribution_file_records_the_license():
    text = (REPO_ROOT / "assets" / "vehicles" / "ATTRIBUTION.md").read_text(encoding="utf-8")
    for required in ("Wikimedia Commons", "CC0", "TTTNIS", "commons.wikimedia.org"):
        assert required in text, f"attribution is missing {required}"
