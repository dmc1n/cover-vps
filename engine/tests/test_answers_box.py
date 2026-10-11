"""Rens's answers of 9 Oct 2026 (ADR-117): a box top wider than the roll is cut into strips; a box
cover shaped by hand for one model keeps its pieces and is checked like any cover."""

import json
from pathlib import Path

import numpy as np
import trimesh
from coverengine.cli import main as cover
from coverengine.hull import hand
from coverengine.io.model_io import import_model, load_model
from coverengine.params import Registry


def _model(tmp: Path, name: str, mesh: trimesh.Trimesh, hull: dict) -> Path:
    src = tmp / f"{name}.stl"
    mesh.export(src)
    d = tmp / "models" / name
    import_model(src, d, Registry.load().resolve())
    (d / "cover.json").write_text(
        json.dumps({"format_version": 1, "parameters": {"hull": {"top": "box", **hull}}})
    )
    return d


def test_a_box_top_wider_than_the_roll_is_cut_in_strips(tmp_path: Path) -> None:
    """The Portofino daybed: its sloping top was one 1.85 m piece on a 1.48 m roll (Desk question
    16, "split the panel"). A wedge 2.6 m long and 1.9 m deep: the slope is cut across into
    strips whose seams run downhill; every piece fits the roll."""
    params = Registry.load().resolve()
    usable = float(params["roll.usable_width_mm"])  # type: ignore[arg-type]
    pts = [
        [x, y, z] for x in (-1300, 1300) for y, z in ((-950, 0), (-950, 300), (950, 0), (950, 700))
    ]
    wedge = trimesh.convex.convex_hull(np.array(pts, float))
    d = _model(tmp_path, "wide-wedge", wedge, {"plan": "box", "box_pieces": 6})
    for step in ("hull", "cut", "flatten"):
        assert cover([step, str(d)]) == 0, step
    hull = json.loads((d / "hull.json").read_text())
    cuts = hull["box"].get("roll_cuts") or []
    assert cuts, "the wide slope gets cut lines"
    for c in cuts:  # the seam runs down the slope: across the slope's own downhill direction
        n = np.asarray(c["normal"])
        down = -n[:2] / np.linalg.norm(n[:2])
        assert abs(float(down @ np.asarray(c["across"]))) < 1e-6
    pattern = json.loads((d / "pattern.json").read_text())
    assert all(p["flat_width_mm"] <= usable for p in pattern["panels"])  # rule 5
    assert sum(p["name"].startswith("top") for p in pattern["panels"]) >= 2


def _block() -> trimesh.Trimesh:
    b = trimesh.creation.box(extents=(1000, 800, 700))
    b.apply_translation((0, 0, 350))
    return b


def _shape(front_left: float = 720.0) -> dict:
    """Two top pieces meeting at x = 0, their corners not in one plane (ruled), every wall with
    one straight top edge."""
    fl, fm, fr, bl, bm, br = front_left, 730.0, 740.0, 850.0, 845.0, 840.0
    x0, x1, y0, y1, h = -510.0, 510.0, -410.0, 410.0, 50.0
    return {
        "read": "test block",
        "pieces": {
            "top-left": [[[x0, y0, fl], [0, y0, fm], [0, y1, bm], [x0, y1, bl]]],
            "top-right": [[[0, y0, fm], [x1, y0, fr], [x1, y1, br], [0, y1, bm]]],
            "skirt-front": [[[x0, y0, h], [x1, y0, h], [x1, y0, fr], [0, y0, fm], [x0, y0, fl]]],
            "skirt-right": [[[x1, y0, h], [x1, y1, h], [x1, y1, br], [x1, y0, fr]]],
            "skirt-back": [[[x1, y1, h], [x0, y1, h], [x0, y1, bl], [0, y1, bm], [x1, y1, br]]],
            "skirt-left": [[[x0, y1, h], [x0, y0, h], [x0, y0, fl], [x0, y1, bl]]],
        },
    }


def test_a_hand_shaped_box_keeps_its_pieces(tmp_path: Path) -> None:
    """Desk questions 1, 22 and 23: the approver's layout (a straight top edge on each wall, a
    ridge where he draws it) built by hand for those models only, from box_shape.json."""
    d = _model(tmp_path, "hand-block", _block(), {})
    (d / hand.HAND_FILE).write_text(json.dumps(_shape()))
    for step in ("hull", "cut", "flatten"):
        assert cover([step, str(d)]) == 0, step
    hull = json.loads((d / "hull.json").read_text())
    assert hull["box"]["chosen_by"] == "hand"
    assert hull["drainage"]["drains"] and not hull["warnings"]
    assert hull["box"]["plan"]["furniture_outside_points"] == 0
    panels = json.loads((d / "panels.json").read_text())["panels"]
    assert len(panels) == 6  # one panel per piece given
    pattern = json.loads((d / "pattern.json").read_text())
    assert max(p["stretch"]["max_pct"] for p in pattern["panels"] if "stretch" in p) < 1.0
    # the front wall's top edge is one straight line (rule of Desk question 22)
    v = np.asarray(load_model(d / "hull.glb").vertices)
    front = v[np.abs(v[:, 1] + 410) < 0.5]
    line = 720.0 + (front[:, 0] + 510) / 1020 * 20.0  # from 72 cm at the left to 74 at the right
    assert float((front[:, 2] - line).max()) < 0.5  # nothing of the wall above the line
    on = np.abs(front[:, 2] - line) < 0.5
    assert len(np.unique(np.round(front[on, 0]))) > 10  # and the edge runs along it


