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
