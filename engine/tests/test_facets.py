"""Flat faces joined into fewer pieces with a fold (ADR-055): no slivers; on request one top."""

import json
from pathlib import Path

import numpy as np
import trimesh
from coverengine.drawn import build, scene
from coverengine.seams import facets
from coverengine.seams.build import BOX_UPRIGHT_NZ, _flat_regions


def _cover(strip_cm: float) -> tuple[trimesh.Trimesh, np.ndarray, np.ndarray]:
    sizes = {"length_cm": 200, "depth_cm": 100, "back_height_cm": 88, "front_height_cm": 61,
             "back_strip_cm": strip_cm}  # fmt: skip
    sc = scene(build("sloped box", sizes, 1450.0))
    m = trimesh.util.concatenate(list(sc.geometry.values()))
    hull = trimesh.Trimesh(m.vertices, m.faces, process=True)
    label = _flat_regions(hull)
    w = np.zeros((label.max() + 1, 3))
    np.add.at(w, label, hull.face_normals * hull.area_faces[:, None])
    top = np.abs(w[:, 2]) / np.linalg.norm(w, axis=1) >= BOX_UPRIGHT_NZ
    return hull, label, top


def test_a_sliver_is_joined_to_its_neighbour_with_a_fold() -> None:
    hull, label, top = _cover(4)  # a 4 cm strip along the back
    new, notes, folds = facets.join(hull, label, top, 100, 1450, 3000, fold_merge=False)
    assert len(np.unique(new)) == len(np.unique(label)) - 1
    assert "narrow face joined" in notes[0] and len(folds) == 1


def test_on_request_the_top_is_one_piece_and_lies_flat_exactly() -> None:
    hull, label, top = _cover(30)
    kept, _, _ = facets.join(hull, label, top, 100, 1450, 3000, fold_merge=False)
    assert len(np.unique(kept)) == len(np.unique(label))  # a 30 cm strip stays its own piece
    new, _, folds = facets.join(hull, label, top, 100, 1450, 3000, fold_merge=True)
    assert len(np.unique(new)) == len(np.unique(label)) - 1 and len(folds) == 1
    # the joined top unfolds without overlap: its flat area is its 3D area
    members = [int(r) for r in np.unique(label[new == new[np.flatnonzero(top[label])[0]]])]
    fs = [facets._facet(hull, r, np.flatnonzero(label == r), True) for r in members]
    a, b = members
    pairs, ends = np.asarray(hull.face_adjacency), np.sort(hull.face_adjacency_edges, axis=1)
    sel = np.isin(label[pairs[:, 0]], members) & np.isin(label[pairs[:, 1]], members)
    sel &= label[pairs[:, 0]] != label[pairs[:, 1]]
    pts = hull.vertices[np.unique(ends[sel])]
    t = (pts - pts.mean(axis=0)) @ np.linalg.svd(pts - pts.mean(axis=0))[2][0]
    shared = {(min(a, b), max(a, b)): np.array([pts[np.argmin(t)], pts[np.argmax(t)]])}
    flat = facets.unfolded(hull, fs, shared)
    area3 = float(hull.area_faces[np.isin(label, members)].sum())
    assert abs(flat.area - area3) < 1e-6 * area3


def test_a_join_that_would_not_fit_the_roll_is_not_made() -> None:
    hull, label, top = _cover(30)
    new, _, _ = facets.join(hull, label, top, 100, 700, 3000, fold_merge=True)  # a narrow roll
    assert len(np.unique(new)) == len(np.unique(label))


def _gable_table() -> tuple[trimesh.Trimesh, np.ndarray, np.ndarray]:
    """A box cover over an 80 x 80 cm table: its flat top drained into a 10 degree gable."""
    from coverengine.hull.box import Box, drain, mesh_of

    corners = np.array([[x, y, z] for x in (-400, 400) for y in (-400, 400) for z in (0, 1100)],
                       dtype=float)  # fmt: skip
    box = Box(corners, 50.0, 10.0)
    hull = mesh_of(box, drain(box, box.start(), 5.0))
    hull = trimesh.Trimesh(hull.vertices, hull.faces, process=True)
    label = _flat_regions(hull)
    w = np.zeros((label.max() + 1, 3))
    np.add.at(w, label, hull.face_normals * hull.area_faces[:, None])
    top = np.abs(w[:, 2]) / np.linalg.norm(w, axis=1) >= BOX_UPRIGHT_NZ
    return hull, label, top


def test_a_gentle_gable_is_one_piece_with_a_fold() -> None:
    """Rens, 8 Oct 2026 (bar tables, bar chairs, corners): "crossed-out panels can become one
    panel": two top faces meeting at a 10 degree fold lie flat together (ADR-099)."""
    hull, label, top = _gable_table()
    assert int(top.sum()) == 2  # the gable
    kept, _, _ = facets.join(hull, label, top, 100, 1450, 3000, fold_merge=False, gentle_deg=0)
    assert len(np.unique(kept)) == len(np.unique(label))
    new, notes, folds = facets.join(hull, label, top, 100, 1450, 3000, fold_merge=False,
                                    gentle_deg=15)  # fmt: skip
    assert len(np.unique(new)) == len(np.unique(label)) - 1 and len(folds) == 1
    assert "10 degree fold joined" in notes[0]
    # the upright sides meet at 90 degrees: never joined by this rule
    steep, _, _ = facets.join(hull, label, top, 100, 1450, 3000, fold_merge=False, gentle_deg=9)
    assert len(np.unique(steep)) == len(np.unique(label))


def test_a_gentle_fold_that_would_not_fit_the_roll_stays_a_seam() -> None:
    hull, label, top = _gable_table()
    new, _, _ = facets.join(hull, label, top, 100, 600, 3000, fold_merge=False, gentle_deg=15)
    assert len(np.unique(new)) == len(np.unique(label))


def test_the_audit_finds_a_seam_on_a_gentle_fold(tmp_path: Path) -> None:
    """The audit's gentle folds check (ADR-099): a gable top in two pieces fails, in one passes."""
    from coverengine.audit import fold_checks
    from coverengine.params import Registry

    hull, label, top = _gable_table()
    params = Registry.load(None).resolve()
    for gentle, ok in ((0.0, False), (15.0, True)):
        new, _, _ = facets.join(hull, label, top, 100, 1450, 3000, False, gentle)
        new = np.unique(new, return_inverse=True)[1].ravel()
        np.savez(tmp_path / "panels.npz", vertices=hull.vertices, faces=hull.faces, labels=new,
                 original_vertex=np.arange(len(hull.vertices)))  # fmt: skip
        region = ["top" if top[label[new == k][0]] else "skirt" for k in range(new.max() + 1)]
        panels = [{"name": f"p{k}", "region": region[k], "flat_width_mm": 420.0}
                  for k in range(new.max() + 1)]  # fmt: skip
        (tmp_path / "panels.json").write_text(json.dumps({"panels": panels}))
        (tmp_path / "hull.json").write_text(json.dumps({"top": "box"}))
        (check,) = fold_checks(tmp_path, params)
        assert check["ok"] is ok, check
