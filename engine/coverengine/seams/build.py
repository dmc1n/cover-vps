"""`cover cut`: divide the cover surface into panels (ADR-026).

models/<id>/panels.glb        panels in colour with the furniture, for viewing
models/<id>/panels.json       panels (name, area, flat size, roll check) and seams
models/<id>/seams.auto.json   the seams used, in the editable format of seams.json
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import shapely
import trimesh
from numpy.typing import NDArray
from trimesh.grouping import group_rows

from coverengine import __version__
from coverengine.errors import CoverError
from coverengine.hull.build import HULL_GLB, MODEL_RGBA, _coloured
from coverengine.io.model_io import glb_bytes, load_model, read_model_json
from coverengine.palette import piece as piece_colour
from coverengine.params import EffectiveParams
from coverengine.seams import auto
from coverengine.seams.cut import (
    CutMesh,
    Seam,
    apply,
    is_disk,
    panels,
    seam_edges,
    smooth_seam,
    unzip,
)
from coverengine.seams.panels import (
    Panel,
    SeamInfo,
    _ordered,
    all_seam_edges,
    flat_size,
    labels_without_slivers,
    min_radius,
    panel_mesh,
)

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]

FORMAT_VERSION = 1
PANELS_GLB, PANELS_JSON, SEAMS_AUTO_JSON, SEAMS_JSON = (
    "panels.glb",
    "panels.json",
    "seams.auto.json",
    "seams.json",
)
PANELS_NPZ = "panels.npz"  # the unzipped cover, panel labels and seam edges, for flattening
TOP, SKIRT, WALL = "top", "skirt", "wall"
TOP_REGION, SKIRT_REGION, WALL_REGION = 0, 1, 2
# A seam with the same panel on both sides and shorter than this is a merged sliver's rest (mm).
SLIVER_SEAM_MM = 10.0  # param-ok: geometric tolerance
# Roll-width splits per panel before giving up (each halves the width).
MAX_ROLL_SPLITS = 4
PROPOSALS_JSON = "proposals.json"
# Box covers: faces with the same normal (to this many decimals) are one panel; faces with
# |normal z| below BOX_UPRIGHT_NZ are upright (skirt, so the vents go there).
BOX_NORMAL_DIGITS = 3
BOX_COPLANAR_DEG = 1.0  # param-ok: neighbours turning less are one flat face
BOX_SCRAP_SHARE = 0.002  # param-ok: flat bits smaller than this share of the cover are merged
# A flat piece is L-shaped when its convex outline is this share larger than the piece itself.
CORNER_SHARE = 0.02  # param-ok: geometric tolerance
SIMPLIFY_MM = 1.0  # param-ok: outline tolerance for finding its corners
BOX_UPRIGHT_NZ = 0.1  # param-ok: geometric rule  # proposed seams accepted by cover improve
MM_PER_CM = 10.0  # param-ok: unit conversion
# Smoothing a jittery wall seam in place: passes, and how far a face may turn (cosine).
SMOOTH_PASSES = 30  # param-ok: iterations
SMOOTH_KEEP_NORMAL = 0.8  # param-ok: geometric tolerance
LOW_EDGE_PERCENTILE = 5.0  # param-ok: rule, short dips of the top edge do not set the skirt height
# Reach of a straight top seam's field beyond its ends (mm), so it cuts right to the panel edge.
TOP_SEAM_OVERSHOOT_MM = 50.0  # param-ok: geometric reach


@dataclass
class Cut:
    panels: list[Panel]
    seams: list[SeamInfo]
    report: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    mesh: trimesh.Trimesh | None = None
    opened: trimesh.Trimesh | None = None  # the cover unzipped along all seams
    labels: IntArray | None = None  # panel index per face
    seam_edges: dict[tuple[int, int], int] = field(default_factory=dict)  # edge -> seam index


def _p(params: EffectiveParams, key: str) -> float:
    return float(params[key])  # type: ignore[arg-type]


def line_seam(
    seam_id: str, kind: str, points_xy: Array, region: int, only: IntArray | None = None
) -> Seam:
    """A top seam along a polyline in the floor plan: signed distance to the line, cutting only
    faces of one region (and, optionally, only the given panel's faces by label)."""
    line = shapely.LineString(points_xy)
    ext = shapely.LineString(_extend(points_xy, TOP_SEAM_OVERSHOOT_MM))

    def fld(p: Array) -> Array:
        pts = shapely.points(p[:, :2])
        d = shapely.distance(ext, pts)
        # side: sign of the cross product with the nearest segment's direction
        s = shapely.line_locate_point(ext, pts)
        a = np.array([ext.interpolate(max(x - 1.0, 0.0)).coords[0] for x in s])
        b = np.array([ext.interpolate(min(x + 1.0, ext.length)).coords[0] for x in s])
        t = b - a
        side = np.sign(t[:, 0] * (p[:, 1] - a[:, 1]) - t[:, 1] * (p[:, 0] - a[:, 0]))
        return d * np.where(side == 0, 1.0, side)

    def faces(cut: CutMesh) -> NDArray[np.bool_]:
        c = np.asarray(cut.mesh.triangles_center)
        near = shapely.distance(ext, shapely.points(c[:, :2])) < TOP_SEAM_OVERSHOOT_MM
        mask = near & (cut.region == region)
        if only is not None:
            labels = labels_without_slivers(cut)
            mask &= np.isin(labels, only)
        return mask

    del line
    return Seam(id=seam_id, kind=kind, field=fld, faces=faces)


def _extend(points: Array, by: float) -> Array:
    p = np.asarray(points, dtype=np.float64)
    d0 = p[0] - p[1]
    d1 = p[-1] - p[-2]
    return np.vstack([p[0] + d0 / np.linalg.norm(d0) * by, p, p[-1] + d1 / np.linalg.norm(d1) * by])


def _read_manual(model_dir: Path, path: Path | None) -> dict[str, Any] | None:
    p = path or (model_dir / SEAMS_JSON)
    if not p.is_file():
        if path is not None:
            raise CoverError(f"no seam file at {p}")
        return None
    doc: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    return doc


def cut_cover(model_dir: Path, params: EffectiveParams, seams_file: Path | None = None) -> Cut:
    """Seams and panels of the cover. If wall panels leave a panel that cannot lie flat in one
    piece, the cover is cut again without walls (the top then wraps down to the skirt there) and
    a warning says so."""
    try:
        return _cut_cover(model_dir, params, seams_file, walls_allowed=True)
    except CoverError as exc:
        if "not a disk" not in str(exc):
            raise
        result = _cut_cover(model_dir, params, seams_file, walls_allowed=False)
        if result.report.get("walls_tried"):
            result.warnings.append(
                f"wall panels were left out ({exc}); the top panels reach down to the skirt"
            )
            result.report["warnings"] = result.warnings
        return result


def _cut_cover(
    model_dir: Path, params: EffectiveParams, seams_file: Path | None, walls_allowed: bool
) -> Cut:
    hull_path = model_dir / HULL_GLB
    if not hull_path.is_file():
        raise CoverError(f"no cover surface at {hull_path} (run cover hull first)")
    hull = load_model(hull_path)
    hull = trimesh.Trimesh(hull.vertices, hull.faces, process=True)
    drawn = _drawn_parts(model_dir, hull) if params["hull.top"] in ("given", "box") else None
    if (
        drawn is not None
        or params["hull.top"] == "box"
        or (params["hull.top"] == "given" and _flat_faced(hull))
    ):
        return _box_cut(model_dir, hull, params, drawn)
    snap = _p(params, "seams.snap_mm")
    inset = _p(params, "seams.skirt_seam_inset_mm")
    line = auto.outline(hull)
    manual = _read_manual(model_dir, seams_file)
    warnings: list[str] = []

    # 1. skirt seam all round at one height (the company rule), just below the lowest point of
    # the top edge; the two regions it makes are the top and the skirt
    hem_z = float(hull.vertices[:, 2].min())
    below = _p(params, "seams.skirt_below_rim_mm")
    rim = auto.rim_profile(hull, line, inset, _p(params, "seams.rim_smoothing_mm"))
    # the lowest the top edge goes, leaving out short dips (the rounded corners of a box)
    lowest_edge = float(np.percentile(rim.height, LOW_EDGE_PERCENTILE))
    skirt_height = _p(params, "seams.skirt_height_mm")
    level_skirt = params["seams.skirt_seam"] == "level"
    if level_skirt:
        chosen = skirt_height > 0
        if not chosen:  # automatic, but never lower than the minimum (splayed legs: the
            # cover runs down to the feet there and has no upright part to put a seam on)
            skirt_height = max(lowest_edge - below - hem_z, _p(params, "seams.min_skirt_height_mm"))
        if chosen and hem_z + skirt_height > lowest_edge - below:
            warnings.append(
                f"the skirt seam ({skirt_height / MM_PER_CM:.1f} cm above the hem) climbs onto "
                f"the top where the top edge is lower (lowest "
                f"{(lowest_edge - hem_z) / MM_PER_CM:.1f} cm); the skirt panels there wrap over "
                "the rounded edge"
            )
        skirt = auto.skirt_seam(hem_z + skirt_height)
        heights = (skirt_height, skirt_height)
    else:
        skirt = auto.rim_seam(line, rim, below)
        heights = (lowest_edge - below - hem_z, float(rim.height.max()) - below - hem_z)
    cut = apply(CutMesh(hull, []), skirt, snap)
    labels = panels(cut.mesh, seam_edges(cut)["skirt"])
    edges = cut.mesh.edges_sorted
    hem_vertices = np.unique(edges[group_rows(edges, require_count=1)])
    hem_faces = np.flatnonzero(np.isin(cut.mesh.faces, hem_vertices).any(axis=1))
    skirt_label = int(np.bincount(labels[hem_faces]).argmax())
    cut.region = np.where(labels == skirt_label, SKIRT_REGION, TOP_REGION).astype(np.int64)

    # 2. vertical skirt seams: corners and equal splits, or the manual positions
    if manual and manual.get("skirt_seams") is not None:
        ext = line.polygon.exterior
        positions = sorted(float(ext.project(shapely.Point(xy))) for xy in manual["skirt_seams"])
    else:
        found = auto.corners(
            line, _p(params, "seams.corner_angle_deg"), _p(params, "seams.corner_window_mm")
        )
        positions = auto.split_positions(
            line,
            found,
            _p(params, "seams.max_skirt_panel_mm"),
            _p(params, "seams.min_skirt_panel_mm"),
        )

    # 3. walls: where the top edge stands clearly higher than the skirt seam (the back of a
    # chair), the upright part between becomes a wall panel, so the top never wraps down over
    # its edge; a wall ends in a short upright line where the edge comes down again
    walls: list[tuple[float, float]] = []
    walls_tried = False
    if level_skirt:
        walls = auto.wall_ranges(
            rim,
            hem_z + skirt_height,
            _p(params, "seams.wall_min_mm"),
            _p(params, "seams.wall_min_length_mm"),
        )
    if walls and not walls_allowed:
        walls, walls_tried = [], True
    if walls:
        cut = apply(cut, auto.wall_seam(line, rim, inset, walls, TOP_REGION), snap)
        # a wall a millimetre out of plumb makes the true edge jitter: then smooth it in place
        # (a clean edge, with its real corners, is left as it is)
        if _seam_wiggle(cut, "wall") > _p(params, "seams.max_wiggle_mm"):
            cut = smooth_seam(cut, "wall", hull, SMOOTH_PASSES, SMOOTH_KEEP_NORMAL)
    reach = _p(params, "seams.corner_window_mm")
    for i, s in enumerate(positions):
        cut = apply(cut, auto.corner_seam(line, s, i, SKIRT_REGION, reach), snap)
    if walls:
        found_edges = [e for e in seam_edges(cut).values() if len(e)]
        lab = panels(cut.mesh, np.vstack(found_edges))
        # the top reaches inward from the outline; walls stand at the outline
        centre = np.asarray(cut.mesh.triangles_center)
        inward = line.inside_distance(centre[:, :2]) > auto.WALL_ZONE_MM
        tops = np.unique(lab[inward & (cut.region == TOP_REGION)])
        cut.region = np.where(
            cut.region == SKIRT_REGION,
            SKIRT_REGION,
            np.where(np.isin(lab, tops), TOP_REGION, WALL_REGION),
        ).astype(np.int64)

    # 3. top seams from seams.json
    top_lines: list[list[list[float]]] = []
    wanted = list((manual or {}).get("top_seams") or [])
    # seams the program proposed and `cover improve` accepted (kept apart from seams.json)
    accepted = model_dir / PROPOSALS_JSON
    if accepted.is_file():
        wanted += json.loads(accepted.read_text(encoding="utf-8")).get("top_seams", [])
    for i, pts in enumerate(wanted):
        xy = np.asarray(pts, dtype=np.float64)[:, :2]
        cut = apply(cut, line_seam(f"top-{i + 1}", "top", xy, 0), snap)
        top_lines.append(xy.tolist())

    # 4. roll width: split top panels that do not fit along a line of constant height, so the
    #    upper panel laps over the lower like roof tiles; the first split separates the band
    #    just below the highest point (the flat band along a backrest)
    usable = _p(params, "roll.usable_width_mm")
    drop = _p(params, "seams.band_drop_mm")
    levels: list[float] = []
    for round_ in range(MAX_ROLL_SPLITS):
        lab = labels_without_slivers(cut)
        opened = unzip(cut.mesh, all_seam_edges(cut))
        too_wide = []
        for k in range(int(lab.max()) + 1):
            faces = np.flatnonzero(lab == k)
            if np.bincount(cut.region[faces]).argmax() != 0:
                continue
            width, _ = flat_size(panel_mesh(opened, faces))
            if width > usable:
                too_wide.append(k)
        if not too_wide:
            break
        for k in too_wide:
            faces = np.flatnonzero(lab == k)
            z = np.asarray(cut.mesh.triangles_center)[faces, 2]
            options: list[tuple[str, Seam, float | None, Array | None]] = []
            for label, z0 in (
                ("band", float(z.max() - drop)),
                ("half", _split_height(cut.mesh, faces, drop, first=False)),
            ):
                seam = level_seam(f"level-{round_ + 1}-{k}-{label}", z0, np.array([k]))
                options.append((label, seam, z0, None))
            xy = _long_axis(cut.mesh, faces)
            options.append(
                (
                    "straight",
                    line_seam(f"roll-{round_ + 1}-{k}", "roll", xy, 0, only=np.array([k])),
                    None,
                    xy,
                )
            )
            for _label, seam, level, xy_line in options:
                trial = apply(_copy(cut), seam, snap)
                if _pieces_are_disks(trial, faces_before=len(faces)):
                    cut = trial
                    if level is not None:
                        levels.append(level)
                    if xy_line is not None:
                        top_lines.append(xy_line.tolist())
                    break

    result = _assemble(model_dir, cut, params, positions, line, top_lines, levels, warnings)
    result.report["skirt_height_mm"] = [round(h, 1) for h in heights]  # lowest, highest
    result.report["walls_tried"] = walls_tried
    return result


# A given cover surface made of at most this many flat faces is cut like a box (ADR-039).
FLAT_FACES_MAX = 20  # param-ok: geometric limit


def _flat_faced(hull: trimesh.Trimesh) -> bool:
    """Is the surface a few flat faces (a cover drawn as a box), not a curved surface?"""
    normals = np.round(np.asarray(hull.face_normals), BOX_NORMAL_DIGITS)
    return len(np.unique(normals, axis=0)) <= FLAT_FACES_MAX


def _flat_regions(hull: trimesh.Trimesh) -> NDArray[np.int64]:
    """Faces joined into flat regions: neighbours turning less than BOX_COPLANAR_DEG are one
    region; regions smaller than BOX_SCRAP_SHARE of the cover (slivers left by meshing) go to
    the neighbour they share the longest edge with."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    n = len(hull.faces)
    pairs = np.asarray(hull.face_adjacency)
    same = np.asarray(hull.face_adjacency_angles) < math.radians(BOX_COPLANAR_DEG)
    a, b = pairs[same, 0], pairs[same, 1]
    graph = coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n))
    _, label = connected_components(graph, directed=False)
    label = np.asarray(label, np.int64)
    edge_len = np.linalg.norm(
        np.diff(hull.vertices[hull.face_adjacency_edges], axis=1)[:, 0], axis=1
    )
    scrap = BOX_SCRAP_SHARE * float(hull.area)
    for _ in range(n):
        area = np.bincount(label, weights=hull.area_faces)
        small = [r for r in np.flatnonzero(area) if area[r] < scrap]
        if not small:
            break
        r = min(small, key=lambda q: area[q])
        la, lb = label[pairs[:, 0]], label[pairs[:, 1]]
        touch = ((la == r) & (lb != r)) | ((lb == r) & (la != r))
        if not touch.any():
            break
        other = np.where(la[touch] == r, lb[touch], la[touch])
        shared = np.bincount(other, weights=edge_len[touch])
        label[label == r] = int(np.argmax(shared))
    _, label = np.unique(label, return_inverse=True)
    return _split_at_inside_corners(hull, label.ravel().astype(np.int64))


def _split_at_inside_corners(hull: trimesh.Trimesh, label: NDArray[np.int64]) -> NDArray[np.int64]:
    """A flat piece that turns a corner (an L-shaped strip) is split from its inside corner
    along the line halving that corner: the 45 degree seam of an L-shaped cover (ADR-045)."""
    out = label.copy()
    nxt = int(label.max()) + 1
    for r in range(int(label.max()) + 1):
        m = np.flatnonzero(out == r)
        if not len(m):
            continue
        n = hull.face_normals[m].mean(axis=0)
        n /= np.linalg.norm(n)
        u = np.cross(n, [0.0, 0.0, 1.0] if abs(n[2]) < 0.9 else [1.0, 0.0, 0.0])  # param-ok
        u /= np.linalg.norm(u)
        w = np.cross(n, u)
        tri = hull.vertices[hull.faces[m]]
        flat = np.stack([tri @ u, tri @ w], axis=-1)
        piece = shapely.union_all([shapely.Polygon(t) for t in flat]).buffer(0)
        if not isinstance(piece, shapely.Polygon) or piece.convex_hull.area <= piece.area * (
            1 + CORNER_SHARE
        ):
            continue
        ring = np.asarray(piece.simplify(SIMPLIFY_MM).exterior.coords)[:-1]
        if shapely.LinearRing(ring).is_ccw is False:
            ring = ring[::-1]
        centres = tri.mean(axis=1) @ np.column_stack([u, w])
        for i in range(len(ring)):
            a, v, b = ring[i - 1], ring[i], ring[(i + 1) % len(ring)]
            e1, e2 = (a - v) / np.linalg.norm(a - v), (b - v) / np.linalg.norm(b - v)
            if e1[0] * e2[1] - e1[1] * e2[0] <= 0:  # not an inside (reflex) corner
                continue
            d = -(e1 + e2)
            d /= np.linalg.norm(d)
            side = (d[0] * (centres[:, 1] - v[1]) - d[1] * (centres[:, 0] - v[0])) > 0
            here = out[m] == r
            if side[here].all() or not side[here].any():
                continue
            out[m[here & side]] = nxt
            nxt += 1
            break
    _, out = np.unique(out, return_inverse=True)
    return out.ravel().astype(np.int64)


def _drawn_parts(model_dir: Path, hull: trimesh.Trimesh) -> NDArray[np.int64] | None:
    """The pieces of a cover surface drawn in parts (one part per piece), if it was."""
    from coverengine.hull.build import HULL_PARTS

    path = model_dir / HULL_PARTS
    if not path.is_file():
        return None
    part = np.load(path)
    if len(part) != len(hull.faces):
        return None
    _, label = np.unique(part, return_inverse=True)
    return label.ravel().astype(np.int64)


def _box_cut(
    model_dir: Path,
    hull: trimesh.Trimesh,
    params: EffectiveParams,
    drawn: NDArray[np.int64] | None = None,
) -> Cut:
    """A box cover: every flat face is one panel and every box edge a seam (ADR-038); a cover
    drawn in parts: every part is one panel (ADR-045)."""
    label = drawn if drawn is not None else _flat_regions(hull)
    joined: list[str] = []
    folds: list[list[list[float]]] = []
    if drawn is None:  # an owner's drawing keeps its pieces as drawn
        from coverengine.seams import facets

        weighted = np.zeros((label.max() + 1, 3))
        np.add.at(weighted, label, hull.face_normals * hull.area_faces[:, None])
        nz = np.abs(weighted[:, 2]) / np.maximum(np.linalg.norm(weighted, axis=1), 1e-9)
        roll = _p(params, "roll.usable_width_mm") - 2 * _p(params, "stitching.allowance_mm")
        label, joined, folds = facets.join(
            hull,
            label,
            nz >= BOX_UPRIGHT_NZ,
            _p(params, "seams.min_piece_width_mm"),
            roll,
            _p(params, "seams.max_skirt_panel_mm"),
            bool(params["seams.fold_merge"]),
        )
        label = np.unique(label, return_inverse=True)[1].astype(np.int64)
    else:  # a cover drawn in parts by the program (ADR-103): the folds it made
        hull_json = model_dir / "hull.json"
        if hull_json.is_file():
            plan = (json.loads(hull_json.read_text(encoding="utf-8")).get("box") or {}).get("plan")
            folds = list((plan or {}).get("folds_mm") or [])
    # the people's corrections at the Desk: join pieces, split a piece (ADR-082)
    from coverengine import learned

    edit_notes: list[str] = []
    edits = learned.read_edits(model_dir)
    if edits:
        label, edit_notes = learned.apply_edits(
            np.asarray(hull.triangles_center), np.asarray(hull.face_adjacency), label, edits
        )
    # a region's direction is its area-weighted normal (thin slivers have noisy normals)
    weighted = np.zeros((label.max() + 1, 3))
    np.add.at(weighted, label, hull.face_normals * hull.area_faces[:, None])
    upright = np.abs(weighted[label, 2] / np.linalg.norm(weighted[label], axis=1)) < BOX_UPRIGHT_NZ
    region = np.where(upright, SKIRT_REGION, TOP_REGION).astype(np.int64)
    pairs = np.asarray(hull.face_adjacency)
    shared = np.sort(np.asarray(hull.face_adjacency_edges), axis=1)
    seams: dict[tuple[int, int], Seam] = {}
    for (a, b), e in zip(pairs.tolist(), shared.tolist(), strict=True):
        la, lb = int(label[a]), int(label[b])
        if la == lb:
            continue
        key = (min(la, lb), max(la, lb))
        if key not in seams:
            ra, rb = int(region[a]), int(region[b])
            kind = "corner" if ra == rb == SKIRT_REGION else "skirt" if ra != rb else "top"
            seams[key] = Seam(
                f"box-{key[0]}-{key[1]}",
                kind,
                field=lambda p: np.zeros(len(p)),
                faces=lambda c: np.zeros(len(c.mesh.faces), dtype=bool),
            )
        seams[key].edges.add((int(e[0]), int(e[1])))
        seams[key].vertices.update(e)
    cut = CutMesh(hull, list(seams.values()), region)
    line = auto.outline(hull)
    result = _assemble(model_dir, cut, params, [], line, [], [], [])
    result.report["skirt_height_mm"] = None
    result.report["walls_tried"] = False
    result.report["box"] = True
    result.report["joined"] = joined  # slivers and (on request) top faces joined, with folds
    result.report["folds_mm"] = folds  # the 3D ends of every fold, drawn in pen (ADR-055)
    result.report["part_edits"] = edit_notes  # what the Desk's piece edits did (ADR-082)
    return result


def _seam_wiggle(cut: CutMesh, seam_id: str) -> float:
    """The largest zig-zag (mm) along any part of a seam, as the pattern check measures it."""
    from coverengine.flatten.pattern import wiggle

    edges = seam_edges(cut).get(seam_id)
    if edges is None or not len(edges):
        return 0.0
    v = np.asarray(cut.mesh.vertices)
    remaining = {tuple(e) for e in edges.tolist()}
    worst = 0.0
    while remaining:
        start = next(iter(remaining))
        part, ends = {start}, set(start)
        remaining.discard(start)
        grew = True
        while grew:
            grew = False
            for e in [e for e in remaining if e[0] in ends or e[1] in ends]:
                part.add(e)
                ends.update(e)
                remaining.discard(e)
                grew = True
        order = _ordered(np.array(sorted(part)))
        if len(order) > 2:
            worst = max(worst, wiggle(v[order]))
    return worst


def _copy(cut: CutMesh) -> CutMesh:
    """A copy whose seams can be changed without touching the original (apply updates the edge
    sets of earlier seams in place)."""
    seams = [Seam(s.id, s.kind, s.field, s.faces, set(s.vertices), set(s.edges)) for s in cut.seams]
    return CutMesh(cut.mesh, seams, cut.region.copy())


def _pieces_are_disks(cut: CutMesh, faces_before: int) -> bool:
    """Every panel is a disk after a trial cut."""
    del faces_before
    lab = labels_without_slivers(cut)
    opened = unzip(cut.mesh, all_seam_edges(cut))
    return all(
        is_disk(panel_mesh(opened, np.flatnonzero(lab == k))) for k in range(int(lab.max()) + 1)
    )


def level_seam(seam_id: str, z0: float, only: IntArray) -> Seam:
    """A seam along the height z0 on the given top panels."""

    def faces(cut: CutMesh) -> NDArray[np.bool_]:
        return (cut.region == 0) & np.isin(labels_without_slivers(cut), only)

    return Seam(id=seam_id, kind="level", field=lambda p: p[:, 2] - z0, faces=faces)


def _split_height(mesh: trimesh.Trimesh, faces: IntArray, drop_mm: float, first: bool) -> float:
    """Height of a level split: just below the top for the first split (the band), otherwise
    where half of the panel's area lies above."""
    z = np.asarray(mesh.triangles_center)[faces, 2]
    if first:
        return float(z.max() - drop_mm)
    w = np.asarray(mesh.area_faces)[faces]
    order = np.argsort(z)
    half = np.searchsorted(np.cumsum(w[order]), w.sum() / 2)
    return float(z[order][min(half, len(z) - 1)])


def _long_axis(mesh: trimesh.Trimesh, faces: IntArray) -> Array:
    """A straight line through the panel's centre along its longest direction (floor plan)."""
    c = np.asarray(mesh.triangles_center)[faces][:, :2]
    w = np.asarray(mesh.area_faces)[faces]
    centre = (c * w[:, None]).sum(0) / w.sum()
    cov = np.cov((c - centre).T, aweights=w)
    _, vec = np.linalg.eigh(cov)
    d = vec[:, -1]
    span = float(np.ptp((c - centre) @ d))
    return np.array([centre - d * span, centre + d * span])


def _side(angle_deg: float) -> str:
    """Which side a skirt panel faces, from the angle of its outward normal (front is -y)."""
    if -45 <= angle_deg < 45:  # param-ok: quadrant bounds
        return "right"
    if 45 <= angle_deg < 135:  # param-ok: quadrant bounds
        return "back"
    if -135 <= angle_deg < -45:  # param-ok: quadrant bounds
        return "front"
    return "left"


def _names(mesh: trimesh.Trimesh, lab: IntArray, region: IntArray) -> dict[int, str]:
    names: dict[int, str] = {}
    tops: list[tuple[float, int]] = []
    skirts: list[tuple[str, float, int]] = []
    walls: list[tuple[str, float, int]] = []
    for k in range(int(lab.max()) + 1):
        faces = np.flatnonzero(lab == k)
        c = np.asarray(mesh.triangles_center)[faces]
        w = np.asarray(mesh.area_faces)[faces]
        major = int(np.bincount(region[faces], minlength=3).argmax())
        if major == TOP_REGION:
            tops.append((float((c[:, 1] * w).sum() / w.sum()), k))
        else:
            n = (np.asarray(mesh.face_normals)[faces][:, :2] * w[:, None]).sum(0)
            angle = math.degrees(math.atan2(n[1], n[0]))
            side = _side(angle)
            (walls if major == WALL_REGION else skirts).append((side, angle, k))
    tops.sort()
    for i, (_, k) in enumerate(tops):
        names[k] = "top" if len(tops) == 1 else f"top-{i + 1}"
    for kind, pieces in (("skirt", skirts), ("wall", walls)):
        if len(pieces) == 1:  # one piece all round
            names[pieces[0][2]] = kind
            continue
        for side in ("front", "right", "back", "left"):
            group = sorted((a, k) for s, a, k in pieces if s == side)
            for i, (_, k) in enumerate(group):
                names[k] = f"{kind}-{side}" if len(group) == 1 else f"{kind}-{side}-{i + 1}"
    return names


def _assemble(
    model_dir: Path,
    cut: CutMesh,
    params: EffectiveParams,
    positions: list[float],
    line: auto.Outline,
    top_lines: list[list[list[float]]],
    levels: list[float],
    warnings: list[str],
) -> Cut:
    mesh = cut.mesh
    lab = labels_without_slivers(cut)
    names = _names(mesh, lab, cut.region)
    usable = _p(params, "roll.usable_width_mm")
    # seams: group seam edges by the pair of panels on either side
    pairs = np.asarray(mesh.face_adjacency)
    shared = np.sort(np.asarray(mesh.face_adjacency_edges), axis=1)
    index = {tuple(e): i for i, e in enumerate(shared.tolist())}
    groups: dict[tuple[str, int, int], list[tuple[int, int]]] = {}
    kinds = {s.id: s.kind for s in cut.seams}
    for sid, edges in seam_edges(cut).items():
        for e in edges.tolist():
            i = index.get(tuple(e))
            if i is None:
                continue
            a, b = int(lab[pairs[i, 0]]), int(lab[pairs[i, 1]])
            # a == b: a seam closing a panel onto itself (a skirt ring cut once), or the rest
            # of a merged sliver (dropped below by its length)
            key = (kinds[sid], min(a, b), max(a, b))
            groups.setdefault(key, []).append((min(e), max(e)))
    # a short seam inside one panel is a leftover slit (the end of a seam that ran on past the
    # seam it meets); it is not cut open
    v = np.asarray(mesh.vertices)
    slits: set[tuple[int, int]] = set()
    for (kind, a, b), chain in groups.items():
        if a == b:
            e = np.array(sorted(set(chain)))
            length = float(np.linalg.norm(v[e[:, 0]] - v[e[:, 1]], axis=1).sum())
            # only a vertical seam may close a panel onto itself (a round skirt cut once); a
            # top seam inside one panel is the end of a line that ran on past its seam
            if length < SLIVER_SEAM_MM or kind != "corner":
                slits.update(map(tuple, e.tolist()))
    cut_edges = all_seam_edges(cut)
    if slits:
        cut_edges = np.array(
            [e for e in cut_edges.tolist() if (min(e), max(e)) not in slits], dtype=np.int64
        ).reshape(-1, 2)
    opened = unzip(mesh, cut_edges)
    result: list[Panel] = []
    for k in range(int(lab.max()) + 1):
        faces = np.flatnonzero(lab == k)
        sub = panel_mesh(opened, faces)
        disk = is_disk(sub)
        width, length = flat_size(sub) if disk else (float("nan"), float("nan"))
        region = (TOP, SKIRT, WALL)[int(np.bincount(cut.region[faces], minlength=3).argmax())]
        result.append(Panel(k, names[k], faces, sub, float(sub.area), disk, width, length, region))
        if not disk:
            raise CoverError(
                f"panel {names[k]} does not lie flat in one piece (not a disk); add a seam"
            )
        if width > usable:
            warnings.append(
                f"panel {names[k]} is {width:.0f} mm wide, more than the roll ({usable:g} mm)"
            )

    infos: list[SeamInfo] = []
    edge_seam: dict[tuple[int, int], int] = {}
    v = np.asarray(mesh.vertices)
    for (kind, a, b), chain in sorted(groups.items()):
        # two seam lines may run along the same edges (manual lines sharing a stretch)
        chain = sorted(set(chain))
        order = _ordered(np.array(chain))
        pts = v[order]
        # all parts of the seam (it may come in pieces, either side of a wall)
        e = np.array(chain)
        length = float(np.linalg.norm(v[e[:, 0]] - v[e[:, 1]], axis=1).sum())
        if a == b and (length < SLIVER_SEAM_MM or kind != "corner"):
            continue
        lap = _lap(kind, result[a], result[b])
        seam_id = f"{names[a]}/{names[b]}"
        if any(i.id == seam_id for i in infos):  # two seams between the same panels
            seam_id = f"{seam_id} ({kind})"
        infos.append(SeamInfo(seam_id, kind, (a, b), length, lap, min_radius(pts), pts))
        for e in chain:
            edge_seam[(min(e), max(e))] = len(infos) - 1
        result[a].seams.append(infos[-1].id)
        if b != a:
            result[b].seams.append(infos[-1].id)
    tight = _p(params, "seams.min_weld_radius_mm")
    tight_seams = [s for s in infos if s.min_radius_mm < tight and s.kind != "corner"]
    if params["construction.method"] == "welded":  # tight curves matter most for welding
        for s in tight_seams:
            warnings.append(
                f"seam {s.id} curves tighter than {tight:g} mm (radius {s.min_radius_mm:.0f} mm)"
            )

    hem = mesh.edges_sorted[group_rows(mesh.edges_sorted, require_count=1)]
    keys = [k for k in params.keys() if k.startswith("seams.")] + [
        "roll.usable_width_mm",
        "construction.method",
    ]
    info = read_model_json(model_dir)
    report: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "engine_version": __version__,
        "model_id": info["id"],
        "panels": [
            {
                "id": f"P{p.index + 1}",
                "name": p.name,
                "region": p.region,
                "area_m2": round(p.area_mm2 / 1e6, 4),
                "flat_width_mm": round(p.width_mm, 1),
                "flat_length_mm": round(p.length_mm, 1),
                "fits_roll": bool(p.width_mm <= usable),
                "triangles": len(p.faces),
                "seams": p.seams,
            }
            for p in result
        ],
        "seams": [
            {
                "id": s.id,
                "kind": s.kind,
                "panels": [result[s.panels[0]].name, result[s.panels[1]].name],
                "length_mm": round(s.length_mm, 1),
                "lap_side": result[s.lap_panel].name,
                "min_radius_mm": None if math.isinf(s.min_radius_mm) else round(s.min_radius_mm, 1),
            }
            for s in infos
        ],
        "tight_seams": [s.id for s in tight_seams],
        "hem_length_mm": round(float(np.linalg.norm(v[hem[:, 0]] - v[hem[:, 1]], axis=1).sum()), 1),
        "area_m2": round(float(mesh.area) / 1e6, 4),
        "parameters": {k: params[k] for k in keys},
        "parameter_sources": {k: params.source(k) for k in keys},
        "warnings": warnings,
    }
    seams_used = {
        "format_version": FORMAT_VERSION,
        "skirt_seams": [[round(float(c), 1) for c in line.at(s)[0]] for s in positions],
        "top_seams": [[[round(float(c), 1) for c in p] for p in pts] for pts in top_lines],
        "level_seams_mm": [round(z, 1) for z in levels],
    }
    report["seams_used"] = seams_used
    return Cut(result, infos, report, warnings, mesh, opened, lab, edge_seam)


