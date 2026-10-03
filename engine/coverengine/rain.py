"""`cover rain`: where rain goes on a cover (ADR-049, docs/plans/rain-simulation.md).

The cover surface (hull.glb) is laid on a grid seen from above. Then:

- hollows: every cell is filled up to the lowest edge it can overflow from (priority flood); a
  cell more than `rain.pond_mm` under that level is a pond;
- flat parts: cells flatter than `hull.min_slope_deg` that are no pond (water stands there);
- streams: how much of the cover drains through each cell (flow accumulation on the filled
  surface), and drops traced down the steepest way, for the 3D view;
- sag: a pond weighs on the fabric; between supports (where the cover rests on the furniture
  or a balloon) it sags by about (water load × span²) / (8 × `rain.fabric_tension_n_per_m`),
  which deepens the pond; repeated, the pond either settles or keeps growing (ponding);
- seams: drops that run along a seam for a long way (water soaks into the stitching).

The AI (DeepSeek) gets the numbers and a top view with streams and ponds and gives a verdict
and advice in plain words. Results: rain.json, rain.glb (ponds and flat parts in blue).
"""

from __future__ import annotations

import base64
import heapq
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from numpy.typing import NDArray
from scipy import ndimage

from coverengine.hull.heightmap import rasterize
from coverengine.io.model_io import glb_bytes, load_model
from coverengine.params import EffectiveParams

Array = NDArray[np.float64]
RAIN_JSON, RAIN_GLB, RAIN_PNG = "rain.json", "rain.glb", "rain.png"
STREAM_FROM = 0.45  # param-ok: display: a point is a stream from this share of the most flow
POND_FULL_MM = 30.0  # param-ok: display: a pond this deep is full red
# the rain on the cover as it really lies, after the drape (ADR-057): the same, and a heatmap
WET_JSON, WET_GLB, WET_PNG = "drape_rain.json", "drape_rain.glb", "drape_rain.png"
G = 9.81  # param-ok: gravity (m/s2)
WATER_KG_M3 = 1000.0  # param-ok: density of water
MM_PER_M = 1000.0  # param-ok: unit conversion
M2 = 1e6  # param-ok: mm2 per m2
LITRE_MM3 = 1e6  # param-ok: mm3 per litre
SAG_ROUNDS = 6  # param-ok: iterations of the sag estimate
SLOPE_MARGIN_DEG = 0.5  # param-ok: grid reading of a slope
SETTLED_MM = 0.05  # param-ok: the sag has settled when it changes less than this
SAG_SPAN_DIVISOR = 8.0  # param-ok: the membrane formula, load x span^2 / (8 T)
GROWS = 1.5  # param-ok: a pond whose volume grows by more than this keeps growing (ponding)
ALONG_COS = 0.9  # param-ok: a drop runs along a seam when its direction is this close
NEAR_SEAM_MM = 15.0  # param-ok: and it is this close to the seam
LIFT_MM = 2.0  # param-ok: the blue water surfaces just above the cover
POND_RGBA = (40, 110, 220, 190)  # param-ok: display colour
POND_RGB, FLAT_RGB, STREAM_RGB = (0.12, 0.45, 0.9), (0.55, 0.8, 0.95), (0.15, 0.3, 0.75)
TITLE_PT = 7.5  # param-ok: display
FLAT_RGBA = (120, 190, 240, 140)  # param-ok: display colour
PATH_POINTS = 80  # param-ok: points per drop path at most
NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _p(params: EffectiveParams, key: str) -> float:
    return float(params[key])  # type: ignore[arg-type]


def fill(z: Array) -> Array:
    """Priority flood: every cell raised to the level at which water can leave the cover."""
    inside = np.isfinite(z)
    filled = np.where(inside, np.inf, -np.inf)
    done = ~inside
    heap: list[tuple[float, int, int]] = []
    edge = inside & ndimage.binary_dilation(~inside, structure=np.ones((3, 3)))
    edge[0, :] |= inside[0, :]
    edge[-1, :] |= inside[-1, :]
    edge[:, 0] |= inside[:, 0]
    edge[:, -1] |= inside[:, -1]
    for i, j in zip(*np.nonzero(edge), strict=True):
        filled[i, j] = z[i, j]
        done[i, j] = True
        heapq.heappush(heap, (float(z[i, j]), int(i), int(j)))
    ni, nj = z.shape
    while heap:
        level, i, j = heapq.heappop(heap)
        for di, dj in NEIGHBOURS:
            a, b = i + di, j + dj
            if 0 <= a < ni and 0 <= b < nj and not done[a, b]:
                done[a, b] = True
                filled[a, b] = max(float(z[a, b]), level)
                heapq.heappush(heap, (float(filled[a, b]), a, b))
    return filled