def test_a_hand_shape_that_cuts_into_the_furniture_says_so(tmp_path: Path) -> None:
    d = _model(tmp_path, "hand-low", _block(), {})
    (d / hand.HAND_FILE).write_text(json.dumps(_shape(front_left=650.0)))
    assert cover(["hull", str(d)]) == 0
    hull = json.loads((d / "hull.json").read_text())
    assert hull["box"]["plan"]["furniture_outside_points"] > 0
    assert any("outside the cover" in w for w in hull["warnings"])


def _sofa() -> trimesh.Trimesh:
    """A sofa 1600 x 900: seat 420 high, a back 800 high along +y, an arm 650 high at -x."""
    seat = trimesh.creation.box(extents=(1600, 900, 420))
    seat.apply_translation((0, 0, 210))
    back = trimesh.creation.box(extents=(1600, 200, 800))
    back.apply_translation((0, 350, 400))
    arm = trimesh.creation.box(extents=(200, 900, 650))
    arm.apply_translation((-700, 0, 325))
    return trimesh.util.concatenate([seat, back, arm])


def test_straight_wall_tops_keep_the_shape(tmp_path: Path) -> None:
    """Desk questions 22 and 23 (Sorrento, Avero): every wall's top edge one straight line; the
    wall above it is folded down from the roof pieces. The surface is the box's own."""
    d = _model(tmp_path, "straight", _sofa(), {"plan": "box", "box_pieces": 7})
    doc = json.loads((d / "cover.json").read_text())
    doc["parameters"]["seams"] = {"straight_wall_tops": True}
    (d / "cover.json").write_text(json.dumps(doc))
    for step in ("hull", "cut", "flatten"):
        assert cover([step, str(d)]) == 0, step
    hull = json.loads((d / "hull.json").read_text())
    assert hull["box"]["chosen_by"] == "straight wall tops" and not hull["warnings"]
    pattern = json.loads((d / "pattern.json").read_text())
    assert max(p["stretch"]["max_pct"] for p in pattern["panels"] if "stretch" in p) < 0.5
    # every upright piece: its points above the hem lie on its bottom-to-top straight outline,
    # i.e. its top edge is one line (the highest points of each wall are collinear)
    spec = hand.straight_tops(_solid_of(d), 50.0)
    for name, faces in spec["pieces"].items():
        if not name.startswith("wall"):
            continue
        assert len(faces) == 1  # the wall below its chord: one flat face
        pts = np.asarray(faces[0])
        top = pts[pts[:, 2] > 51]
        # its corners above the hem lie on one straight line: one straight top edge
        d = top - top[0]
        assert np.linalg.svd(d, compute_uv=False)[1] < 1.0, name


def _solid_of(d: Path):  # type: ignore[no-untyped-def]
    """The convex box of a built cover (its hull points)."""
    from scipy.spatial import ConvexHull

    v = np.asarray(load_model(d / "hull.glb").vertices)
    return ConvexHull(v)


def test_a_corner_sofa_in_one_file_is_built_as_an_l(tmp_path: Path) -> None:
    """Desk question 21 (Vento lounge): an L-shaped sofa in one file, its two arms' plan given
    (plan_members.json): an L with a square inner corner, each arm's top its own."""
    import shapely

    a = trimesh.creation.box(extents=(2400, 900, 800))
    a.apply_translation((0, 450, 400))
    b = trimesh.creation.box(extents=(900, 1500, 800))
    b.apply_translation((750, -750, 400))
    d = _model(tmp_path, "corner", trimesh.util.concatenate([a, b]), {})
    (d / "plan_members.json").write_text(json.dumps({"rects": [
        [[-1200, 0], [1200, 0], [1200, 900], [-1200, 900]],
        [[300, -1500], [1200, -1500], [1200, 0], [300, 0]]]}))  # fmt: skip
    for step in ("hull", "cut", "flatten"):
        assert cover([step, str(d)]) == 0, step
    hull = json.loads((d / "hull.json").read_text())
    assert "plan_members.json" in hull["box"]["reason"]
    plan = shapely.Polygon(hull["box"]["plan"]["outline_mm"])
    assert not plan.contains(shapely.Point(-300, -600))  # the inner corner is not spanned
    usable = float(Registry.load().resolve()["roll.usable_width_mm"])  # type: ignore[arg-type]
    pattern = json.loads((d / "pattern.json").read_text())
    assert all(p["flat_width_mm"] <= usable for p in pattern["panels"])


def test_extra_box_faces_are_read_and_checked() -> None:
    """Desk question 3 (Nuna): a chamfer added by hand (hull.box_extra_faces)."""
    import pytest
    from coverengine.errors import CoverError
    from coverengine.hull.box import extra_faces

    reg = Registry.load()
    assert extra_faces(reg.resolve()) == []
    got = extra_faces(reg.resolve(trial={"hull": {"box_extra_faces": "0 1 1; -1 0 2"}}))
    assert np.allclose(got[0], [0, 2**-0.5, 2**-0.5]) and len(got) == 2
    with pytest.raises(CoverError):
        extra_faces(reg.resolve(trial={"hull": {"box_extra_faces": "0 0 -1"}}))
