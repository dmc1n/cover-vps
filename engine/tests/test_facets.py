"""Flat faces joined into fewer pieces with a fold (ADR-055): no slivers; on request one top."""

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
