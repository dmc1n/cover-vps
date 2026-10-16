"""The air vents on the cover in 3D, to show them in the viewer (ADR-073).

The vents are placed on the flat skirt panels (`finish.place_vents`, in the coordinates of
`pattern.json`). To find where one sits on the cover, the panel is flattened again exactly as
`cover flatten` did (the same mesh, solver and settings, so the same flat panel; checked
against the stored outline) and each corner of the opening is carried back to 3D through the
flat triangle it lies in. Written by `cover export` as `vents.json`:

    {"format": 3, "lower_edge_z_mm": z, "logo": "placed" | "missing" | "none",
     "vents": [{"number": 1, "piece": "skirt-front", "centre_mm": [x, y, z],
                "corners_mm": [[x, y, z] x 4], "normal": [x, y, z], "size_mm": [w, h],
                "above_hem_mm": a, "bottom_z_mm": z, "height_line_mm": [[x, y, z] x 2],
                "sides": {"left": {"to": "seam", "name": "skirt-left", "mm": d,
                                   "line_mm": [[x, y, z] x 2]}, "right": {...}},
                "hood": {"seam_mm": [[x, y, z] x 2], "down": [x, y, z], "length_mm": l},
                "logo": {"corners_mm": [[x, y, z] x 4], "centre_mm": [x, y, z],
                         "below_seam_mm": [top, bottom], "size_mm": [w, h] (on the hood)}
                         | null}],
     "warnings": [...]}

Corners run bottom left, bottom right, top right, top left (as seen from outside); the normal
points out of the cover.

The measurements (ADR-111: the workshop checks a sewn cover against them) are the cutting
file's own numbers, read off the flat piece the vent is cut in, not estimated on the 3D surface:
`above_hem_mm` is the distance along the fabric from the cover's lower edge (the hem line) to
the opening's bottom edge (over a skirt too low for a vent, the skirt's height is added);
`sides` is the distance along the bottom edge of the piece from each side of the opening to the
nearest seam, or to a corner of the cover inside the piece (the bottom edge turns by
`CORNER_DEG` or more within `CORNER_SPAN_MM`), left and right as seen from outside.
`bottom_z_mm` is the opening's bottom above the ground and `lower_edge_z_mm` the cover's lowest
point, both in 3D. The `line_mm` and `height_line_mm` ends are the 3D points the viewer draws
the dimension lines between.

The logo (ADR-146) is the frame the PEN layer draws on each vent hood, where it lies on the
cover once the hood is sewn on: `logos_mm` of the vent's piece in `finished.json`, written by
`cover export` together with cut.dxf from the same frame (`finish.logo_frame`,
`finish.logo_on_cover`), carried to 3D like the opening. So the 3D view shows what the cutting
file says, never a second computation. `hood` is the hood's top stitch line (the PEN ring's top,
a seam allowance above the opening), the direction down the cover there and how far the hood
reaches below that line (to the ring's bottom: its sides are sewn down the ring);
`below_seam_mm` the logo's top and bottom edge under it, so the viewer can stand them out with
its hood. `logo` at the top is "placed" when every vent has
its logo, "none" when the cover's vents carry none (`features.vent_logo`), "missing" when
finished.json does not have them (exported before format 2, or out of step with pattern.json):
export again. Corners of a logo run bottom left, bottom right, top right, top left, from outside.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree

from coverengine.finish.finish import (
    FINISHED_JSON,
    HemRun,
    _ends,
    hood_size,
    logo_frame,
    place_vents,
    vent_bases,
    vent_walls,
)
from coverengine.flatten.pattern import _panel_mesh, compensation
from coverengine.flatten.solve import flatten
from coverengine.params import EffectiveParams

Array = NDArray[np.float64]
VENTS_JSON = "vents.json"
VENTS_FORMAT = 3  # 2: the measurements (ADR-111); 3: the logo (ADR-146); an older one is made again
CORNER_DEG = 45.0  # param-ok: measurement definition, the bottom edge turns this much at a corner
CORNER_SPAN_MM = 100.0  # param-ok: measurement definition, over this length either side
CORNER_STEP = 10  # param-ok: stations per CORNER_SPAN_MM where the turn is measured
SAME_OUTLINE_MM = 1.0  # param-ok: the re-flattened panel must match the stored outline


PROBE_MM = 50.0  # param-ok: a point this far beside the wall tells out from in
UPRIGHT = 0.05  # param-ok: a face whose normal rises more than this is sloping, not upright


def _barycentric(uv: Array, faces: NDArray[np.int64], p: Array) -> tuple[int, Array]:
    """The flat triangle `p` lies in (or the nearest one) and its barycentric weights."""
    a, b, c = uv[faces[:, 0]], uv[faces[:, 1]], uv[faces[:, 2]]
    v0, v1, v2 = b - a, c - a, p - a
    den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    den = np.where(np.abs(den) < 1e-12, 1e-12, den)  # param-ok: no division by zero
    w1 = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
    w2 = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
    w0 = 1 - w1 - w2
    worst = np.minimum(np.minimum(w0, w1), w2)  # >= 0 inside
    i = int(np.argmax(worst))
    w = np.clip(np.array([w0[i], w1[i], w2[i]]), 0.0, None)
    return i, w / w.sum()


def _to_3d(v: Array, f: NDArray[np.int64], uv: Array, p: Array) -> tuple[Array, Array]:
    i, w = _barycentric(uv, f, p)
    tri = v[f[i]]
    n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
    return w @ tri, n / (np.linalg.norm(n) or 1.0)


def vents_3d(model_dir: Path, doc: dict[str, Any], params: EffectiveParams) -> dict[str, Any]:
    """Every vent of the cover in 3D (see the module's docstring)."""
    walls = vent_walls(model_dir, params)
    vents, _ = place_vents(doc["panels"], params, walls)
    out: list[dict[str, Any]] = []
    warnings: list[str] = []
    data = np.load(model_dir / "panels.npz")
    lower = float(np.asarray(data["vertices"])[:, 2].min()) if len(data["vertices"]) else 0.0
    head: dict[str, Any] = {"format": VENTS_FORMAT, "lower_edge_z_mm": round(lower, 1)}
    if not vents:
        return {**head, "logo": "none", "vents": out, "warnings": warnings}
    logos, logo_size = _finished_logos(model_dir, doc, params)
    frame = logo_frame(params)
    a = float(params["stitching.allowance_mm"])  # type: ignore[arg-type]
    hood_w, _ = hood_size(params)
    skip = frozenset() if params["features.vent_inner_walls"] else walls.inner
    bases, _ = vent_bases(doc["panels"], params, skip)
    panel_of = {p["name"]: p for p in doc["panels"]}
    names = [p["name"] for p in json.loads((model_dir / "panels.json").read_text())["panels"]]
    vertices, faces, labels = data["vertices"], data["faces"], data["labels"]
    # out of the cover is where no cover lies overhead (an L or U shape's inner walls face the
    # open corner: "away from the middle" pointed them into the cover, C23, 7 Oct 2026)
    import shapely

    tri = vertices[faces][:, :, :2]
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    big = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) > 1.0  # param-ok: mm², not edge-on
    footprint = shapely.union_all([shapely.Polygon(t) for t in tri[big]]).buffer(
        1.0
    )  # param-ok: mm

    def covered(q: np.ndarray) -> bool:
        return bool(footprint.contains(shapely.Point(float(q[0]), float(q[1]))))

    outline_of = {p["name"]: np.asarray(p["outline_mm"], dtype=np.float64) for p in doc["panels"]}
    scale = compensation(params)
    for name, rects in vents.items():
        if name not in names:
            warnings.append(f"{name}: not in panels.json")
            continue
        mesh, _ = _panel_mesh(vertices, faces[labels == names.index(name)])
        flat = flatten(
            mesh,
            str(params["flatten.solver"]),
            int(params["flatten.iterations"]),
            float(params["flatten.slim_tolerance"]),  # type: ignore[arg-type]
            int(params["flatten.max_triangles"]),
        )
        uv = flat.uv * scale
        gap, _ = cKDTree(uv).query(outline_of[name])
        if float(gap.max()) > SAME_OUTLINE_MM:
            warnings.append(f"{name}: the flat panel differs from pattern.json (run cover flatten)")
            continue
        v, f = np.asarray(flat.vertices), np.asarray(flat.faces, dtype=np.int64)
        for rect in rects:
            rect = np.asarray(rect, dtype=np.float64)
            corners = [_to_3d(v, f, uv, q)[0] for q in rect]
            centre, normal = _to_3d(v, f, uv, np.asarray(rect, dtype=np.float64).mean(axis=0))
            flat_n = np.array([normal[0], normal[1], 0.0])
            if abs(float(normal[2])) > UPRIGHT:
                # a sloping face (a box cover's side over a low band, ADR-099): the cover never
                # overhangs, so out is up; the probe beside it would land under its own slope
                if normal[2] < 0:
                    normal = -normal
            elif np.linalg.norm(flat_n) > 0:  # an upright wall: step out sideways and look up
                probe = centre + flat_n / np.linalg.norm(flat_n) * PROBE_MM
                if covered(probe):  # cover overhead: that was the inside
                    normal = -normal
            elif normal[2] < 0:  # a level face (rare): out is up
                normal = -normal
            # seen from outside the corners run bottom left to top left
            swapped = float(np.cross(corners[1] - corners[0], corners[3] - corners[0]) @ normal) < 0
            if swapped:
                corners = [corners[1], corners[0], corners[3], corners[2]]
            w = float(np.linalg.norm(np.asarray(rect[1]) - np.asarray(rect[0])))
            h = float(np.linalg.norm(np.asarray(rect[3]) - np.asarray(rect[0])))
            vent: dict[str, Any] = {
                "number": len(out) + 1,
                "piece": name,
                "centre_mm": [round(float(x), 1) for x in centre],
                "corners_mm": [[round(float(x), 1) for x in c] for c in corners],
                "normal": [round(float(x), 4) for x in normal],
                "size_mm": [round(w, 1), round(h, 1)],
                "bottom_z_mm": round(float(min(corners[0][2], corners[1][2])), 1),
            }
            runs = bases.get(name, [])
            if runs:

                def to3d(q: Array, v: Array = v, f: NDArray[np.int64] = f, uv: Array = uv) -> Array:
                    return _to_3d(v, f, uv, np.asarray(q, dtype=np.float64))[0]

                vent |= vent_sizes(rect, runs, panel_of[name], to3d, lower, swapped)
            vent |= _hood_and_logo(rect, logos.get(name, []), v, f, uv, normal, swapped,
                                   frame, a, hood_w, logo_size)  # fmt: skip
            out.append(vent)
    if frame is None:
        state = "none"
    elif out and all(x.get("logo") for x in out):
        state = "placed"
    else:
        state = "missing"
    return {**head, "logo": state, "vents": out, "warnings": warnings}


