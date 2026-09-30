"""`cover hull`: the drape hull of an imported model (ADR-010, ADR-024).

models/<id>/hull.glb     the cover surface: mm, Z up, open at the hem, faces outward
models/<id>/hull.json    quality report and the parameters used
models/<id>/preview.glb  furniture (grey) and cover (see-through blue), for viewing
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pymeshlab
import trimesh
from numpy.typing import NDArray
from scipy.ndimage import binary_fill_holes
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from trimesh.grouping import group_rows

from coverengine import __version__
from coverengine.errors import CoverError
from coverengine.hull import clearance, drainage, masks, support
from coverengine.hull.heightmap import HeightMap, rasterize
from coverengine.hull.morphology import close
from coverengine.hull.surface import (
    BAND_CELLS,
    BELOW_HEM_CELLS,
    FAR_MM,
    mesh_solid,
    solid_field,
)
from coverengine.hull.tension import concave_envelope
from coverengine.io.model_io import glb_bytes, load_model, read_model_json
from coverengine.params import EffectiveParams

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]

FORMAT_VERSION = 1
HULL_GLB, HULL_JSON, PREVIEW_GLB = "hull.glb", "hull.json", "preview.glb"
# Taubin smoothing filter coefficients (lambda, mu): the classic volume-preserving pair.
TAUBIN = (0.5, 0.53)  # param-ok: filter coefficients, not a setting
# Preview colours (RGBA 0-255): furniture grey, cover blue and see-through.
MODEL_RGBA = (150, 150, 150, 255)  # param-ok: display colour
HULL_RGBA = (40, 120, 220, 110)  # param-ok: display colour
# Preview: water spots in red, lifted off the cover so they do not flicker through it.
WATER_RGBA = (220, 30, 30, 255)  # param-ok: display colour
WATER_LIFT_MM = 2.0
# A face counts as part of the top when its normal points up at least this much (cosine).
WATER_FACING_UP = 0.3
# Points within this many grid cells of the crease between skirt and top are made sharp.
CREASE_CELLS = 2
# ... but only where the top next to the skirt is flatter than this (a real crease).
CREASE_MAX_SLOPE_DEG = 60.0  # param-ok: geometric threshold
# A model counts as mirror-symmetric when its height map differs from its mirror by less (mm).
SYMMETRY_MM = 0.5  # param-ok: geometric tolerance, not a setting
# Resolution steps when the grid is made coarser to fit max_grid_cells.
COARSEN_STEP_MM = 0.5  # param-ok: rounding step for the coarsened resolution


@dataclass
class Hull:
    mesh: trimesh.Trimesh
    report: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    water_faces: IntArray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))


def _p(params: EffectiveParams, key: str) -> float:
    return float(params[key])  # type: ignore[arg-type]


def _resolution(
    size: Array, margin: float, top_span: float, params: EffectiveParams
) -> tuple[float, list[str]]:
    """Grid resolution, made coarser if the 3D field would exceed hull.max_grid_cells."""
    h = _p(params, "hull.resolution_mm")
    limit = _p(params, "hull.max_grid_cells")

    def cells(step: float) -> float:
        nz = top_span / step + 2 * BELOW_HEM_CELLS + 2
        return ((size[0] + 2 * margin) / step + 2) * ((size[1] + 2 * margin) / step + 2) * nz

    if cells(h) <= limit:
        return h, []
    coarse = h
    while cells(coarse) > limit:
        coarse = (
            math.ceil(coarse * (cells(coarse) / limit) ** (1 / 3) / COARSEN_STEP_MM)
            * COARSEN_STEP_MM
        )
    return coarse, [
        f"model too large for a {h:g} mm grid within hull.max_grid_cells; used {coarse:g} mm"
    ]


def _remesh(mesh: trimesh.Trimesh, params: EffectiveParams) -> trimesh.Trimesh:
    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(np.asarray(mesh.vertices), np.asarray(mesh.faces)))
    ms.meshing_isotropic_explicit_remeshing(
        targetlen=pymeshlab.PureValue(_p(params, "hull.target_edge_length_mm")),
        iterations=int(params["hull.remesh_passes"]),
        checksurfdist=True,
        maxsurfdist=pymeshlab.PureValue(_p(params, "hull.remesh_max_deviation_mm")),
    )
    out = ms.current_mesh()
    return trimesh.Trimesh(out.vertex_matrix(), out.face_matrix(), process=False)


def _boundary_vertices(mesh: trimesh.Trimesh) -> IntArray:
    edges = mesh.edges_sorted
    return np.unique(edges[group_rows(edges, require_count=1)])


def _ridges(mesh: trimesh.Trimesh, angle_deg: float) -> tuple[int, float]:
    """Chains of edges sharper than the angle (seam candidates) and their total length."""
    sharp = mesh.face_adjacency_angles > math.radians(angle_deg)
    edges = mesh.face_adjacency_edges[sharp]
    if len(edges) == 0:
        return 0, 0.0
    n = len(mesh.vertices)
    graph = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(n, n))
    _, labels = connected_components(graph, directed=False)
    chains = len(np.unique(labels[np.unique(edges)]))
    length = float(
        np.linalg.norm(mesh.vertices[edges[:, 0]] - mesh.vertices[edges[:, 1]], axis=1).sum()
    )
    return chains, length


def build_hull(model_dir: Path, params: EffectiveParams) -> Hull:
    if not params["hull.sweep_down"]:
        raise CoverError(
            "hull.sweep_down = false (a fitted shell) is not available yet; it is planned for "
            "cushion-like models (ADR-024)"
        )
    model = load_model(model_dir)
    model_v, model_f = masks.apply(model.vertices, model.faces, masks.load_masks(model_dir))
    c = _p(params, "hull.clearance_mm")
    bridge_r = _p(params, "hull.bridge_gap_mm") / 2
    hem = _p(params, "hull.hem_height_mm")
    lo, hi = model_v.min(axis=0), model_v.max(axis=0)
    if hi[2] <= hem:
        raise CoverError(f"the model is not higher than the hem ({hem:g} mm)")
    margin = c + bridge_r
    h, warnings = _resolution(hi - lo, margin, hi[2] + c - hem, params)
    margin += (BAND_CELLS + 2) * h

    hm = rasterize(model_v, model_f, h, margin)
    bridged = HeightMap(close(hm.z, bridge_r, h), hm.x0, hm.y0, h)
    top, wall = solid_field(bridged, c, model_v, model_f, str(params["hull.edge"]))
    covered = (top > hem) & (wall > 0)
    # a cover has no holes seen from above: an area the furniture encloses (the frame of a
    # folding chair) is spanned by the top, not left as a tube down to the floor
    filled = binary_fill_holes(covered)
    holes = filled & ~covered
    if holes.any():
        wall = np.where(holes, np.maximum(wall, h), wall)
        top = np.where(holes, np.maximum(top, hem + h), top)
        covered = filled
    min_slope = _p(params, "hull.min_slope_deg")
    patch = _p(params, "hull.flat_patch_mm")
    held: support.Support | None = None
    if params["hull.top"] == "tensioned":
        if params["hull.support"] == "frame":
            tight, held = support.frame(
                top, covered, bridged.xs, bridged.ys, _p(params, "hull.support_height_mm"),
                min_slope, patch,
            )  # fmt: skip
        elif params["hull.support"] == "balloon":
            tight, held = support.balloon(
                top, covered, bridged.xs, bridged.ys, _p(params, "hull.support_radius_mm"),
                _p(params, "hull.support_height_mm"), min_slope, patch,
            )  # fmt: skip
        else:
            tight = concave_envelope(top, covered, bridged.xs, bridged.ys)
        top = np.where(covered, tight, top)
    # outside the planform the wall field alone decides where the skirt is
    top = np.where(wall <= 0, FAR_MM, top)
    water = drainage.check(top, covered, bridged.xs, bridged.ys, min_slope, patch)
    if not water.drains:
        x, y = water.worst_xy_mm or (0.0, 0.0)
        warnings.append(
            f"water would stay on the cover near x {x:.0f}, y {y:.0f} mm "
            f"({water.flat_area_mm2 / 1e6:.2f} m2 flat, {water.hollow_area_mm2 / 1e6:.2f} m2 "
            "hollow); for a flat top set hull.support = balloon"
        )
    mesh = mesh_solid(top, wall, hm.x0, hm.y0, h, hem)
    mesh = trimesh.Trimesh(mesh.vertices, mesh.faces, process=True)  # weld duplicate vertices
    mesh = _one_piece(mesh)
    iterations = round(_p(params, "hull.smoothing") * _p(params, "hull.smoothing_max_iterations"))
    if iterations > 0:
        trimesh.smoothing.filter_taubin(mesh, lamb=TAUBIN[0], nu=TAUBIN[1], iterations=iterations)
    mesh = trimesh.intersections.slice_mesh_plane(
        mesh, plane_normal=[0.0, 0.0, 1.0], plane_origin=[0.0, 0.0, hem], cap=False
    )
    mesh = _remesh(mesh, params)
    # the remesher can leave duplicate points (hairline cracks); weld them, or the cracks count
    # as hem and the cover is not one closed surface
    mesh = trimesh.Trimesh(mesh.vertices, mesh.faces, process=True)
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    hem_vertices = _boundary_vertices(mesh)
    v = np.asarray(mesh.vertices).copy()
    v[hem_vertices, 2] = hem  # the hem edge lies exactly at hem height
    if params["hull.edge"] == "sharp":
        v = _sharpen(v, top, wall, bridged.xs, bridged.ys, h, hem_vertices)
    mesh.vertices = v
    # symmetric furniture: build one half and mirror it, so mirrored panels are equal
    symmetric = _mirror_symmetric(hm)
    if symmetric:
        mesh = _mirrored(mesh, _p(params, "seams.snap_mm"))
        hem_vertices = _boundary_vertices(mesh)
    fit = clearance.enforce(
        mesh, model_v, model_f, c, int(params["hull.clearance_passes"]), hem_vertices
    )
    if fit.min_mm < c:
        warnings.append(f"closest point is {fit.min_mm:.2f} mm from the furniture (< clearance)")

    v = np.asarray(mesh.vertices)
    edges = mesh.edges_sorted[group_rows(mesh.edges_sorted, require_count=1)]
    chains, ridge_mm = _ridges(mesh, _p(params, "seams.ridge_angle_deg"))
    info = read_model_json(model_dir)
    keys = [k for k in params.keys() if k.startswith("hull.")] + ["seams.ridge_angle_deg"]
    report: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "engine_version": __version__,
        "model_id": info["id"],
        "model_sha256": info["source"]["sha256"],
        "resolution_used_mm": h,
        "mesh": {"vertices": len(v), "triangles": len(mesh.faces)},
        "area_m2": round(float(mesh.area) / 1e6, 6),
        "bbox_mm": [[round(float(x), 3) for x in v.min(0)], [round(float(x), 3) for x in v.max(0)]],
        "hem": {
            "height_mm": hem,
            "length_mm": round(
                float(np.linalg.norm(v[edges[:, 0]] - v[edges[:, 1]], axis=1).sum()), 3
            ),
        },
        "distance_to_model_mm": {
            "min": round(fit.min_mm, 3),
            "mean_at_vertices": round(fit.mean_vertex_mm, 3),
            "clearance": c,
        },
        "clearance_repair": {
            "vertices_moved": fit.vertices_moved,
            "max_move_mm": round(fit.max_move_mm, 3),
        },
        "ridges": {
            "chains": chains,
            "length_mm": round(ridge_mm, 1),
            "angle_deg": _p(params, "seams.ridge_angle_deg"),
        },
        "top": params["hull.top"],
        "drainage": water.summary(),
        "support": None
        if held is None
        else {
            "kind": held.kind,
            "centre_mm": [round(held.centre_mm[0], 1), round(held.centre_mm[1], 1)],
            "radius_mm": round(held.radius_mm, 1),
            "height_mm": round(held.height_mm, 1),
            "automatic": held.automatic,
        },
        "masks": len(masks.load_masks(model_dir)),
        "mirrored": symmetric,
        "parameters": {k: params[k] for k in keys},
        "parameter_sources": {k: params.source(k) for k in keys},
        "parameter_hash": params.hash(),
        "warnings": warnings,
    }
    return Hull(mesh, report, warnings, _water_faces(mesh, water, hm.x0, hm.y0, h))


def _water_faces(
    mesh: trimesh.Trimesh, water: drainage.Drainage, x0: float, y0: float, h: float
) -> IntArray:
    """Upward-facing hull faces over the cells where water would stay (for the preview)."""
    if water.drains:
        return np.zeros(0, dtype=np.int64)
    c = mesh.triangles_center
    i = np.clip(np.rint((c[:, 0] - x0) / h).astype(np.int64), 0, water.problem.shape[0] - 1)
    j = np.clip(np.rint((c[:, 1] - y0) / h).astype(np.int64), 0, water.problem.shape[1] - 1)
    up = mesh.face_normals[:, 2] > WATER_FACING_UP
    return np.flatnonzero(up & water.problem[i, j])


def _sharpen(
    v: Array, top: Array, wall: Array, xs: Array, ys: Array, h: float, hem_vertices: IntArray
) -> Array:
    """Make the crease between the skirt and the top sharp again. Meshing and smoothing round
    it over a few cells; such a lip cannot lie flat in either panel. Points near the crease move
    onto the nearer of the two surfaces: the wall (outward, until the wall field is 0) or the
    top (to its height)."""
    from scipy.interpolate import RegularGridInterpolator

    top_ok = np.where(np.abs(top) < FAR_MM / 2, top, np.nan)
    at_top = RegularGridInterpolator((xs, ys), top_ok, bounds_error=False, fill_value=np.nan)
    at_wall = RegularGridInterpolator((xs, ys), wall, bounds_error=False, fill_value=np.nan)
    out = v.copy()
    xy = v[:, :2]
    dw = at_wall(xy)  # distance inside the outline (the wall field is 0 on the skirt)
    tz = at_top(xy)
    zone = CREASE_CELLS * h
    # only where there is a crease: next to the skirt the top is clearly less steep than a wall
    # (a rounded top that curves smoothly into the skirt, like a dome, is left alone)
    gx, gy = np.gradient(np.where(np.isfinite(top_ok), top_ok, np.nan), h)
    steep = RegularGridInterpolator(
        (xs, ys), np.hypot(gx, gy), bounds_error=False, fill_value=np.nan
    )
    inner = xy + 0.0  # the slope is read one zone further in, on the top itself
    grad_w = np.column_stack(
        [
            (at_wall(xy + [h / 2, 0.0]) - at_wall(xy - [h / 2, 0.0])) / h,
            (at_wall(xy + [0.0, h / 2]) - at_wall(xy - [0.0, h / 2])) / h,
        ]
    )
    norm = np.linalg.norm(grad_w, axis=1, keepdims=True)
    inner = xy + np.where(norm > 0, grad_w / np.maximum(norm, 1e-12), 0.0) * zone
    crease = steep(inner) < math.tan(math.radians(CREASE_MAX_SLOPE_DEG))
    near = np.isfinite(dw) & np.isfinite(tz) & (dw < zone) & (v[:, 2] > tz - zone) & crease
    near[hem_vertices] = False
    if not near.any():
        return out
    to_wall = near & (np.maximum(dw, 0.0) < (tz - v[:, 2]))
    to_top = near & ~to_wall
    out[to_top, 2] = tz[to_top]
    # onto the wall: step outward along the wall field's gradient by its value
    step = h / 2
    gx = (at_wall(xy + [step, 0.0]) - at_wall(xy - [step, 0.0])) / (2 * step)
    gy = (at_wall(xy + [0.0, step]) - at_wall(xy - [0.0, step])) / (2 * step)
    g2 = np.maximum(gx**2 + gy**2, 1e-12)
    ok = to_wall & np.isfinite(g2)
    out[ok, 0] -= (dw * gx / g2)[ok]
    out[ok, 1] -= (dw * gy / g2)[ok]
    return out


def _one_piece(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """The cover is one piece of surface: loose fragments (a few mm2 left by meshing small
    gaps) are dropped, the largest connected part is kept."""
    parts = mesh.split(only_watertight=False)
    if len(parts) <= 1:
        return mesh
    keep = max(parts, key=lambda m: float(m.area))
    return trimesh.Trimesh(keep.vertices, keep.faces, process=True)


def _mirror_symmetric(hm: HeightMap) -> bool:
    """Is the furniture symmetric about x = 0 (its height map equals its mirror image)?"""
    if not np.allclose(hm.xs[::-1], -hm.xs, atol=1e-9):
        return False
    z, mirror = hm.z, hm.z[::-1, :]
    same_footprint = np.array_equal(np.isfinite(z), np.isfinite(mirror))
    both = np.isfinite(z) & np.isfinite(mirror)
    return bool(
        same_footprint and both.any() and np.abs(z[both] - mirror[both]).max() < SYMMETRY_MM
    )


def _mirrored(mesh: trimesh.Trimesh, snap_mm: float) -> trimesh.Trimesh:
    """The x >= 0 half of the cover and its mirror image, joined at x = 0, so mirrored panels
    come out exactly equal."""
    v = np.asarray(mesh.vertices, dtype=np.float64).copy()
    v[np.abs(v[:, 0]) < snap_mm, 0] = 0.0  # no slivers along the cut
    half = trimesh.Trimesh(v, mesh.faces, process=False)
    half = trimesh.intersections.slice_mesh_plane(
        half, plane_normal=[1.0, 0.0, 0.0], plane_origin=[0.0, 0.0, 0.0], cap=False
    )
    hv = np.asarray(half.vertices).copy()
    hv[np.abs(hv[:, 0]) < 1e-9, 0] = 0.0
    other = hv * np.array([-1.0, 1.0, 1.0])
    faces = np.asarray(half.faces)
    joined = trimesh.Trimesh(
        np.vstack([hv, other]),
        np.vstack([faces, faces[:, ::-1] + len(hv)]),  # mirroring flips the winding back
        process=True,  # welds the shared vertices on x = 0
    )
    joined.update_faces(joined.nondegenerate_faces())
    joined.remove_unreferenced_vertices()
    return joined


def _coloured(mesh: trimesh.Trimesh, rgba: tuple[int, int, int, int]) -> trimesh.Trimesh:
    out = trimesh.Trimesh(mesh.vertices, mesh.faces, process=False)
    material = trimesh.visual.material.PBRMaterial(
        baseColorFactor=list(rgba),
        alphaMode="BLEND" if rgba[3] < 255 else "OPAQUE",
        doubleSided=True,
        metallicFactor=0.0,
        roughnessFactor=1.0,
    )
    out.visual = trimesh.visual.TextureVisuals(material=material)
    return out


def write_hull(model_dir: Path, hull: Hull, out_dir: Path | None = None) -> Path:
    out = out_dir or model_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / HULL_GLB).write_bytes(glb_bytes([("hull", hull.mesh)]))
    (out / HULL_JSON).write_text(
        json.dumps(hull.report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    model = load_model(model_dir)
    preview = [
        ("furniture", _coloured(model, MODEL_RGBA)),
        ("cover", _coloured(hull.mesh, HULL_RGBA)),
    ]
    if len(hull.water_faces):
        spots = trimesh.Trimesh(
            hull.mesh.vertices, hull.mesh.faces[hull.water_faces], process=False
        )
        spots.remove_unreferenced_vertices()
        spots.vertices = spots.vertices + spots.vertex_normals * WATER_LIFT_MM
        preview.append(("water", _coloured(spots, WATER_RGBA)))
    (out / PREVIEW_GLB).write_bytes(glb_bytes(preview))
    return out
