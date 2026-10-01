"""The audit's measurements (ADR-042)."""

import numpy as np
import trimesh
from coverengine.audit import mirror_gap, outside


def _open_box(size: tuple[float, float, float]) -> trimesh.Trimesh:
    box = trimesh.creation.box(size)
    box.apply_translation((0, 0, size[2] / 2))
    keep = box.face_normals[:, 2] > -0.5
    v, f = trimesh.remesh.subdivide_to_size(box.vertices, box.faces[keep], max_edge=50)
    return trimesh.Trimesh(v, f)


def test_furniture_sticking_out_of_the_cover_is_found() -> None:
    cover = _open_box((1000, 600, 800))
    inside = trimesh.creation.box((900, 500, 700))
    inside.apply_translation((0, 0, 360))
    _, d = outside(inside, cover)
    assert d.max() < 0
    leg = trimesh.creation.box((40, 40, 300))
    leg.apply_translation((520, 0, 200))  # 40 mm out of the side
    _, d = outside(leg, cover)
    assert np.isclose(d.max(), 40, atol=1)


def test_a_symmetric_cover_mirrors_onto_itself() -> None:
    cover = _open_box((1000, 600, 800))
    assert mirror_gap(cover, 0, 0.0) < 1
    cover.apply_translation((100, 0, 0))
    assert mirror_gap(cover, 0, 0.0) > 50
