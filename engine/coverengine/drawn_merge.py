"""Fewer pieces for covers built from drawings (ADR-076).

The owner, 5 October 2026, on drawing-s43: "this has far too many panels, it must be much
simpler". S43 came out in 37 pieces: the shape the AI read had profile points 4 cm and 0.5 mm
apart, and its curve was cut into many strips, each of which became a piece.

Neighbouring pieces are joined while the joint is no real crease and the joined piece still
lies flat on the table:

- the fold between them is gentler than `drawn.merge_fold_deg` (a crease stays a seam: the
  flat back strip and the slope of a sofa, a wall and the top);
- the joined piece is one sheet with one outline (a ring round the cover is never closed);
- flattened, it stretches no more than `drawn.merge_max_stretch_pct` (a cone, a cylinder and a
  flat strip are exact; a doubly curved part is not);
- it fits the roll in its narrowest direction.

Pairs with the gentlest fold go first; it repeats until no pair can be joined.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import trimesh

from coverengine.flatten.solve import flatten, singular_values

ROUND_MM = 0.05  # param-ok: points this close are the same point
SLIM_ITERATIONS = 60  # param-ok: enough to tell a flat-able piece from one that is not
SLIM_TOLERANCE = 1e-6  # param-ok
STRETCH_SHARE = 0.98  # param-ok: the stretch most of the piece (by area) stays under
SUBDIVIDE_PARTS = 12.0  # param-ok: a piece is measured with triangles this fine (of its size)
SUBDIVIDE_MIN_MM = 50.0  # param-ok: mm, the finest measuring triangles
PERCENT = 100.0  # param-ok: a share as a percentage
FLAT_TRIANGLE_MM = 0.01  # param-ok: a triangle lower than this has no area


def _weld(m: trimesh.Trimesh) -> trimesh.Trimesh:
    v = np.round(np.asarray(m.vertices) / ROUND_MM) * ROUND_MM
    out = trimesh.Trimesh(v, m.faces, process=True)
    out.merge_vertices()
    return out


def _key(p: np.ndarray) -> tuple[float, ...]:
    return tuple(np.round(p / ROUND_MM).astype(np.int64).tolist())


def _edges(m: trimesh.Trimesh) -> dict[Any, np.ndarray]:
    """Outline edges of a piece by their two end points, with the normal of their face."""
    out = {}
    rim = trimesh.grouping.group_rows(m.edges_sorted, require_count=1)
    for i in rim:
        a, b = m.edges_sorted[i]
        k = tuple(sorted((_key(m.vertices[a]), _key(m.vertices[b]))))
        out[k] = m.face_normals[m.edges_face[i]]
    return out


def _fold(a: trimesh.Trimesh, b: trimesh.Trimesh) -> tuple[float, float]:
    """The fold between two pieces along their shared outline (degrees, length-weighted) and
    the shared length (mm). No shared outline: (inf, 0)."""
    ea, eb = _edges(a), _edges(b)
    shared = set(ea) & set(eb)
    if not shared:
        return math.inf, 0.0
    total, angle = 0.0, 0.0
    for k in shared:
        p, q = np.array(k[0]) * ROUND_MM, np.array(k[1]) * ROUND_MM
        length = float(np.linalg.norm(q - p))
        na, nb = ea[k], eb[k]
        # the angle between the two faces' normals (either may face in: a fold is under 90°
        # for a cover's creases, so the sign does not matter)
        angle += math.degrees(math.acos(float(np.clip(abs(na @ nb), 0.0, 1.0)))) * length
        total += length
    return angle / max(total, 1e-9), total


def _one_sheet(m: trimesh.Trimesh) -> bool:
    if (
        len(trimesh.graph.connected_components(m.face_adjacency, nodes=np.arange(len(m.faces))))
        != 1
    ):
        return False
    rim = m.edges[trimesh.grouping.group_rows(m.edges_sorted, require_count=1)]
    return len(trimesh.graph.connected_components(rim)) == 1


def flat_ok(m: trimesh.Trimesh, max_stretch_pct: float, roll_mm: float) -> tuple[bool, float]:
    """Does the piece lie flat (stretch within the limit) and fit the roll? (ok, stretch %)."""
    stretch, narrow = flat_measure(m)
    return bool(stretch <= max_stretch_pct and narrow <= roll_mm), stretch


def flat_measure(m: trimesh.Trimesh) -> tuple[float, float]:
    """The piece flattened: its stretch over most of its area (%) and its width in its
    narrowest direction (mm). A piece that cannot be flattened: (inf, inf)."""
    # triangles with no area (points on one line, as S43's strips have) make the solver blow
    # up; they cover nothing, so they are left out of the measure
    m = m.copy()
    m.update_faces(m.nondegenerate_faces(height=FLAT_TRIANGLE_MM))
    m.remove_unreferenced_vertices()
    trimesh.repair.fix_winding(m)  # triangles turned either way fold the flat piece over
    if len(m.faces) == 0:
        return math.inf, math.inf
    # long thin triangles flatten badly: split them so the measure is fair
    edge = max(float(m.scale) / SUBDIVIDE_PARTS, SUBDIVIDE_MIN_MM)
    v, f = trimesh.remesh.subdivide_to_size(m.vertices, m.faces, max_edge=edge)
    sub = trimesh.Trimesh(v, f, process=False)
    try:
        flat = flatten(sub, "slim", SLIM_ITERATIONS, SLIM_TOLERANCE)
    except Exception:  # noqa: BLE001 - a piece that cannot be flattened is not joined
        return math.inf, math.inf
    s1, s2, area = singular_values(flat.vertices, flat.faces, flat.uv)
    worst = np.maximum(s1, 1.0 / np.maximum(s2, 1e-9)) - 1.0
    order = np.argsort(worst)
    cum = np.cumsum(area[order]) / max(float(area.sum()), 1e-9)
    at = min(int(np.searchsorted(cum, STRETCH_SHARE)), len(order) - 1)
    stretch = float(worst[order][at]) * PERCENT
    import shapely

    hull = shapely.MultiPoint(flat.uv).minimum_rotated_rectangle
    rect = np.asarray(hull.exterior.coords)[:4]
    narrow = min(np.linalg.norm(rect[1] - rect[0]), np.linalg.norm(rect[2] - rect[1]))
    return stretch, float(narrow)


def absorb_slivers(
    parts: list[tuple[str, trimesh.Trimesh]],
    least_mm: float,
    roll_mm: float,
    max_stretch_pct: float,
    log: Any = None,
) -> list[tuple[str, trimesh.Trimesh]]:
    """A piece narrower than `least_mm` (seams.min_piece_width_mm) flattened is no panel to
    cut and sew: it goes into the neighbour it shares the longest edge with, when the two lie
    flat together and fit the roll (ADR-097). C27's trimmed noses left strip ends of 4 x 6 cm;
    S43 had four pieces of 0.01-0.05 m2. The neighbour keeps its name."""
    meshes = {n: _weld(m) for n, m in parts}
    order = [n for n, _ in parts]
    tried: set[str] = set()
    width: dict[str, float] = {}
    while True:
        thin = []
        for n in order:
            if n in tried:
                continue
            if n not in width:
                width[n] = flat_measure(meshes[n])[1]
            if width[n] < least_mm:
                thin.append((width[n], n))
        if not thin:
            break
        _, n = min(thin)
        tried.add(n)
        mates = []
        for o in order:
            if o == n:
                continue
            fold, shared = _fold(meshes[n], meshes[o])
            if shared > 0:
                mates.append((-shared, fold, o))
        for _neg, fold, o in sorted(mates):
            both = trimesh.util.concatenate([meshes[n], meshes[o]])
            assert isinstance(both, trimesh.Trimesh)
            m = _weld(both)
            if not _one_sheet(m):
                continue
            ok, stretch = flat_ok(m, max_stretch_pct, roll_mm)
            if not ok:
                continue
            if log:
                log(f"sliver {n} joined to {o} (fold {fold:.1f}°, stretch {stretch:.2f} %)")
            meshes[o] = m
            width.pop(o, None)
            meshes.pop(n)
            order.remove(n)
            break
    return [(n, meshes[n]) for n in order]


def merge(
    parts: list[tuple[str, trimesh.Trimesh]],
    roll_mm: float,
    fold_deg: float,
    max_stretch_pct: float,
    log: Any = None,
) -> list[tuple[str, trimesh.Trimesh]]:
    """Join neighbouring pieces as described above. `parts`: (name, mesh in mm)."""
    pieces = [(n, _weld(m)) for n, m in parts]
    tried: set[tuple[int, int]] = set()
    ids = list(range(len(pieces)))
    names = {i: pieces[i][0] for i in ids}
    meshes = {i: pieces[i][1] for i in ids}
    next_id = len(pieces)
    while True:
        cands = []
        keys = sorted(meshes)
        for x in range(len(keys)):
            for y in range(x + 1, len(keys)):
                i, j = keys[x], keys[y]
                if (i, j) in tried:
                    continue
                fold, shared = _fold(meshes[i], meshes[j])
                if fold <= fold_deg and shared > 0:
                    cands.append((fold, -shared, i, j))
        if not cands:
            break
        cands.sort()
        joined = False
        for fold, _neg, i, j in cands:
            tried.add((i, j))
            both = trimesh.util.concatenate([meshes[i], meshes[j]])
            assert isinstance(both, trimesh.Trimesh)
            m = _weld(both)
            if not _one_sheet(m):
                continue
            ok, stretch = flat_ok(m, max_stretch_pct, roll_mm)
            if not ok:
                continue
            big = i if meshes[i].area >= meshes[j].area else j
            name = names[big]
            if log:
                log(f"joined {names[i]} and {names[j]} (fold {fold:.1f}°, stretch {stretch:.2f} %)")
            for k in (i, j):
                meshes.pop(k)
                names.pop(k)
            meshes[next_id], names[next_id] = m, name
            next_id += 1
            joined = True
            break
        if not joined:
            break
    return [(names[k], meshes[k]) for k in sorted(meshes)]


def model_parts(model_glb: Any) -> list[tuple[str, trimesh.Trimesh]]:
    """A model's own parts (model.glb: metres, Y up) as (name, mesh in mm, Z up)."""
    sc = trimesh.load(model_glb)
    assert isinstance(sc, trimesh.Scene)
    out = []
    for node in sc.graph.nodes_geometry:
        transform, geom = sc.graph[node]
        m = sc.geometry[geom].copy()
        m.apply_transform(transform)
        v = np.asarray(m.vertices) * 1000.0  # param-ok: m to mm
        out.append((str(node), trimesh.Trimesh(np.column_stack([v[:, 0], -v[:, 2], v[:, 1]]),
                                                m.faces)))  # fmt: skip
    return out