def _finished_logos(
    model_dir: Path, doc: dict[str, Any], params: EffectiveParams
) -> tuple[dict[str, list[tuple[Array, Array]]], list[float]]:
    """Per piece in finished.json: each opening with its logo frame on the cover (format 2 on;
    an older export has none); and the frame's size on the hood (`logo_mm`), [] without. Only
    when finished.json is the export of this pattern.json with these parameters (both hashes):
    else the cutting file may say something else, and the logo is "missing" (export again)."""
    try:
        fin = json.loads((model_dir / FINISHED_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, []
    if (fin.get("pattern_parameter_hash") != doc.get("parameter_hash")
            or fin.get("parameter_hash") != params.hash()):  # fmt: skip
        return {}, []
    out: dict[str, list[tuple[Array, Array]]] = {}
    size: list[float] = []
    for pc in fin.get("pieces", []):
        if pc.get("name") == "vent-hood" and pc.get("logo_mm"):
            frame = np.asarray(pc["logo_mm"], dtype=np.float64)
            size = [round(float(x), 1) for x in np.ptp(frame, axis=0)]
        openings, logos = pc.get("openings_mm") or [], pc.get("logos_mm") or []
        if len(openings) == len(logos):
            out[pc["name"]] = [(np.asarray(o, dtype=np.float64), np.asarray(lg, dtype=np.float64))
                               for o, lg in zip(openings, logos, strict=True)]  # fmt: skip
    return out, size


def _hood_and_logo(
    rect: Array,
    logos: list[tuple[Array, Array]],
    v: Array,
    f: NDArray[np.int64],
    uv: Array,
    normal: Array,
    swapped: bool,
    frame: Array | None,
    allowance: float,
    hood_w: float,
    logo_size: list[float],
) -> dict[str, Any]:
    """The hood's top stitch line and the logo of one vent in 3D (see the module's docstring).
    The logo is the one finished.json gives for this opening (the same corners within
    `SAME_OUTLINE_MM`), or None."""
    along = rect[1] - rect[0]
    along = along / (np.linalg.norm(along) or 1.0)
    up = rect[3] - rect[0]
    up = up / (np.linalg.norm(up) or 1.0)
    seam_mid = (rect[2] + rect[3]) / 2 + up * allowance
    ends = [seam_mid - along * hood_w / 2, seam_mid + along * hood_w / 2]
    if swapped:
        ends = ends[::-1]
    seam3 = [_to_3d(v, f, uv, q)[0] for q in ends]
    mid3 = _to_3d(v, f, uv, seam_mid)[0]
    ring_low3 = _to_3d(v, f, uv, (rect[0] + rect[1]) / 2 - up * allowance)[0]
    down = ring_low3 - mid3
    down = down - normal * float(down @ normal)  # along the cover
    down = down / (np.linalg.norm(down) or 1.0)
    # on the 3D surface, as the logo's corners (the flat pattern may be compensated)
    reach = float((ring_low3 - mid3) @ down)
    out: dict[str, Any] = {
        "hood": {
            "seam_mm": [_r(p) for p in seam3],
            "down": [round(float(x), 4) for x in down],
            "length_mm": round(reach, 1),
        },
        "logo": None,
    }
    if frame is None:
        return out
    match = next((lg for o, lg in logos
                  if o.shape == rect.shape and float(np.abs(o - rect).max()) <= SAME_OUTLINE_MM),
                 None)  # fmt: skip
    if match is None or not logo_size:
        return out
    pts = [_to_3d(v, f, uv, q)[0] for q in match[:4]]
    if swapped:
        pts = [pts[1], pts[0], pts[3], pts[2]]
    # the exported frame's own corners, measured on the 3D surface like the hood's reach
    below = np.array([float((p - mid3) @ down) for p in pts])
    out["logo"] = {
        "corners_mm": [_r(p) for p in pts],
        "centre_mm": _r(np.mean(pts, axis=0)),
        "below_seam_mm": [round(float(below.min()), 1), round(float(below.max()), 1)],
        "size_mm": logo_size,  # on the hood (on the cover it hangs foreshortened)
    }
    return out


def seam_under(vent: dict[str, Any]) -> float:
    """How high above the cover's lower edge a vent's own bottom edge lies (mm): 0 for a vent on
    the hem; for one over a seam (a low skirt's top, or one panel up by hand) that seam's
    height. "High up a wall" is measured from there (ADR-142)."""
    if vent.get("bottom_edge") != "above":
        return 0.0
    lift = float(vent.get("above_hem_mm", 0.0)) - float(vent.get("above_piece_edge_mm", 0.0))
    return max(lift, 0.0)


def _r(p: Array) -> list[float]:
    return [round(float(x), 1) for x in p]


def corners_along(pts3: Array) -> list[float]:
    """Where along a line on the cover (mm from its start, in plan) it turns a corner: the
    direction over `CORNER_SPAN_MM` before and after a point differs by `CORNER_DEG` or more."""
    seg = np.linalg.norm(np.diff(pts3[:, :2], axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    if s[-1] <= 2 * CORNER_SPAN_MM:
        return []
    stations = np.arange(CORNER_SPAN_MM, s[-1] - CORNER_SPAN_MM, CORNER_SPAN_MM / CORNER_STEP)
    xy = [np.column_stack([np.interp(stations + d, s, pts3[:, 0]),
                           np.interp(stations + d, s, pts3[:, 1])])
          for d in (-CORNER_SPAN_MM, 0.0, CORNER_SPAN_MM)]  # fmt: skip
    d1, d2 = xy[1] - xy[0], xy[2] - xy[1]
    den = np.maximum(np.linalg.norm(d1, axis=1) * np.linalg.norm(d2, axis=1), 1e-9)  # param-ok
    turn = np.degrees(np.arccos(np.clip((d1 * d2).sum(axis=1) / den, -1.0, 1.0)))
    out: list[float] = []
    k = 0
    while k < len(stations):
        if turn[k] < CORNER_DEG:
            k += 1
            continue
        j = k
        while j + 1 < len(stations) and turn[j + 1] >= CORNER_DEG:
            j += 1
        out.append(float(stations[k + int(np.argmax(turn[k : j + 1]))]))
        k = j + 1
    return out


def vent_sizes(
    rect: Array,
    runs: list[HemRun],
    panel: dict[str, Any],
    to3d: Any,
    lower: float,
    swapped: bool,
) -> dict[str, Any]:
    """A vent's measurements on its flat piece (see the module's docstring). `rect`: the
    opening in the piece's coordinates (bottom start, bottom end, top end, top start)."""
    import shapely

    bottom_mid = (rect[0] + rect[1]) / 2
    at = shapely.Point(*bottom_mid)
    run = min(runs, key=lambda r: shapely.LineString(r.points).distance(at))
    line = shapely.LineString(run.points)
    lift = float(line.distance(at))
    s0, s1 = sorted(float(line.project(shapely.Point(*q))) for q in rect[:2])
    up = rect[3] - rect[0]
    up = up / (np.linalg.norm(up) or 1.0)

    def flat_at(s: float) -> Array:
        p = line.interpolate(s)
        return np.array([p.x, p.y]) + up * lift  # at the height of the opening's bottom

    turns = corners_along(np.array([to3d(q) for q in run.points]))
    start_name, end_name = _ends(run, panel)
    before = [c for c in turns if c < s0]
    after = [c for c in turns if c > s1]
    a = before[-1] if before else 0.0
    b = after[0] if after else float(line.length)
    first = {
        "to": "corner" if before else ("seam" if start_name else "edge"),
        "name": "" if before else start_name,
        "mm": round(s0 - a, 1),
        "line_mm": [_r(to3d(flat_at(a))), _r(to3d(flat_at(s0)))],
    }
    last = {
        "to": "corner" if after else ("seam" if end_name else "edge"),
        "name": "" if after else end_name,
        "mm": round(b - s1, 1),
        "line_mm": [_r(to3d(flat_at(s1))), _r(to3d(flat_at(b)))],
    }
    # over a skirt too low for a vent the piece's bottom edge is that skirt's top seam: the
    # skirt's height (in 3D, upright) comes on top (ADR-101)
    base = line.interpolate((s0 + s1) / 2)
    extra = float(to3d(np.array([base.x, base.y]))[2] - lower) if run.kind == "above" else 0.0
    left, right = (last, first) if swapped else (first, last)
    bottom3 = to3d(bottom_mid)
    return {
        "above_hem_mm": round(lift + extra, 1),
        "above_piece_edge_mm": round(lift, 1),
        "bottom_edge": run.kind,
        "run_mm": round(float(line.length), 1),
        "height_line_mm": [_r(np.array([bottom3[0], bottom3[1], lower])), _r(bottom3)],
        "sides": {"left": left, "right": right},
    }


def ensure_vents(model_dir: Path) -> Path | None:
    """vents.json, made when the viewer asks for it (ADR-080): export no longer flattens every
    skirt piece a second time. Made again when it is older than finished.json. None when the
    cover is not exported yet."""
    import json

    finished = model_dir / "finished.json"
    pattern = model_dir / "pattern.json"
    out = model_dir / VENTS_JSON
    if not (finished.is_file() and pattern.is_file()):
        return None
    inputs = [finished, pattern] + [model_dir / n for n in ("panels.npz", "panels.json",
                                                             "cover.json")]  # fmt: skip
    newest = max(p.stat().st_mtime for p in inputs if p.is_file())
    if out.is_file() and out.stat().st_mtime >= newest:
        try:
            current = json.loads(out.read_text(encoding="utf-8")).get("format") == VENTS_FORMAT
        except (OSError, ValueError):
            current = False
        if current:
            return out
    from coverengine.params.registry import Registry, resolve_model

    params = resolve_model(model_dir, {}, Registry.load(None), None)
    doc = json.loads(pattern.read_text(encoding="utf-8"))
    try:
        vents = vents_3d(model_dir, doc, params)
    except (OSError, KeyError, ValueError) as exc:
        vents = {
            "format": VENTS_FORMAT,
            "vents": [],
            "warnings": [f"vents not placed in 3D: {exc}"],
        }
    out.write_text(json.dumps(vents, indent=1) + "\n", encoding="utf-8")
    return out
