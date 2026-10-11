"""ADR-119: barbecues in the configurator and in the catalogue."""

import json
import math
from pathlib import Path

import numpy as np
import pytest
import shapely
from coverengine import bbq, drawn, match, quote
from coverengine.params import Registry

P = Registry.load(None).resolve()
BBQ = [k for k, v in quote.PRODUCTS.items() if v["group"] == "bbq"]
CASES = [(k, {}) for k in BBQ] + [
    ("bbq_kamado", {"side_tables": True}),
    ("bbq_fire_table", {"square": True}),
]


def test_the_barbecues_are_a_group_of_their_own() -> None:
    assert set(BBQ) == {"bbq_kamado", "bbq_kamado_table", "bbq_gas", "bbq_pellet",
                        "bbq_fire_table"}  # fmt: skip
    opts = quote.options(P)["products"]
    assert opts["bbq_gas"]["group"] == "bbq" and opts["sofa"]["group"] is None


@pytest.mark.parametrize(("product", "extra"), CASES)
def test_a_barbecue_cover_fits_over_it_fits_the_roll_and_sheds_water(
    product: str, extra: dict
) -> None:
    pr = quote.proposal(product, extra, P)
    assert pr["cold_only"] is True  # a cover over a cold barbecue only
    assert pr["roof_slope_deg"] >= float(P["quote.bbq_slope_min_deg"])
    assert pr["shape"] == ("cone round" if product in ("bbq_kamado", "bbq_fire_table")
                           and not extra else "hip box")  # fmt: skip
    roll = float(P["roll.usable_width_mm"]) / 10
    for piece in pr["pieces"]:
        assert min(piece["cut_width_cm"], piece["cut_height_cm"]) <= roll
    assert pr["vents"] >= 1 and pr["price"]["sale_eur"] > 0
    # every point of the barbecue is inside the cover, with the ease
    cover = quote.cover_mesh(product, extra, P)
    under = quote.under_cover(product, extra, P)
    ease = float(P["quote.ease_cm"]) * 10
    lo, hi = cover.bounds
    v = under.vertices
    assert (v[:, :2] >= lo[:2] + ease - 1).all() and (v[:, :2] <= hi[:2] - ease + 1).all()
    assert v[:, 2].max() + ease <= hi[2] + 1e-6
    rain = quote.rain_check(product, extra, P)
    assert list(rain["options"]) == ["none"] and rain["options"]["none"]["dry"]


def test_the_roof_clears_every_point() -> None:
    mesh = bbq.gas(1560, 685, 1220, 915, 880)
    f = bbq.fit(mesh, "hip box", 25.0, 12.0, 30.0, 350.0)
    s = math.tan(math.radians(f["slope_deg"]))
    a, b = f["length_mm"] / 2, f["depth_mm"] / 2
    top = f["wall_mm"] + f["rise_mm"]
    v = mesh.vertices - np.r_[(mesh.bounds[0][:2] + mesh.bounds[1][:2]) / 2, 0]
    roof = top - s * np.maximum(np.abs(v[:, 1]), np.abs(v[:, 0]) - (a - b))
    assert (v[:, 2] + 25.0 <= roof + 1e-6).all()
    assert f["wall_mm"] >= 350.0


def test_a_cone_s_sectors_lie_flat_exactly() -> None:
    pieces = drawn.build("cone round", {"diameter_cm": 90, "height_cm": 80, "rise_cm": 30}, 1450)
    tops = [p for p in pieces if p.name.startswith("top")]
    bands = [p for p in pieces if p.name.startswith("band")]
    assert len(tops) == len(bands) >= 2  # a cone is no flat disc; the seams line up
    for p in tops:
        flat = shapely.Polygon(p.flat).area
        tri = np.array(p.faces)
        area3d = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]),
                                      axis=1).sum()  # fmt: skip
        assert abs(flat - area3d) / area3d < 0.002  # developable: the same area flat
    # a cone over a 90 cm band: slant 51 cm
    r, rise = 450.0, 300.0
    assert abs(max(math.hypot(*q) for q in tops[0].flat) - math.hypot(r, rise)) < 1e-6


