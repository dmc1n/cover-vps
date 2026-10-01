"""The guess after an upload: the furniture or only the cover surface (ADR-039)."""

import json
from pathlib import Path

import numpy as np
import trimesh
from coverengine.io.kind import COVER, PRODUCT, confirm, guess, read, write_guess
from coverengine.params.registry import read_cover_definition


def _open_box() -> trimesh.Trimesh:
    """A cover surface: a box of 1000 x 600 x 800 mm without its bottom."""
    box = trimesh.creation.box((1000, 600, 800))
    box.apply_translation((0, 0, 400))
    keep = box.face_normals[:, 2] > -0.5
    return trimesh.Trimesh(box.vertices, box.faces[keep])


def _table() -> trimesh.Trimesh:
    """A table: a top on four legs."""
    parts = [trimesh.creation.box((1200, 800, 40), trimesh.transformations.translation_matrix(
        (0, 0, 730)))]  # fmt: skip
    for x in (-550, 550):
        for y in (-350, 350):
            leg = trimesh.creation.box((50, 50, 710))
            leg.apply_translation((x, y, 355))
            parts.append(leg)
    return trimesh.util.concatenate(parts)


def test_a_cover_surface_is_recognised() -> None:
    g = guess(_open_box())
    assert g["guess"] == COVER and g["sure"]
    assert g["measures"]["sides_closed"] == 1.0 and g["measures"]["floor_share"] == 0.0


def test_furniture_is_recognised() -> None:
    assert guess(_table())["guess"] == PRODUCT
    closed = trimesh.creation.box((500, 500, 400))  # a pouf: closed, with a bottom
    closed.apply_translation((0, 0, 200))
    assert guess(closed)["guess"] == PRODUCT


def test_confirm_sets_the_cover_mode(tmp_path: Path) -> None:
    write_guess(tmp_path, _open_box())
    assert read(tmp_path)["confirmed"] is False  # type: ignore[index]
    confirm(tmp_path, COVER)
    assert read_cover_definition(tmp_path)["parameters"]["hull"]["top"] == "given"
    write_guess(tmp_path, _open_box())  # a new import keeps the answer
    assert read(tmp_path)["kind"] == COVER  # type: ignore[index]
    confirm(tmp_path, PRODUCT)
    assert "top" not in read_cover_definition(tmp_path)["parameters"]["hull"]
    assert np.isfinite(guess(_table())["measures"]["skin_ratio"])


def test_a_cover_drawn_as_a_box_becomes_one_piece_per_face(tmp_path: Path) -> None:
    from coverengine.cli import main

    box = trimesh.creation.box((940, 2550, 480))  # a cover drawn as a solid, with its bottom
    box.apply_translation((0, 0, 240))
    src = tmp_path / "cover D8.stl"
    box.export(src)
    model = tmp_path / "d8"
    assert main(["import", str(src), "--out", str(model), "--units", "mm"]) == 0
    assert read(model)["guess"] == COVER  # type: ignore[index]  # the name decides a block
    confirm(model, COVER)
    assert main(["hull", str(model)]) == 0
    assert main(["cut", str(model)]) == 0
    panels = json.loads((model / "panels.json").read_text())["panels"]
    assert sorted(p["name"] for p in panels) == [
        "skirt-back",
        "skirt-front",
        "skirt-left",
        "skirt-right",
        "top",
    ]


def test_a_symmetric_product_gets_its_slopes_in_mirror_pairs() -> None:
    """Lesson from the Vento daybed (ADR-041): one front corner sloped, the other did not."""
    from coverengine.hull.box import Box

    rng = np.random.default_rng(1)
    pts = rng.uniform((-1000, -900, 50), (1000, 900, 400), (4000, 3))
    back = rng.uniform((-1000, 500, 400), (1000, 900, 850), (2000, 3))  # a high back
    half = np.vstack([pts, back])
    half = half[half[:, 0] >= 0]
    box = Box(np.vstack([half, half * (-1, 1, 1)]), 50.0, 10.0)  # left = right mirrored
    assert [k for k, _ in box.mirrors] == [0]  # left-right, not front-back
    slope = np.array([0.6, -0.5, 0.62])
    pair = box.mirror(slope / np.linalg.norm(slope))
    assert len(pair) == 2 and np.isclose(pair[0][0], -pair[1][0])
    for planes in box.grow(9):
        xs = sorted(round(float(p[0]), 3) for p in planes)
        assert xs == sorted(-x for x in xs)  # every face has its mirror image


def test_an_l_shaped_cover_from_a_drawing_becomes_the_drawn_pieces(tmp_path: Path) -> None:
    """The owner's C6 (ADR-045): recognised as a cover surface, the strip and the slope split
    at 45 degrees at the corner, one piece per wall, every piece flat."""
    import sys

    from coverengine.cli import main

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from c6_surface import mesh

    src = tmp_path / "c6.stl"
    mesh().export(src)
    model = tmp_path / "c6"
    assert main(["import", str(src), "--out", str(model), "--units", "mm"]) == 0
    assert read(model)["guess"] == COVER  # type: ignore[index]
    confirm(model, COVER)
    assert main(["hull", str(model)]) == 0
    assert main(["cut", str(model)]) == 0
    panels = json.loads((model / "panels.json").read_text())["panels"]
    assert len(panels) == 10
    tops = sorted(round(p["area_m2"], 2) for p in panels if p["region"] == "top")
    # strips 30 cm wide with 45 degree ends (0.825, 1.095 m2); slopes 80 cm across, 93.3 cm
    # along the slope (1.76 and 2.48 m2 seen from above)
    assert tops == [0.82, 1.09, 2.05, 2.89]