def accumulate(filled: Array, inside: NDArray[np.bool_]) -> tuple[Array, NDArray[np.int64]]:
    """Flow accumulation (cells draining through each cell) and each cell's downhill neighbour
    (flat parts of the filled surface drain towards the nearest edge)."""
    ni, nj = filled.shape
    dist = ndimage.distance_transform_edt(inside)
    # a tiny slope towards the edge, so filled ponds and flat parts drain somewhere
    key = np.where(inside, filled + dist * 1e-6, -np.inf)  # param-ok: tie breaker
    order = np.argsort(-key, axis=None)
    down = np.full(ni * nj, -1, dtype=np.int64)
    acc = np.where(inside, 1.0, 0.0).ravel()
    flat = key.ravel()
    for idx in order:
        if not inside.flat[idx]:
            continue
        i, j = divmod(int(idx), nj)
        best, best_z = -1, flat[idx]
        for di, dj in NEIGHBOURS:
            a, b = i + di, j + dj
            if 0 <= a < ni and 0 <= b < nj:
                k = a * nj + b
                drop = (flat[idx] - flat[k]) / math.hypot(di, dj)
                if flat[k] < best_z and (best < 0 or drop > (flat[idx] - best_z)):
                    best, best_z = k, flat[k]
        down[idx] = best
        if best >= 0:
            acc[best] += acc[idx]
    return acc.reshape(ni, nj), down