def test_a_hipped_box_slopes_on_every_roof_face() -> None:
    pieces = drawn.build("hip box", {"length_cm": 160, "depth_cm": 74, "height_cm": 110,
                                     "rise_cm": 19}, 1450)  # fmt: skip
    assert len(pieces) == 8
    for p in pieces:
        if not p.name.startswith("roof"):
            continue
        v = np.array(p.faces[0])
        n = np.cross(v[1] - v[0], v[2] - v[0])
        tilt = math.degrees(math.acos(abs(n[2]) / np.linalg.norm(n)))
        assert tilt > 20  # all four roof faces at the same, real slope


def _bbq_cover(models: Path, mid: str, kind: str, size_cm: tuple, status: str | None) -> None:
    d = models / mid
    d.mkdir(parents=True)
    (d / "cover.json").write_text(json.dumps(
        {"category": "BBQ › Kamado", "match": {"kind": kind, "name": "Big Green Egg Large in nest",
                                              "families": ["big green egg"]}}))  # fmt: skip
    (d / "model.json").write_text(json.dumps({"size_mm": [x * 10 for x in size_cm]}))
    if status:
        (d / "desk.json").write_text(json.dumps({"status": status}))


def test_a_barbecue_cover_of_our_range_is_offered_once_approved(tmp_path: Path) -> None:
    models = tmp_path / "models"
    size = bbq.plan_cm("bbq_kamado", {k: d for k, (d, _, _) in
                                      quote.PRODUCTS["bbq_kamado"]["fields"].items()})  # fmt: skip
    _bbq_cover(models, "bbq-bge-large-nest", "bbq_kamado", (size[1], size[0], size[2]),
               "approved")  # fmt: skip
    _bbq_cover(models, "bbq-bge-xlarge-nest", "bbq_kamado", (70, 86, 112), "new")  # not yet
    r = match.match("bbq_kamado", {}, models, P)
    assert [m["model_id"] for m in r["matches"]] == ["bbq-bge-large-nest"]
    assert r["decision"] == "existing" and r["matches"][0]["score_pct"] == 100.0
    assert r["matches"][0]["name"] == "Big Green Egg Large in nest"
    # another kind of barbecue never matches it
    assert match.match("bbq_gas", {}, models, P)["matches"] == []
    # its sizes as the configurator's fields price a cover within the ranges
    fields = match.fields_for("bbq_kamado", size)
    spec = quote.PRODUCTS["bbq_kamado"]["fields"]
    assert fields["side_tables"] is False
    for k, v in fields.items():
        if spec[k][1] is not None:
            assert spec[k][1] <= v <= spec[k][2]
    assert quote.proposal("bbq_kamado", fields, P)["shape"] == "cone round"


def test_every_barbecue_word_is_in_four_languages() -> None:
    ui = json.loads((Path(__file__).resolve().parents[2] / "config/shop_ui.json").read_text())
    for k in BBQ:
        assert set(ui["product"][k]) >= {"nl", "en", "de", "fr"}, k
        for f in quote.PRODUCTS[k]["fields"]:
            assert set(ui["field"][f]) >= {"nl", "en"}, f
    for f in ("egg_diameter_cm", "closed_height_cm", "handle_depth_cm", "side_tables",
              "tables_width_cm", "shelf_height_cm", "hood_width_cm", "lid_length_cm",
              "fire_width_cm", "square"):  # fmt: skip
        assert set(ui["field"][f]) >= {"nl", "en", "de", "fr"}, f
    for w in ("group_furniture", "group_bbq", "bbq_cold"):
        assert set(ui["words"][w]) >= {"nl", "en", "de", "fr"}, w
