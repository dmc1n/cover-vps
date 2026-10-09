"""Arrangements: furniture placed together, one cover over the whole (ADR-089)."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import shapely
import trimesh
from coverengine import arrange as ar
from coverengine.cli import main as cover
from coverengine.io.model_io import import_model
from coverengine.params import Registry
from coverengine.testshapes import write_all as write_shapes


@pytest.fixture(scope="module")
def models(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Two imported boxes on legs (800 x 600 x 700 mm), as two catalogue models."""
    root = tmp_path_factory.mktemp("arr")
    write_shapes(root / "generated")
    models = root / "models"
    for name in ("box-a", "box-b"):
        import_model(root / "generated" / "box_with_legs.stl", models / name,
                     Registry.load().resolve())  # fmt: skip
    return models


def test_snap_puts_a_member_against_the_other_side_aligned(models: Path) -> None:
    a, b = ar.Member("box-a"), ar.Member("box-b")
    meshes = {m: ar.furniture(models, m) for m in ("box-a", "box-b")}
    right = ar.snap([a, b], meshes, 1, 0, "right", "back")
    pa, pb = (
        ar.plan_box(ar.placed(meshes["box-a"], a)),
        ar.plan_box(ar.placed(meshes["box-b"], right)),
    )
    assert pb[0] == pytest.approx(pa[2], abs=0.01)  # touching
    assert pb[3] == pytest.approx(pa[3], abs=0.01)  # the backs in line
    front = ar.snap([a, b], meshes, 1, 0, "front", "left", gap_mm=50)
    pf = ar.plan_box(ar.placed(meshes["box-b"], front))
    assert pf[3] == pytest.approx(pa[1] - 50, abs=0.01) and pf[0] == pytest.approx(pa[0], abs=0.01)
    with pytest.raises(Exception, match="side"):
        ar.snap([a, b], meshes, 1, 0, "above")


def test_turned_and_mirrored_members_keep_their_place(models: Path) -> None:
    mesh = ar.furniture(models, "box-a")
    turned = ar.placed(mesh, ar.Member("box-a", 1000, -200, 90, True))
    x0, y0, x1, y1 = ar.plan_box(turned)
    assert (x1 - x0, y1 - y0) == pytest.approx((600, 800), abs=1)  # 90°: width and depth swap
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == pytest.approx((1000, -200), abs=0.01)
    assert turned.bounds[0][2] == pytest.approx(0, abs=1e-6)  # on the ground


def test_two_boxes_side_by_side_become_one_cover(models: Path) -> None:
    a = ar.Member("box-a")
    b = ar.snap([a, ar.Member("box-b")], {m: ar.furniture(models, m) for m in ("box-a", "box-b")},
                1, 0, "right", "back")  # fmt: skip
    src = ar.write(models, "arr-two-boxes", "Two boxes", [a, b])
    d = models / "arr-two-boxes"
    doc = ar.read(d)
    assert doc["size_mm"] == pytest.approx([1600, 600, 700], abs=1)
    assert [m["model_id"] for m in doc["members"]] == ["box-a", "box-b"]
    assert doc["members"][0]["version"]["model_glb"]  # what each member was
    assert ar.stale(models, doc) == []
    assert cover(["import", str(src), "--out", str(d), "--units", "mm", "--up", "z"]) == 0
    (d / "cover.json").write_text(json.dumps({"format_version": 1, "tags": ["arrangement"],
                                              "parameters": {"hull": {"top": "box"}}}))  # fmt: skip
    for step in ("hull", "cut", "flatten", "export"):
        assert cover([step, str(d)]) == 0, step
    assert (d / ar.ARRANGEMENT_JSON).is_file()  # the import kept it
    assert json.loads((d / "kind.json").read_text())["kind"] == "product"  # and the answer
    fin = json.loads((d / "finished.json").read_text())
    pieces = [p for p in fin["pieces"] if not p["name"].startswith("vent")]
    assert pieces and all(min(p["size_mm"]) <= 1500 for p in pieces)  # every piece fits the roll
    assert max(max(p["size_mm"]) for p in pieces) > 1600  # one cover over both boxes

    # moved apart and built again: a bigger arrangement
    far = ar.Member("box-b", b.x_mm + 300, b.y_mm)
    ar.write(models, "arr-two-boxes", "Two boxes", [a, far])
    assert ar.read(d)["size_mm"][0] == pytest.approx(1900, abs=1)


