"""The cover surface of the owner's drawing C6 (cover 8), built from its sizes (ADR-045).

L shape seen from above: 290 x 380 cm outside, arms 110 cm deep. Back (the outside edges) 85 cm
high, front (the inside edges) 37 cm. On top a flat strip 30 cm wide along the back (measured on
the top view), then a straight slope to the front; the arms meet in a 45 degree seam at the
corner. Open at the bottom. Written in mm, Z up, the outside corner at the origin.

    uv run python scripts/c6_surface.py out/c6/C6-cover.stl
"""

from __future__ import annotations

import sys

import numpy as np
import trimesh

X, Y = 2900.0, 3800.0  # outside sizes (drawing: 289.99 and 379.98 cm)
ARM = 1100.0  # depth of both arms (109.98 cm)
BACK, FRONT = 850.0, 370.0  # heights (84.99 and 37.01 cm)
STRIP = 300.0  # flat strip along the back (measured on the top view)


def h(d: float) -> float:
    """Height of the top at distance d from the back edge."""
    if d <= STRIP:
        return BACK
    return BACK + (FRONT - BACK) * (d - STRIP) / (ARM - STRIP)


def faces() -> list[list[tuple[float, float, float]]]:
    """Every flat face as its corners in order (x to the right, y to the front = -y)."""
    s, a = STRIP, ARM
    out = [
        # top: strips along the back of each arm, meeting on the diagonal
        [(0, 0, BACK), (X, 0, BACK), (X, s, BACK), (s, s, BACK)],
        [(0, 0, BACK), (s, s, BACK), (s, Y, BACK), (0, Y, BACK)],
        # top: the slopes, meeting on the diagonal
        [(s, s, BACK), (X, s, BACK), (X, a, FRONT), (a, a, FRONT)],
        [(s, s, BACK), (a, a, FRONT), (a, Y, FRONT), (s, Y, BACK)],
        # back walls (outside edges)
        [(0, 0, 0), (X, 0, 0), (X, 0, BACK), (0, 0, BACK)],
        [(0, 0, 0), (0, 0, BACK), (0, Y, BACK), (0, Y, 0)],
        # front walls (inside edges)
        [(a, a, 0), (a, a, FRONT), (X, a, FRONT), (X, a, 0)],
        [(a, a, 0), (a, Y, 0), (a, Y, FRONT), (a, a, FRONT)],
        # the ends of the arms
        [(X, 0, 0), (X, a, 0), (X, a, FRONT), (X, s, BACK), (X, 0, BACK)],
        [(0, Y, 0), (0, Y, BACK), (s, Y, BACK), (a, Y, FRONT), (a, Y, 0)],
    ]
    return [[(x, -y, z) for x, y, z in f] for f in out]


def mesh() -> trimesh.Trimesh:
    verts: list[tuple[float, float, float]] = []
    tris = []
    for f in faces():
        i0 = len(verts)
        verts += f
        tris += [(i0, i0 + k, i0 + k + 1) for k in range(1, len(f) - 1)]
    m = trimesh.Trimesh(np.array(verts), np.array(tris), process=True)
    trimesh.repair.fix_normals(m)
    return m


if __name__ == "__main__":
    m = mesh()
    m.export(sys.argv[1])
    print(f"{sys.argv[1]}: {m.bounds[1] - m.bounds[0]} mm, area {m.area / 1e6:.2f} m2")
