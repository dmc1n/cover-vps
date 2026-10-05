"""The cover built from the drawing's own views, checked against its 3D view (ADR-075).

`drawing_views.read` gives the silhouettes and the scale. Here:

1. **The solid.** The plan extruded up, cut by each elevation extruded across: the shape a CAD
   drawer built (a trapezoid sofa with a sloping back, a kidney with a sloping top, a lens).
   An elevation may be seen from the front or the side, and from either end; every way that
   fits the plan's sizes is built.
2. **The check against the 3D view.** Each candidate is drawn as the CAD program draws its 3D
   view (an isometric view, from each of the four corners); the one whose silhouette covers the
   drawing's 3D view best wins (intersection over union, no scaling: the 3D view is drawn at
   the sheet's scale). The score is kept: it says how sure the program is.
3. **The pieces.** The solid's surface without its bottom, split where it folds (edges sharper
   than `FOLD_DEG`): a flat top, a slope, each wall; a curved wall stays one piece. A closed
   band is cut in two (a ring cannot lie flat), and a piece wider than the roll is cut across.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from coverengine import drawing_views as dv
from coverengine.drawn import Piece

MM = 10.0  # param-ok: cm to mm
FOLD_DEG = 10.0  # param-ok: a fold sharper than this is a seam between pieces
WALL_FOLD_DEG = 35.0  # param-ok: between two upright faces only a real corner is a seam (a
# curved wall is drawn as many flat bits that turn a little each)
SMALL_SHARE = 0.01  # param-ok: a region smaller than this share of the cover joins a neighbour
ISO_ELEVATION = math.degrees(math.atan(1 / math.sqrt(2)))  # 35.26°: the isometric view
WIDTH_MATCH = 0.08  # param-ok: an elevation as wide as the plan within 8 %
UPRIGHT = 90.0  # param-ok: degrees, a section stood up
OVERHANG_MM = 20.0  # param-ok: an elevation's prism reaches this far past the plan each way
CORNERS_DEG = (45.0, 135.0, 225.0, 315.0)  # param-ok: the four corners an iso view is seen from


def _ccw(p: np.ndarray) -> np.ndarray:
    """Counter-clockwise (manifold fills only those)."""
    x, y = p[:, 0], p[:, 1]
    return p if np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y) > 0 else p[::-1]


def _prism(outline_cm: np.ndarray, height_mm: float) -> Any:
    import manifold3d as m3

    return m3.Manifold.extrude(m3.CrossSection([(_ccw(outline_cm) * MM).tolist()]), height_mm)


def _local(v: dv.View) -> np.ndarray:
    k = float(v.meta["scale"])
    return (v.outline - v.outline.min(axis=0)) * k


def candidates(read: dict[str, Any], height_cm: float | None = None) -> list[dict[str, Any]]:
    """Every solid the views allow: each orthographic view as the plan, the others as
    elevations seen from the front or the side (when their width fits) and from either end.
    Each: {"solid": trimesh, "how": [...]}; x along the plan's width, y its depth (+y the top of
    the plan on the sheet), z up, in mm."""
    ortho = [v for v in read["views"] if v.kind != "iso"]
    out = []
    for plan in ortho:
        elevs = [v for v in ortho if v is not plan]
        out += _from(plan, elevs, height_cm)
    return out


def _from(plan: dv.View, elevs: list[dv.View], height_cm: float | None) -> list[dict[str, Any]]:
    import itertools

    import manifold3d as m3

    p = _local(plan)
    pw, pd = float(p[:, 0].max()), float(p[:, 1].max())
    choices = []
    for e in elevs:
        w = float(_local(e)[:, 0].max())
        ways = []
        for kind, span in (("front", pw), ("side", pd)):
            if abs(w / span - 1) <= WIDTH_MATCH:
                ways += [(kind, False), (kind, True)]
        if not ways:
            return []  # this view cannot be the plan with that elevation
        choices.append(ways)
    top = max([float(_local(e)[:, 1].max()) for e in elevs] + [height_cm or 0.0])
    if top <= 0:
        return []
    out = []
    for combo in itertools.product(*choices) if choices else [()]:
        body = _prism(p, top * MM * (1.01 if elevs else 1.0))  # above the elevations' tops
        how = [f"plan: the view {plan.size[0] * plan.meta['scale']:.0f} x "
               f"{plan.size[1] * plan.meta['scale']:.0f} cm"]  # fmt: skip
        for e, (kind, flip) in zip(elevs, combo, strict=True):
            q = _local(e)
            span = pw if kind == "front" else pd
            q[:, 0] *= span / max(float(q[:, 0].max()), 1e-9)
            if flip:
                q[:, 0] = span - q[:, 0]
            far = (pd if kind == "front" else pw) * MM
            reach = far + 2 * OVERHANG_MM
            prism = m3.Manifold.extrude(m3.CrossSection([(_ccw(q) * MM).tolist()]), reach)
            # the section lies in x-y; turn it upright: its y becomes z
            if kind == "front":  # across x, extruded along y
                prism = prism.rotate((UPRIGHT, 0, 0)).translate((0, far + OVERHANG_MM, 0))
            else:  # across y, extruded along x
                prism = prism.rotate((UPRIGHT, 0, UPRIGHT)).translate((-OVERHANG_MM, 0, 0))
            body = body ^ prism
            how.append(f"{kind}{' (from the other end)' if flip else ''}")
        if not elevs:
            how.append(f"straight up to {top:g} cm")
        mesh = body.to_mesh()
        tm = trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts))
        if len(tm.faces) and tm.volume > 0:
            out.append({"solid": tm, "how": how, "plan": plan, "height_cm": top})
    return out


def _iso_silhouette(mesh: trimesh.Trimesh, azimuth_deg: float) -> Any:
    import shapely

    a, e = math.radians(azimuth_deg), math.radians(ISO_ELEVATION)
    right = np.array([math.cos(a), -math.sin(a), 0.0])
    up = np.array([math.sin(a) * math.sin(e), math.cos(a) * math.sin(e), math.cos(e)])
    xy = np.column_stack([mesh.vertices @ right, mesh.vertices @ up]) / MM  # cm
    tris = xy[mesh.faces]
    u, v = tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    area = np.abs(u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0])
    polys = [shapely.Polygon(t) for t in tris[area > 1e-6]]
    return shapely.union_all(polys)


def iso_fit(mesh: trimesh.Trimesh, iso: dv.View, mirror: bool = False) -> tuple[float, float]:
    """How well the solid seen isometrically covers the drawing's 3D view: (IoU, azimuth).
    `mirror`: also try it mirrored (for a cover whose left and right may be swapped)."""
    import shapely
    from shapely import affinity

    target = shapely.Polygon(iso.outline * float(iso.meta["scale"])).buffer(0)
    target = affinity.translate(target, -target.centroid.x, -target.centroid.y)
    best = (0.0, 0.0)
    shapes = [mesh]
    if mirror:
        flipped = mesh.copy()
        flipped.vertices[:, 0] *= -1
        flipped.invert()
        shapes.append(flipped)
    for az, m_ in ((a, m_) for a in CORNERS_DEG for m_ in shapes):
        sil = _iso_silhouette(m_, az)
        sil = affinity.translate(sil, -sil.centroid.x, -sil.centroid.y)
        iou = float(sil.intersection(target).area / max(sil.union(target).area, 1e-9))
        if iou > best[0]:
            best = (iou, az)
    return best


HEIGHT_RANGE_CM = (10.0, 160.0)  # param-ok: the heights tried when only a plan is drawn


def best_solid(pdf: Path, height_cm: float | None = None) -> dict[str, Any]:
    """The views read, every candidate solid built and scored against the 3D view. With a plan
    and no elevation the height is the one whose 3D view fits best, snapped to a written size
    within 3 % (it must be written somewhere)."""
    read = dv.read(pdf)
    iso = next((v for v in read["views"] if v.kind == "iso"), None)
    cands = candidates(read, height_cm)
    lone = [c for c in cands if len(c["how"]) == 2 and c["how"][1].startswith("straight")]  # noqa: PLR2004
    if iso is not None and not height_cm:
        plans = {id(c["plan"]): c["plan"] for c in lone} or (
            {id(v): v for v in read["views"] if v.kind != "iso"} if not cands else {}
        )
        cands = [c for c in cands if c not in lone]
        for plan in plans.values():
            h = _best_height(plan, iso, read["sizes_cm"])
            if h:
                cands += _from(plan, [], h)
    for c in cands:
        c["iou"], c["azimuth"] = iso_fit(c["solid"], iso) if iso is not None else (0.0, 0.0)
    cands.sort(key=lambda c: -c["iou"])
    return {"read": read, "candidates": cands, "best": cands[0] if cands else None}


def _best_height(plan: dv.View, iso: dv.View, sizes: list[float]) -> float | None:
    lo, hi = HEIGHT_RANGE_CM
    best = (0.0, 0.0)
    for h in np.arange(lo, hi + 1, 2.0):  # param-ok: 2 cm steps, then refined
        c = _from(plan, [], float(h))
        if c:
            iou = iso_fit(c[0]["solid"], iso)[0]
            if iou > best[0]:
                best = (iou, float(h))
    if best[1] == 0:
        return None
    for h in np.arange(best[1] - 2, best[1] + 2.01, 0.5):  # param-ok: refine to 5 mm
        c = _from(plan, [], float(h))
        if c:
            iou = iso_fit(c[0]["solid"], iso)[0]
            if iou > best[0]:
                best = (iou, float(h))
    near = [s for s in sizes if abs(s / best[1] - 1) <= 0.03]  # param-ok: a written height
    return min(near, key=lambda s: abs(s - best[1])) if near else best[1]


def _regions(mesh: trimesh.Trimesh) -> list[np.ndarray]:
    """Faces grouped into pieces: connected across edges that fold less than FOLD_DEG."""
    import networkx as nx

    adj = mesh.face_adjacency
    angles = np.degrees(mesh.face_adjacency_angles)
    upright = np.abs(mesh.face_normals[:, 2]) < 0.1  # param-ok: a wall
    walls = upright[adj[:, 0]] & upright[adj[:, 1]]
    keep = adj[np.where(walls, angles < WALL_FOLD_DEG, angles < FOLD_DEG)]
    g = nx.Graph()
    g.add_nodes_from(range(len(mesh.faces)))
    g.add_edges_from(keep.tolist())
    return [np.array(sorted(c)) for c in nx.connected_components(g)]


def pieces(solid: trimesh.Trimesh, roll_mm: float) -> list[Piece]:
    """The solid's surface without its bottom, as pieces (faces in mm, y towards the front as
    drawn.scene expects)."""
    m = solid.copy()
    m.merge_vertices()
    bottom = (m.face_normals[:, 2] < -0.99) & (m.triangles_center[:, 2] < 1.0)  # param-ok: mm
    m.update_faces(~bottom)
    m.remove_unreferenced_vertices()
    regs = _regions(m)
    total = float(m.area)
    # tiny regions (slivers where two cuts nearly meet) join the neighbour they share most with
    big = [r for r in regs if m.area_faces[r].sum() >= SMALL_SHARE * total]
    small = [r for r in regs if m.area_faces[r].sum() < SMALL_SHARE * total]
    owner = np.full(len(m.faces), -1)
    for i, r in enumerate(big):
        owner[r] = i
    for r in small:
        nb = [owner[b] for a, b in m.face_adjacency if a in r and owner[b] >= 0]
        nb += [owner[a] for a, b in m.face_adjacency if b in r and owner[a] >= 0]
        owner[r] = max(set(nb), key=nb.count) if nb else len(big)
        if not nb:
            big.append(r)
    groups = [np.where(owner == i)[0] for i in range(len(big))]
    out: list[Piece] = []
    for i, fs in enumerate(groups):
        for k, part in enumerate(_flat_able(m, fs, roll_mm)):
            name = _name(m, part)
            out.append(Piece(f"{name}-{i + 1}" + (f"{chr(97 + k)}" if k else ""),
                             [[(float(x), -float(y), float(z)) for x, y, z in m.vertices[f]]
                              for f in m.faces[part]]))  # fmt: skip
    return out


def _name(m: trimesh.Trimesh, faces: np.ndarray) -> str:
    n = (m.face_normals[faces] * m.area_faces[faces, None]).sum(axis=0)
    n /= max(np.linalg.norm(n), 1e-9)
    if n[2] > 0.95:  # param-ok: facing up
        return "top"
    if n[2] > 0.3:  # param-ok: a slope
        return "slope"
    return "wall"


def _flat_able(m: trimesh.Trimesh, faces: np.ndarray, roll_mm: float) -> list[np.ndarray]:
    """A region that is a closed band (its outline has two loops) is cut in two along its
    longest direction; a region wider than the roll in every direction is cut across."""
    sub = trimesh.Trimesh(m.vertices, m.faces[faces], process=False)
    parts = [faces]
    rim = sub.edges[trimesh.grouping.group_rows(sub.edges_sorted, require_count=1)]
    loops = len(trimesh.graph.connected_components(rim))
    centres = m.triangles_center[faces]
    if loops >= 2:  # a ring round the cover
        c = centres.mean(axis=0)
        _, _, vt = np.linalg.svd(centres[:, :2] - c[:2])
        side = (centres[:, :2] - c[:2]) @ vt[0] >= 0
        parts = [faces[side], faces[~side]]
    out = []
    for f in parts:
        pts = m.vertices[np.unique(m.faces[f])]
        if len(pts) < 3:  # param-ok: a face
            continue
        # the piece's own two main directions (a wall stands up, a top lies flat)
        c = pts.mean(axis=0)
        _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
        spans = [float(np.ptp((pts - c) @ vt[i])) for i in range(2)]
        i = int(np.argmin(spans))
        n = max(1, math.ceil(spans[i] / roll_mm))
        if n == 1:
            out.append(f)
            continue
        t = (m.triangles_center[f] - c) @ vt[i]
        edges = np.linspace(t.min(), t.max(), n + 1)
        idx = np.clip(np.searchsorted(edges, t, side="right") - 1, 0, n - 1)
        out += [f[idx == k] for k in range(n) if (idx == k).any()]
    return out


def model_surface(model_dir: Path) -> trimesh.Trimesh:
    """A model's own surface (model.glb: metres, Y up, as glTF) in mm with Z up."""
    m = trimesh.load(model_dir / "model.glb", force="mesh")
    assert isinstance(m, trimesh.Trimesh)
    v = np.asarray(m.vertices) * 1000.0  # param-ok: m to mm
    return trimesh.Trimesh(np.column_stack([v[:, 0], -v[:, 2], v[:, 1]]), m.faces)