def test_a_changed_member_makes_the_arrangement_stale(models: Path, tmp_path: Path) -> None:
    import shutil

    shutil.copytree(models / "box-a", tmp_path / "box-a")
    shutil.copytree(models / "box-b", tmp_path / "box-b")
    ar.write(tmp_path, "arr-x", "X", [ar.Member("box-a"), ar.Member("box-b", 1000, 0)])
    doc = ar.read(tmp_path / "arr-x")
    glb = tmp_path / "box-b" / "model.glb"
    glb.write_bytes(glb.read_bytes() + b" ")  # a member changed
    assert ar.stale(tmp_path, doc) == ["box-b"]


# ---- the cover's plan follows the members (ADR-095) -----------------------------------------
# The owner, 7 Oct 2026, on the Portofino corner: "you drew a sloping side instead of an L shape
# with a sharp corner; the cover must follow the product and not draw diagonal lines".


def _l_members() -> list[ar.Member]:
    """Box A (800 x 600) and, on its right, two boxes turned to 600 x 800 one behind the other,
    backs in line with A: an L (1400 x 1600) whose inner corner is at A's front right (in the
    arrangement's frame: x 100, y 200)."""
    return [
        ar.Member("box-a"),
        ar.Member("box-b", 700, -100, 90),
        ar.Member("box-b", 700, -900, 90),
    ]


def _plan(d: Path) -> Any:
    """The cover seen from above (hull.glb is glTF: metres, Y up)."""
    m = trimesh.load(d / "hull.glb", force="mesh")
    v = np.asarray(m.vertices) * 1000.0
    tri = np.column_stack([v[:, 0], -v[:, 2]])[m.faces]
    polys = [shapely.Polygon(t) for t in tri]
    return shapely.union_all([p for p in polys if p.area > 1.0]).buffer(0.5).buffer(-0.5)


