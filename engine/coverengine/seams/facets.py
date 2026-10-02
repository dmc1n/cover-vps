"""Flat faces of a box cover joined into fewer pieces, with a fold between them instead of a
seam (ADR-055, docs/plans/fewer-top-pieces.md).

The owner, 2 October 2026 (the Lucia 2-seater): "the top can be cut in one piece"; "we must
learn from these mistakes". Two flat faces that share an edge unfold exactly into one flat
piece (0 % stretch), so they can be cut as one piece with a fold line in pen.

- A face narrower than `seams.min_piece_width_mm` (a sliver) always goes into the neighbour it
  shares the longest edge with, on the same side (top or skirt), if the two fit the roll.
- With `seams.fold_merge` (per model, on the owner's request) neighbouring top faces are joined
  as long as they fit the roll width and the longest piece.

The faces of a group are laid flat one by one, each turned about the edge it shares with one
already laid; the group's flat outline then gives its width and length on the roll.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely
import shapely.affinity
import trimesh
from numpy.typing import NDArray

Array = NDArray[np.float64]
MM_PER_CM = 10.0  # param-ok: unit conversion


@dataclass
class Facet:
    index: int
    faces: NDArray[np.int64]
    top: bool
    origin: Array
    u: Array
    v: Array


def _facet(hull: trimesh.Trimesh, index: int, faces: NDArray[np.int64], top: bool) -> Facet:
    n = (hull.face_normals[faces] * hull.area_faces[faces, None]).sum(axis=0)
    n = n / np.linalg.norm(n)
    upright = abs(n[2]) < 0.9  # param-ok: any helper axis not along n will do
    helper = np.array([0.0, 0.0, 1.0]) if upright else np.array([1.0, 0.0, 0.0])
    u = np.cross(helper, n)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    origin = hull.vertices[hull.faces[faces[0], 0]]
    return Facet(index, faces, top, origin, u, v)


def _local(f: Facet, pts: Array) -> Array:
    d = pts - f.origin
    return np.column_stack([d @ f.u, d @ f.v])


def _shape(hull: trimesh.Trimesh, f: Facet) -> shapely.Geometry:
    tris = _local(f, hull.vertices[hull.faces[f.faces].reshape(-1)]).reshape(-1, 3, 2)
    return shapely.union_all([shapely.Polygon(t) for t in tris]).buffer(0)


def _rigid(src: Array, dst: Array) -> tuple[Array, Array]:
    """The 2D rotation (no mirror) and shift taking the segment src onto dst."""
    a = src[1] - src[0]
    b = dst[1] - dst[0]
    ang = np.arctan2(b[1], b[0]) - np.arctan2(a[1], a[0])
    c, s = np.cos(ang), np.sin(ang)
    r = np.array([[c, -s], [s, c]])
    return r, dst[0] - r @ src[0]


def unfolded(
    hull: trimesh.Trimesh, group: list[Facet], shared: dict[tuple[int, int], Array]
) -> shapely.Geometry:
    """The group's faces laid flat together (each turned about an edge it shares with one laid
    before), as one 2D outline; `shared[(i, j)]` holds the two ends of the edge i and j share."""
    placed: dict[int, tuple[Array, Array]] = {}  # facet -> (rotation, shift) into the sheet
    shapes = []
    first = group[0]
    placed[first.index] = (np.eye(2), np.zeros(2))
    shapes.append(_shape(hull, first))
    todo = [f for f in group[1:]]
    while todo:
        for f in list(todo):
            hinge = next((p for p in placed if (min(p, f.index), max(p, f.index)) in shared), None)
            if hinge is None:
                continue
            ends = shared[(min(hinge, f.index), max(hinge, f.index))]
            ph = next(g for g in group if g.index == hinge)
            rh, th = placed[hinge]
            dst = (rh @ _local(ph, ends).T).T + th  # the edge where it lies in the sheet
            src = _local(f, ends)
            own = _shape(hull, f)
            for flip in (False, True):  # the face must come out on the far side of the hinge
                s2 = src * ([1.0, -1.0] if flip else [1.0, 1.0])
                r, t = _rigid(s2, dst)
                m = r @ (np.diag([1.0, -1.0]) if flip else np.eye(2))
                cand = shapely.affinity.affine_transform(
                    own, [m[0, 0], m[0, 1], m[1, 0], m[1, 1], t[0], t[1]]
                )
                overlap = cand.intersection(shapely.union_all(shapes)).area
                if overlap < 1e-3 * cand.area:  # param-ok: laid on the far side, not on top
                    break
            placed[f.index] = (m, t)
            shapes.append(cand)
            todo.remove(f)
            break
        else:
            raise ValueError("the faces of a group do not hang together")
    return shapely.union_all(shapes).buffer(0)


def size_on_roll(outline: shapely.Geometry) -> tuple[float, float]:
    """(width, length) of the narrowest rectangle round the outline (rotation is free)."""
    box = np.asarray(shapely.minimum_rotated_rectangle(outline).exterior.coords)[:4]
    a = float(np.linalg.norm(box[1] - box[0]))
    b = float(np.linalg.norm(box[2] - box[1]))
    return min(a, b), max(a, b)


def join(
    hull: trimesh.Trimesh,
    label: NDArray[np.int64],
    top: NDArray[np.bool_],
    min_width: float,
    roll_width: float,
    max_length: float,
    fold_merge: bool,
) -> tuple[NDArray[np.int64], list[str], list[list[list[float]]]]:
    """New labels: slivers joined into a neighbour, and (fold_merge) top faces joined while they
    fit the roll. `top[r]` says whether flat face r is part of the top. Returns the labels,
    what was done (in words) and the folds: the two 3D ends of every edge that is now inside a
    piece."""
    regions = [int(r) for r in np.unique(label)]
    facets = {r: _facet(hull, r, np.flatnonzero(label == r), bool(top[r])) for r in regions}
    pairs = np.asarray(hull.face_adjacency)
    ends_of = np.sort(np.asarray(hull.face_adjacency_edges), axis=1)
    shared: dict[tuple[int, int], Array] = {}
    length: dict[tuple[int, int], float] = {}
    lab_a, lab_b = label[pairs[:, 0]], label[pairs[:, 1]]
    for key in {(min(a, b), max(a, b)) for a, b in zip(lab_a, lab_b, strict=True) if a != b}:
        sel = ((lab_a == key[0]) & (lab_b == key[1])) | ((lab_a == key[1]) & (lab_b == key[0]))
        pts = hull.vertices[np.unique(ends_of[sel])]
        d = pts - pts.mean(axis=0)
        axis = np.linalg.svd(d, full_matrices=False)[2][0]
        t = d @ axis
        shared[key] = np.array([pts[np.argmin(t)], pts[np.argmax(t)]])
        length[key] = float(t.max() - t.min())
    groups: dict[int, list[int]] = {r: [r] for r in regions}  # group id -> flat faces
    owner = {r: r for r in regions}
    notes: list[str] = []

    def size(members: list[int]) -> tuple[float, float]:
        return size_on_roll(unfolded(hull, [facets[m] for m in members], shared))

    def neighbours(g: int) -> list[tuple[float, int]]:
        out: dict[int, float] = {}
        for (a, b), L in length.items():
            if owner[a] == g and owner[b] != g:
                out[owner[b]] = out.get(owner[b], 0.0) + L
            elif owner[b] == g and owner[a] != g:
                out[owner[a]] = out.get(owner[a], 0.0) + L
        return sorted(((L, h) for h, L in out.items()), reverse=True)

    def merge(g: int, h: int) -> None:
        for m in groups.pop(h):
            groups[g].append(m)
            owner[m] = g

    def fits(members: list[int], *parts: list[int]) -> bool:
        """Fits the roll, and is no longer than the longest piece (or than it already was)."""
        w, length_now = size(members)
        longest = max([max_length] + [size(p)[1] for p in parts])
        return w <= roll_width and length_now <= longest + 1.0  # param-ok: 1 mm rounding

    # 1 slivers, narrowest first: into the neighbour on the same side with the longest shared
    # edge; if none fits, into the neighbour with the longest shared edge on either side (a
    # narrow strip under a sloping top goes into the top, with a fold)
    for r in sorted(regions, key=lambda q: size([q])[0]):
        g = owner[r]
        width = size(groups[g])[0]
        if width >= min_width:
            continue
        near = neighbours(g)
        order = [h for _, h in near if facets[h].top == facets[r].top]
        order += [h for _, h in near if facets[h].top != facets[r].top]
        for h in order:
            if fits(groups[h] + groups[g], groups[h], groups[g]):
                merge(h, g)
                notes.append(
                    f"a {width / MM_PER_CM:.1f} cm narrow face joined to its neighbour (fold)"
                )
                break
        else:
            notes.append(f"a {width / MM_PER_CM:.1f} cm narrow face could not be joined: check it")
    # 2 on request: top faces together while they fit the roll
    if fold_merge:
        changed = True
        while changed:
            changed = False
            for g in sorted(groups, key=lambda q: -sum(hull.area_faces[facets[m].faces].sum()
                                                         for m in groups[q])):  # fmt: skip
                if g not in groups or not facets[g].top:
                    continue
                for _, h in neighbours(g):
                    if not facets[h].top:
                        continue
                    if fits(groups[g] + groups[h], groups[g], groups[h]):
                        merge(g, h)
                        notes.append("two top faces joined into one piece (fold)")
                        changed = True
                        break
                if changed:
                    break
    new = label.copy()
    for g, members in groups.items():
        for m in members:
            new[label == m] = g
    folds = [
        [[round(float(c), 2) for c in p] for p in shared[(a, b)]]
        for (a, b) in sorted(shared)
        if owner[a] == owner[b]
    ]
    return new, notes, folds