def simulate(
    model_dir: Path, params: EffectiveParams, use_ai: bool = True, surface: str = "design"
) -> dict[str, Any]:
    """surface: "design" (the designed cover surface, hull.glb) or "drape" (the sewn cover as
    it lies after `cover drape`, drape.glb: ADR-057)."""
    if surface not in ("design", "drape"):
        raise ValueError(f"surface: design or drape, not {surface!r}")
    draped = surface == "drape"
    json_name, glb_name, png_name = (WET_JSON, WET_GLB, WET_PNG) if draped else (
        RAIN_JSON, RAIN_GLB, RAIN_PNG)  # fmt: skip
    if draped and not (model_dir / "drape.glb").is_file():
        raise FileNotFoundError("no drape yet (cover drape first)")
    h = _p(params, "rain.cell_mm")
    cover = load_model(model_dir / ("drape.glb" if draped else "hull.glb"))
    hm = rasterize(cover.vertices, cover.faces, h, 2 * h)
    z = np.where(np.isfinite(hm.z), hm.z, np.nan)
    z = np.where(np.isnan(z), np.inf * -1, z)
    z = np.where(np.isinf(z), np.nan, z)
    inside = np.isfinite(z)
    zf = np.where(inside, z, -np.inf)
    filled = fill(np.where(inside, z, np.nan))
    depth = np.zeros_like(zf)
    np.subtract(filled, zf, out=depth, where=inside & np.isfinite(filled))
    pond = depth > _p(params, "rain.pond_mm")
    # flat parts from the cover's own faces (their true slope; a grid reads a 5 degree face as
    # 4 to 5 degrees): the faces facing up flatter than the minimum slope, shown on the grid
    limit = math.radians(_p(params, "hull.min_slope_deg") - SLOPE_MARGIN_DEG)
    up = cover.face_normals[:, 2]
    flat_faces = up > math.cos(limit)
    flat = np.zeros_like(inside)
    if flat_faces.any():
        fl = _same_grid(trimesh.Trimesh(cover.vertices, cover.faces[flat_faces], process=False),
                        hm, h)  # fmt: skip
        flat = inside & np.isfinite(fl) & (np.abs(fl - np.where(inside, zf, 0.0)) < h)
    flat &= ~pond
    acc, down = accumulate(filled, inside)

    # supports: where the cover rests on the furniture (or balloons) underneath
    furniture = load_model(model_dir)
    parts = [furniture]
    balloons = model_dir / "balloons.glb"
    if balloons.is_file():
        parts.append(load_model(balloons))
    under = trimesh.Trimesh(*_merged(parts), process=False)
    fm = _same_grid(under, hm, h)
    support = inside & np.isfinite(fm) & (zf - fm < _p(params, "rain.support_mm"))
    span = 2 * ndimage.distance_transform_edt(~support) * h  # mm across to the next support

    ponds: list[dict[str, Any]] = []
    labels, n = ndimage.label(pond, structure=np.ones((3, 3)))
    tension = _p(params, "rain.fabric_tension_n_per_m")
    for k in range(1, n + 1):
        m = labels == k
        d = depth[m]
        area = float(m.sum()) * h * h
        volume = float(d.sum()) * h * h
        grown, rounds = d.copy(), 0
        for rounds in range(1, SAG_ROUNDS + 1):  # noqa: B007 - the last round is reported
            load = WATER_KG_M3 * G * grown / MM_PER_M  # N/m2
            sag = load * (span[m] / MM_PER_M) ** 2 / (SAG_SPAN_DIVISOR * tension) * MM_PER_M
            new = d + sag
            if np.allclose(new, grown, atol=SETTLED_MM):
                break
            grown = new
        growth = float(grown.sum()) / max(float(d.sum()), 1e-9)
        ii, jj = np.nonzero(m)
        ponds.append(
            {
                "area_m2": round(area / M2, 3),
                "volume_l": round(volume / LITRE_MM3, 2),
                "max_depth_mm": round(float(d.max()), 1),
                "span_mm": round(float(span[m].max())),
                "volume_with_sag_l": round(float(grown.sum()) * h * h / LITRE_MM3, 2),
                "keeps_growing": bool(growth > GROWS),
                "centre_mm": [
                    round(float(hm.xs[int(ii.mean())])),
                    round(float(hm.ys[int(jj.mean())])),
                ],
            }
        )
    ponds.sort(key=lambda p: -p["volume_l"])

    drops, exits = _drops(hm, zf, inside, pond, down, params)
    # the seams' places are the designed ones; on the draped cover they have moved
    seams = [] if draped else _seams_along(model_dir, drops, params)
    stream_cells = acc > max(acc.max() * 0.05, 1.0)  # param-ok: the main streams
    out: dict[str, Any] = {
        "format_version": 1,
        "surface": surface,
        "cell_mm": h,
        "cover_area_m2": round(float(inside.sum()) * h * h / M2, 2),
        "ponds": ponds,
        "pond_area_m2": round(sum(p["area_m2"] for p in ponds), 3),
        "pond_volume_l": round(sum(p["volume_l"] for p in ponds), 2),
        "flat_area_m2": round(float(flat.sum()) * h * h / M2, 3),
        "growing_ponds": sum(p["keeps_growing"] for p in ponds),
        "exits": exits,
        "seams_along": seams,
        "streams_share": round(float(stream_cells.sum()) / max(float(inside.sum()), 1.0), 3),
        "dry": not ponds and float(flat.sum()) * h * h < _p(params, "hull.flat_patch_mm") ** 2,
        "drops": drops,
    }
    if draped:
        out["heat"] = heatmap(model_dir / glb_name, cover, hm, zf, filled, acc, pond, flat, h)
    else:
        _write_glb(model_dir / glb_name, hm, filled, pond, flat, h)
    _picture(model_dir / png_name, hm, zf, acc, pond, flat, inside)
    if use_ai:
        out["ai"] = _advice(model_dir / png_name, out, params)
    # strict JSON: a browser cannot read Infinity or NaN
    (model_dir / json_name).write_text(json.dumps(out, allow_nan=False) + "\n", encoding="utf-8")
    return out


def _merged(parts: list[trimesh.Trimesh]) -> tuple[Array, NDArray[np.int64]]:
    v, f, off = [], [], 0
    for m in parts:
        v.append(np.asarray(m.vertices))
        f.append(np.asarray(m.faces) + off)
        off += len(m.vertices)
    return np.vstack(v), np.vstack(f)