def test_an_l_arrangement_gets_an_l_cover_with_a_sharp_inner_corner(models: Path) -> None:
    from coverengine.audit import plan_checks
    from coverengine.finish.finish import inner_skirts
    from coverengine.finish.vents3d import vents_3d

    params = Registry.load().resolve()
    c = float(params["hull.clearance_mm"])  # type: ignore[arg-type]
    src = ar.write(models, "arr-l", "L", _l_members())
    d = models / "arr-l"
    assert ar.read(d)["footprint"] == "follow"  # the company default, stored
    assert cover(["import", str(src), "--out", str(d), "--units", "mm", "--up", "z"]) == 0
    (d / "cover.json").write_text(json.dumps({"format_version": 1, "tags": ["arrangement"],
                                              "parameters": {"hull": {"top": "box"}}}))  # fmt: skip
    for step in ("hull", "cut", "flatten", "export"):
        assert cover([step, str(d)]) == 0, step
    hull = json.loads((d / "hull.json").read_text())
    assert hull["box"]["plan"]["footprint"] == "follow"
    assert hull["drainage"]["drains"]  # rule 12

    # seen from above: the members' union offset by the clearance, and nothing more
    rects = [shapely.Polygon(r) for r in ar.plan_rects(ar.read(d))]
    members = shapely.union_all(rects)
    plan = _plan(d)
    allowed = members.buffer(c, join_style="mitre").buffer(3.0)  # a few mm
    outline = np.asarray(plan.exterior.coords)
    assert all(allowed.contains(shapely.Point(p)) for p in outline), "a point outside the members"
    assert plan.area == pytest.approx(members.buffer(c, join_style="mitre").area, rel=0.01)
    # the inner corner is a right angle at the members' corner, not cut off diagonally
    assert plan.exterior.distance(shapely.Point(100 - c, 200 - c)) < 2.0
    assert not plan.contains(shapely.Point(100 - c - 60, 200 - c - 60))
    # every wall stands straight down; the rest is top, sloped enough for water
    mesh = trimesh.load(d / "hull.glb", force="mesh")
    up = np.asarray(mesh.face_normals)[:, 1]  # glTF: Y up
    slope = np.sin(np.radians(float(params["hull.min_slope_deg"])))  # type: ignore[arg-type]
    assert np.all((np.abs(up) < 1e-6) | (up >= slope - 1e-6))
    # every piece fits the roll; the inner corner's walls are found (vents go there too by
    # default, ADR-109; switched off they stay on the outer walls, ADR-093)
    fin = json.loads((d / "finished.json").read_text())
    usable = float(params["roll.usable_width_mm"])  # type: ignore[arg-type]
    assert all(min(p["size_mm"]) <= usable for p in fin["pieces"])
    inner = inner_skirts(d, params)
    assert len(inner) == 2  # the two walls of the inner corner
    vents = vents_3d(d, json.loads((d / "pattern.json").read_text()), params)["vents"]
    assert vents

    # the same input gives the same cover (rule 10)
    first = (d / "hull.glb").read_bytes(), (d / "hull_parts.npy").read_bytes()
    assert cover(["hull", str(d), "--force"]) == 0
    assert ((d / "hull.glb").read_bytes(), (d / "hull_parts.npy").read_bytes()) == first
    assert plan_checks(d, params)[0]["ok"]  # the audit agrees

    # the smoothed plan, chosen on the page, gives the first version's box (a diagonal wall
    # across the open corner); the audit notes it as chosen, and flags it when follow was meant
    doc = json.loads((d / ar.ARRANGEMENT_JSON).read_text())
    (d / ar.ARRANGEMENT_JSON).write_text(json.dumps({**doc, "footprint": "smooth"}))
    assert cover(["hull", str(d)]) == 0  # arrangement.json is an input of the hull step
    assert json.loads((d / "hull.json").read_text())["box"]["chosen_by"] != "plan"
    assert not (d / "hull_parts.npy").is_file()
    assert _plan(d).contains(shapely.Point(100 - c - 60, 200 - c - 60))
    assert plan_checks(d, params)[0]["ok"]
    (d / ar.ARRANGEMENT_JSON).write_text(json.dumps(doc))
    assert not plan_checks(d, params)[0]["ok"]


def test_the_page_offers_three_plans_before_building(models: Path) -> None:
    params = Registry.load().resolve()
    c = float(params["hull.clearance_mm"])  # type: ignore[arg-type]
    options = {o["footprint"]: o for o in ar.footprints(models, _l_members(), 0.0, params)}
    assert set(options) == set(ar.FOOTPRINTS)
    follow, box, smooth = (shapely.Polygon(options[k]["outline_mm"]) for k in ar.FOOTPRINTS)
    assert options["follow"]["empty_m2"] == 0  # nothing over empty floor
    assert options["box"]["size_mm"] == pytest.approx([1400 + 2 * c, 1600 + 2 * c], abs=1)
    assert box.area > smooth.area > follow.area  # the smoothed one cuts the corner diagonally
    corner = shapely.Point(100 - c - 60, 200 - c - 60)
    assert smooth.contains(corner) and box.contains(corner) and not follow.contains(corner)
    with pytest.raises(Exception, match="footprint"):
        ar.write(models, "arr-bad", "Bad", _l_members(), footprint="round")


def test_older_arrangements_without_plan_rectangles_still_get_them() -> None:
    size = {"size_mm": [800, 600, 700]}
    doc = {"members": [{"model_id": "a", "version": size},
                       {"model_id": "b", "x_mm": 700, "y_mm": -100, "rot_deg": 90,
                        "version": size}]}  # fmt: skip
    a, b = (np.asarray(r) for r in ar.plan_rects(doc))
    assert a.min(axis=0) == pytest.approx([-700, -200]) and a.max(axis=0) == pytest.approx(
        [100, 400]
    )
    assert b.min(axis=0) == pytest.approx([100, -400]) and b.max(axis=0) == pytest.approx(
        [700, 400]
    )