def _lap(kind: str, a: Panel, b: Panel) -> int:
    """Which panel laps over the other: the top over skirt and walls, the higher over the lower
    (a wall over the skirt, on top seams), and on vertical seams the panel facing the front
    (water run-off, CLAUDE.md rule 6)."""
    if kind in ("skirt", "wall") and TOP in (a.region, b.region):
        return a.index if a.region == TOP else b.index
    if kind == "corner":
        fa = (np.asarray(a.mesh.face_normals)[:, 1] * a.mesh.area_faces).sum() / a.mesh.area
        fb = (np.asarray(b.mesh.face_normals)[:, 1] * b.mesh.area_faces).sum() / b.mesh.area
        return a.index if fa <= fb else b.index
    za = float(np.asarray(a.mesh.vertices)[:, 2].mean())
    zb = float(np.asarray(b.mesh.vertices)[:, 2].mean())
    return a.index if za >= zb else b.index


def write_cut(model_dir: Path, result: Cut, out_dir: Path | None = None) -> Path:
    out = out_dir or model_dir
    out.mkdir(parents=True, exist_ok=True)
    assert result.opened is not None and result.labels is not None
    edges = sorted(result.seam_edges.items())
    np.savez_compressed(
        out / PANELS_NPZ,
        vertices=np.asarray(result.opened.vertices, dtype=np.float64),
        faces=np.asarray(result.opened.faces, dtype=np.int64),
        labels=result.labels,
        original_vertex=np.asarray(result.opened.metadata["original_vertex"], dtype=np.int64),
        seam_edges=np.array([e for e, _ in edges], dtype=np.int64).reshape(-1, 2),
        seam_index=np.array([i for _, i in edges], dtype=np.int64),
    )
    report = dict(result.report)
    seams_used = report.pop("seams_used")
    (out / PANELS_JSON).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / SEAMS_AUTO_JSON).write_text(
        json.dumps(seams_used, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    hull_json = model_dir / "hull.json"
    given = hull_json.is_file() and json.loads(hull_json.read_text()).get("top") == "given"
    # a cover surface upload: the "furniture" is the cover itself; drawn twice it flickers
    meshes = [] if given else [("furniture", _coloured(load_model(model_dir), MODEL_RGBA))]
    for p in result.panels:
        r, g, b = piece_colour(p.index)  # the house-style piece colours (palette.py)
        rgba = (int(r * 255), int(g * 255), int(b * 255), 255)  # param-ok: 8-bit colour
        meshes.append((p.name, _coloured(p.mesh, rgba)))
    (out / PANELS_GLB).write_bytes(glb_bytes(meshes))
    return out
