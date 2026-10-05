"""The webshop proposal (ADR-061): every product gives sane pieces, fabric and a price."""

import pytest
from coverengine import quote
from coverengine.errors import CoverError
from coverengine.params import Registry

PARAMS = Registry.load(None).resolve()


@pytest.mark.parametrize("product", sorted(quote.PRODUCTS))
def test_every_product_gives_a_proposal(product: str) -> None:
    q = quote.proposal(product, {}, PARAMS)
    assert q["pieces"] and q["fabric_m2"] >= q["cover_area_m2"] > 0
    assert q["roll_m"] > 0 and q["vents"] >= 4  # at least one per side
    p = q["price"]
    assert 0 < p["cost_eur"] < p["sale_ex_vat_eur"] < p["sale_eur"]
    # no cut piece wider than the roll
    roll = float(PARAMS["roll.usable_width_mm"]) / 10
    assert all(min(x["cut_width_cm"], x["cut_height_cm"]) <= roll for x in q["pieces"])


def test_a_dining_set_with_chairs_is_wider_and_gets_balloons() -> None:
    alone = quote.proposal("dining_set", {"table_length_cm": 340, "chairs": False}, PARAMS)
    seated = quote.proposal("dining_set", {"table_length_cm": 340, "chairs": True}, PARAMS)
    assert seated["sizes_cm"]["depth_cm"] > alone["sizes_cm"]["depth_cm"] + 60
    assert seated["balloons"] == 4  # 340 cm: one per 110 cm (owner: 3 to 4)
    assert seated["price"]["sale_eur"] > alone["price"]["sale_eur"]


def test_sizes_outside_the_range_are_refused() -> None:
    with pytest.raises(CoverError):
        quote.proposal("sofa", {"length_cm": 5000}, PARAMS)
    with pytest.raises(CoverError):
        quote.proposal("spaceship", {}, PARAMS)


def test_the_preview_is_a_glb() -> None:
    assert quote.preview_glb("corner_sofa", {}, PARAMS)[:4] == b"glTF"


@pytest.mark.parametrize("product", ["dining_set", "round_set"])
def test_pushed_in_chairs_stand_inside_the_widened_cover(product: str) -> None:
    """The owner, 5 Oct 2026: the cover is made wider so the chairs fit underneath it."""
    import numpy as np

    given = {"chairs": True}
    cover = quote.cover_mesh(product, given, PARAMS)
    under = quote.under_cover(product, given, PARAMS)
    lo, hi = cover.bounds
    assert under.vertices[:, 2].max() < hi[2]  # the chair backs below the top
    if product == "round_set":
        assert np.hypot(under.vertices[:, 0], under.vertices[:, 1]).max() < hi[0]
    else:
        assert (under.vertices[:, :2] > lo[:2]).all() and (under.vertices[:, :2] < hi[:2]).all()


def test_balloons_show_in_the_scene_and_touch_the_roof() -> None:
    import trimesh

    given = {"table_length_cm": 220, "chairs": True}
    with_b = trimesh.load(
        trimesh.util.wrap_as_stream(quote.scene_glb("dining_set", given, PARAMS, "balloons")),
        file_type="glb",
    )
    without = trimesh.load(
        trimesh.util.wrap_as_stream(quote.scene_glb("dining_set", given, PARAMS, "none")),
        file_type="glb",
    )
    assert any("balloon" in n for n in with_b.geometry)
    assert not any("balloon" in n for n in without.geometry)
    balls = quote.balloons_mesh("dining_set", given, PARAMS)
    roof = quote.cover_mesh("dining_set", given, PARAMS, "balloons")
    assert balls is not None and abs(balls.bounds[1][2] - roof.bounds[1][2]) < 1.0