def _same_grid(mesh: trimesh.Trimesh, hm: Any, h: float) -> Array:
    """The mesh's top heights on the cover's grid (NaN where nothing is under the cover)."""
    other = rasterize(mesh.vertices, mesh.faces, h, 0.0)
    out = np.full(hm.z.shape, np.nan)
    oi = np.rint((hm.xs - other.x0) / h).astype(int)
    oj = np.rint((hm.ys - other.y0) / h).astype(int)
    vi = (oi >= 0) & (oi < other.z.shape[0])
    vj = (oj >= 0) & (oj < other.z.shape[1])
    sub = other.z[np.ix_(oi[vi], oj[vj])]
    out[np.ix_(np.flatnonzero(vi), np.flatnonzero(vj))] = np.where(np.isfinite(sub), sub, np.nan)
    return out


def _drops(
    hm: Any, zf: Array, inside: NDArray[np.bool_], pond: NDArray[np.bool_],
    down: NDArray[np.int64], params: EffectiveParams,
) -> tuple[list[dict[str, Any]], dict[str, int]]:  # fmt: skip
    """Drops falling at random on the cover, each following the steepest way down."""
    rng = np.random.default_rng(0)
    cells = np.flatnonzero(inside.ravel())
    n = min(int(params["rain.drops"]), len(cells))
    start = rng.choice(cells, size=n, replace=False)
    nj = inside.shape[1]
    lo, hi = np.array([hm.xs[0], hm.ys[0]]), np.array([hm.xs[-1], hm.ys[-1]])
    centre = (lo + hi) / 2
    exits = {"front": 0, "back": 0, "left": 0, "right": 0, "pond": 0}
    out = []
    for c in start:
        path, k, ended = [], int(c), "edge"
        for _ in range(sum(inside.shape)):
            i, j = divmod(k, nj)
            if not inside[i, j]:  # over the edge: the drop leaves the cover
                break
            path.append([float(hm.xs[i]), float(hm.ys[j]), float(zf[i, j]) + LIFT_MM])
            if pond[i, j] and len(path) > 1:
                ended = "pond"
                break
            nxt = int(down[k])
            if nxt < 0:
                break
            k = nxt
        step = max(1, len(path) // PATH_POINTS)
        pts = path[::step] + ([path[-1]] if (len(path) - 1) % step else [])
        if ended == "pond":
            exits["pond"] += 1
        else:
            dx, dy = np.array(pts[-1][:2]) - centre
            span = (hi - lo) / 2
            if abs(dx) / max(span[0], 1) > abs(dy) / max(span[1], 1):
                exits["right" if dx > 0 else "left"] += 1
            else:
                exits["back" if dy > 0 else "front"] += 1
        out.append({"path": [[round(v, 1) for v in p] for p in pts], "ends": ended})
    return out, exits


def _seams_along(
    model_dir: Path, drops: list[dict[str, Any]], params: EffectiveParams
) -> list[dict[str, Any]]:
    """Seams that drops run along (not across) for more than `rain.seam_run_mm`."""
    npz = model_dir / "panels.npz"
    if not npz.is_file():
        return []
    data = np.load(npz)
    v, edges, index = data["vertices"], data["seam_edges"], data["seam_index"]
    if not len(edges):
        return []
    a, b = v[edges[:, 0], :2], v[edges[:, 1], :2]
    from scipy.spatial import cKDTree

    mid = (a + b) / 2
    seam_dir = (b - a) / np.maximum(np.linalg.norm(b - a, axis=1, keepdims=True), 1e-9)
    tree = cKDTree(mid)
    run = np.zeros(int(index.max()) + 1)
    for d in drops:
        p = np.asarray(d["path"])[:, :2]
        if len(p) < 2:
            continue
        seg = np.diff(p, axis=0)
        length = np.linalg.norm(seg, axis=1)
        unit = seg / np.maximum(length[:, None], 1e-9)
        dist, near = tree.query((p[:-1] + p[1:]) / 2)
        along = (dist < NEAR_SEAM_MM) & (
            np.abs(np.einsum("ij,ij->i", unit, seam_dir[near])) > ALONG_COS
        )
        np.add.at(run, index[near[along]], length[along])
    limit = _p(params, "rain.seam_run_mm")
    names = _seam_names(model_dir)
    return [
        {"seam": names[int(s)], "run_mm": round(float(run[s]))}
        for s in np.flatnonzero(run > limit)
        if int(s) in names
    ]


def _seam_names(model_dir: Path) -> dict[int, str]:
    """Seam number -> its two pieces; only seams between two top pieces (water reaching the
    edge of the top falls over it, it does not run along the seam to an upright side)."""
    try:
        cut = json.loads((model_dir / "panels.json").read_text())
        region = {p["name"]: p["region"] for p in cut["panels"]}
        return {
            i: "/".join(s["panels"])
            for i, s in enumerate(cut["seams"])
            if all(region.get(n) == "top" for n in s["panels"])
        }
    except Exception:  # noqa: BLE001
        return {}


def _cells_mesh(
    mask: NDArray[np.bool_], height: Array, hm: Any, h: float
) -> trimesh.Trimesh | None:
    ii, jj = np.nonzero(mask)
    if not len(ii):
        return None
    x, y = hm.xs[ii], hm.ys[jj]
    zc = height[ii, jj] + LIFT_MM
    r = h / 2
    corners = np.stack([np.column_stack([x + dx, y + dy, zc]) for dx, dy in
                        ((-r, -r), (r, -r), (r, r), (-r, r))], axis=1)  # fmt: skip
    v = corners.reshape(-1, 3)
    base = np.arange(len(ii)) * 4
    f = np.concatenate([np.column_stack([base, base + 1, base + 2]),
                        np.column_stack([base, base + 2, base + 3])])  # fmt: skip
    return trimesh.Trimesh(v, f, process=False)


def _write_glb(path: Path, hm: Any, filled: Array, pond: Any, flat: Any, h: float) -> None:
    from coverengine.hull.build import _coloured

    parts = []
    pm = _cells_mesh(pond, np.where(np.isfinite(filled), filled, 0.0), hm, h)
    if pm is not None:
        parts.append(("ponds", _coloured(pm, POND_RGBA)))
    fl = _cells_mesh(flat, np.where(np.isfinite(filled), filled, 0.0), hm, h)
    if fl is not None:
        parts.append(("flat", _coloured(fl, FLAT_RGBA)))
    if parts:
        path.write_bytes(glb_bytes(parts))
    else:
        path.unlink(missing_ok=True)


def _picture(path: Path, hm: Any, zf: Array, acc: Array, pond: Any, flat: Any, inside: Any) -> None:
    """Top view: the cover in grey shades by height, streams dark blue, flat parts light blue,
    ponds blue (for the AI and the report)."""
    from matplotlib.figure import Figure

    fig = Figure(figsize=(6, 6 * zf.shape[1] / max(zf.shape[0], 1) + 0.6), dpi=110)
    ax = fig.add_axes((0.02, 0.02, 0.96, 0.9))
    img = np.full((*zf.shape, 3), 1.0)
    zn = np.where(inside, zf, np.nan)
    lo, hi = np.nanmin(zn), np.nanmax(zn)
    shade = 0.55 + 0.4 * (np.nan_to_num(zn, nan=lo) - lo) / max(hi - lo, 1.0)
    img[inside] = np.stack([shade, shade, shade], axis=-1)[inside]
    streams = inside & (np.log1p(acc) > np.log1p(acc.max()) * 0.55)  # param-ok: display
    img[streams] = STREAM_RGB
    img[flat] = FLAT_RGB
    img[pond] = POND_RGB
    ax.imshow(np.transpose(img, (1, 0, 2)), origin="lower")
    ax.set_title("rain: streams dark blue, flat parts light blue, ponds blue (front at the bottom)",
                 fontsize=TITLE_PT)  # fmt: skip
    ax.axis("off")
    fig.savefig(path, metadata={"Software": None})


# the heatmap's colours, from dry to a pond (RGBA): it runs off, water streams past, it stands
# on a flat part, a pond
HEAT_RGBA = {
    "dry": (133, 136, 111, 255),  # param-ok: display colour
    "stream": (230, 190, 60, 255),  # param-ok: display colour
    "flat": (230, 120, 40, 255),  # param-ok: display colour
    "pond": (178, 40, 30, 255),  # param-ok: display colour
}  # param-ok: display colours (house sage, amber, orange, red)


def heatmap(
    path: Path, cover: trimesh.Trimesh, hm: Any, zf: Array, filled: Array, acc: Array,
    pond: Any, flat: Any, h: float,
) -> dict[str, Any]:  # fmt: skip
    """The draped cover coloured by where water goes (ADR-057): every point seen from above gets
    the state of its grid cell: a pond (red, darker with depth), a flat part where water stands
    (orange), a stream that much water runs through (amber, by how much) or dry (sage). Points
    under the top (the sides) are dry: water runs down them."""
    v = np.asarray(cover.vertices)
    i = np.clip(np.searchsorted(hm.xs, v[:, 0]) - 1, 0, len(hm.xs) - 1)
    j = np.clip(np.searchsorted(hm.ys, v[:, 1]) - 1, 0, len(hm.ys) - 1)
    top = np.isfinite(zf[i, j]) & (v[:, 2] > zf[i, j] - 2 * h)  # seen from above
    gap = np.nan_to_num(filled[i, j], nan=0.0, posinf=0.0, neginf=0.0) - np.nan_to_num(
        zf[i, j], nan=0.0, posinf=0.0, neginf=0.0
    )
    depth = np.where(top & pond[i, j], gap, 0.0)
    flow = np.where(top, np.log1p(acc[i, j]) / max(float(np.log1p(acc.max())), 1e-9), 0.0)
    rgba = np.tile(np.array(HEAT_RGBA["dry"], float), (len(v), 1))
    stream = flow > STREAM_FROM
    t = np.clip((flow - STREAM_FROM) / (1 - STREAM_FROM), 0, 1)[:, None]
    rgba[stream] = (rgba * (1 - t) + np.array(HEAT_RGBA["stream"], float) * t)[stream]
    standing = top & flat[i, j]
    rgba[standing] = HEAT_RGBA["flat"]
    wet = depth > 0
    shade = np.clip(depth / POND_FULL_MM, 0.4, 1.0)[:, None]  # param-ok: a light pond still shows
    rgba[wet] = (np.array(HEAT_RGBA["flat"], float) * (1 - shade) +
                 np.array(HEAT_RGBA["pond"], float) * shade)[wet]  # fmt: skip
    from coverengine.io.model_io import linear_colours

    mesh = trimesh.Trimesh(v, cover.faces, vertex_colors=linear_colours(rgba), process=False)
    path.write_bytes(glb_bytes([("water", mesh)]))
    share = 100.0 / max(len(v), 1)  # param-ok: percent
    return {
        "pond_points_pct": round(share * float(wet.sum()), 1),
        "flat_points_pct": round(share * float((standing & ~wet).sum()), 1),
        "stream_points_pct": round(share * float((stream & ~standing & ~wet).sum()), 1),
    }


AI_SYSTEM = """You judge how rain behaves on an outdoor furniture cover for a cover workshop.
The program simulated it: ponds (hollows where water stays, with depth, area and volume, and
whether a pond keeps growing when the fabric sags under the water), flat parts (water stands
there), where the water leaves the cover, and seams the water runs along (stitching soaks).
The picture is the top view: streams dark blue, flat parts light blue, ponds blue. Facts: the
cover is open at the bottom; balloons under table covers and the furniture are the supports; a
slope of 5 degrees or more sheds water. Answer with JSON only:
{"verdict": "dry | risk | wet", "summary": "two or three plain sentences for the workshop",
 "risks": ["short plain sentences"], "suggestions": ["concrete changes: another balloon, a
 steeper slope, a seam moved, a gable instead of a flat top, ..."]}"""


def _advice(pic: Path, result: dict[str, Any], params: EffectiveParams) -> dict[str, Any]:
    from coverengine.ai import ask_parts, lessons_text

    facts = {k: v for k, v in result.items() if k != "drops"}
    parts: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(facts)}]
    if pic.is_file():
        data = base64.b64encode(pic.read_bytes()).decode()
        parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}})
    try:
        ans = ask_parts(params, AI_SYSTEM + lessons_text("all"), parts)
        ans.pop("_usage", None)
        return {"model": str(params["ai.model"]), **ans}
    except Exception as exc:  # noqa: BLE001 - the advice is extra
        return {"error": str(exc)}
