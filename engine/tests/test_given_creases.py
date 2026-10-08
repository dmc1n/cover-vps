"""A cover surface of its own is cut along its own creases (Rens, 8 Oct 2026, S53/S60; ADR-100)."""

import numpy as np
import trimesh
from coverengine.seams.build import _crease_regions


def _open_bottom(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    keep = ~((np.abs(mesh.face_normals[:, 2]) > 0.99) & (mesh.triangles_center[:, 2] < 1.0))
    out = trimesh.Trimesh(mesh.vertices, mesh.faces[keep], process=True)
    v, f = trimesh.remesh.subdivide_to_size(out.vertices, out.faces, max_edge=60.0)
    return trimesh.Trimesh(v, f, process=True)


def test_a_creased_surface_is_cut_on_its_creases() -> None:
    # a box 1000 x 600 x 500 whose top is a 15 degree slope: top, four walls, open below
    box = trimesh.creation.box(extents=(1000, 600, 500))
    box.apply_translation((0, 0, 250))
    v = box.vertices.copy()
    v[(v[:, 2] > 1) & (v[:, 1] > 0), 2] += 600 * np.tan(np.radians(15))
    surface = _open_bottom(trimesh.Trimesh(v, box.faces, process=True))
    label = _crease_regions(surface, 20.0)
    assert label is not None and len(np.unique(label)) == 5  # the top and four walls
    # creases gentler than the limit do not cut: above every crease angle it is one piece
    assert _crease_regions(surface, 120.0) is None


def test_a_smooth_surface_keeps_the_usual_seams() -> None:
    dome = trimesh.creation.icosphere(subdivisions=4, radius=500)
    keep = dome.triangles_center[:, 2] > 0
    half = trimesh.Trimesh(dome.vertices, dome.faces[keep], process=True)
    assert _crease_regions(half, 20.0) is None
