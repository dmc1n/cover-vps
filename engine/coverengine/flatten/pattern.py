"""`cover flatten`: flat patterns for every panel of a cut cover (PatternSet, FORMATS.md).

Reads `panels.npz` and `panels.json` from `cover cut`. For each panel: the flat map
(`solve.py`), stretch, the outline split into seam and hem edges, the 2D length of both sides
of every seam (ease when they differ), matching marks every `pen.tick_spacing_mm` paired by
id, a label and an UP arrow.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import igl
import numpy as np
import shapely
import trimesh
from numpy.typing import NDArray
from scipy.spatial import ConvexHull, cKDTree

from coverengine import __version__
from coverengine.errors import CoverError
from coverengine.flatten.solve import Flat, flatten, singular_values
from coverengine.params import EffectiveParams

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]

FORMAT_VERSION = 1
PATTERN_JSON = "pattern.json"
HEM = -1  # seam index of hem edges
# Faces below this area (mm2) are dropped before flattening (they cannot be mapped).
MIN_FACE_MM2 = 1e-6  # param-ok: geometric tolerance
PERCENT = 100  # param-ok: ratio to percent
# Wiggle: an edge is compared with itself smoothed over this length (mm), sampled this often.
WIGGLE_WINDOW_MM = 30.0  # param-ok: measurement definition
WIGGLE_STEP_MM = 1.0  # param-ok: measurement definition
# A sharp turn: the direction changes more than WIGGLE_SHARP_DEG over +-WIGGLE_TURN_SPAN_MM.
WIGGLE_SHARP_DEG = 30.0  # param-ok: measurement definition
WIGGLE_TURN_SPAN_MM = 5.0  # param-ok: measurement definition
WIGGLE_CORNER_GAP_MM = 100.0  # param-ok: measurement definition
WIGGLE_MIN_TURNS = 4  # param-ok: measurement definition
# The UP arrow sits this many label heights above the label.
ARROW_ABOVE_LABEL = 2.5  # param-ok: layout


@dataclass
class PanelPattern:
    index: int
    name: str
    outline: Array  # closed polyline, mm, no repeated end point
    flat: Flat
    edges: list[dict[str, Any]]
    pen: list[dict[str, Any]]
    stretch: dict[str, float]
    width_mm: float
    length_mm: float
    warnings: list[str] = field(default_factory=list)


def _p(params: EffectiveParams, key: str) -> float:
    return float(params[key])  # type: ignore[arg-type]


def narrow_width(points: Array) -> tuple[float, float]:
    """Width in the narrowest orientation and the length across it (rotating calipers)."""
    hull = points[ConvexHull(points).vertices]
    best = (math.inf, 0.0)
    for a, b in zip(hull, np.roll(hull, -1, axis=0), strict=True):
        d = b - a
        n = float(np.linalg.norm(d))
        if n == 0:
            continue
        d = d / n
        across = float(np.ptp((hull - a) @ np.array([-d[1], d[0]])))
        if across < best[0]:
            best = (across, float(np.ptp((hull - a) @ d)))
    return best


def _panel_mesh(vertices: Array, faces: IntArray) -> tuple[trimesh.Trimesh, IntArray]:
    """The panel's own mesh (degenerate faces dropped) and its vertices' indices in the input."""
    tri = vertices[faces]
    area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1) / 2
    faces = faces[area > MIN_FACE_MM2]
    used, local = np.unique(faces, return_inverse=True)
    return trimesh.Trimesh(vertices[used], local.reshape(faces.shape), process=False), used


def _runs(labels: list[int]) -> list[tuple[int, int, int]]:
    """(start, end, label) runs around a closed loop of edge labels (end inclusive), rotated so
    no run wraps past the end."""
    n = len(labels)
    start = next((i for i in range(n) if labels[i] != labels[i - 1]), 0)
    order = [(start + i) % n for i in range(n)]
    runs: list[tuple[int, int, int]] = []
    for i in order:
        if runs and runs[-1][2] == labels[i] and (runs[-1][1] + 1) % n == i:
            runs[-1] = (runs[-1][0], i, labels[i])
        else:
            runs.append((i, i, labels[i]))
    return runs


def build_patterns(
    model_dir: Path, params: EffectiveParams
) -> tuple[list[PanelPattern], dict[str, Any]]:
    npz_path, json_path = model_dir / "panels.npz", model_dir / "panels.json"
    if not npz_path.is_file() or not json_path.is_file():
        raise CoverError(f"no panels in {model_dir} (run cover cut first)")
    data = np.load(npz_path)
    cut_report = json.loads(json_path.read_text(encoding="utf-8"))
    vertices, faces, labels = data["vertices"], data["faces"], data["labels"]
    original = data["original_vertex"]
    seam_of = {
        (int(a), int(b)): int(i)
        for (a, b), i in zip(data["seam_edges"], data["seam_index"], strict=True)
    }
    seams = cut_report["seams"]
    names = [p["name"] for p in cut_report["panels"]]
    solver = str(params["flatten.solver"])
    iterations = int(params["flatten.iterations"])
    tolerance = _p(params, "flatten.slim_tolerance")
    tick_spacing = _p(params, "pen.tick_spacing_mm")
    tick_length = _p(params, "pen.tick_length_mm")
    label_h = _p(params, "pen.label_height_mm")
    q_limit = _p(params, "flatten.stretch_quantile")
    max_triangles = int(params["flatten.max_triangles"])

    patterns: list[PanelPattern] = []
    for k, name in enumerate(names):
        mesh, used = _panel_mesh(vertices, faces[labels == k])
        flat = flatten(mesh, solver, iterations, tolerance, max_triangles)
        loop = igl.boundary_loop(flat.faces.astype(np.int32))
        # orient the loop counter-clockwise in the pattern
        ring = flat.uv[loop]
        if shapely.Polygon(ring).exterior.is_ccw is False:
            loop = loop[::-1]
        # outline points are the panel's own boundary points (simplifying keeps them exactly)
        _, local = cKDTree(np.asarray(mesh.vertices)).query(flat.vertices[loop])
        orig = original[used[local]]
        edge_labels = []
        for i in range(len(loop)):
            a, b = int(orig[i]), int(orig[(i + 1) % len(loop)])
            edge_labels.append(seam_of.get((min(a, b), max(a, b)), HEM))
        outline = flat.uv[loop]
        v3 = flat.vertices[loop]
        edges = []
        for start, end, seam_index in _runs(edge_labels):
            idx = [(start + j) % len(loop) for j in range((end - start) % len(loop) + 2)]
            l2 = float(np.linalg.norm(np.diff(outline[idx], axis=0), axis=1).sum())
            l3 = float(np.linalg.norm(np.diff(v3[idx], axis=0), axis=1).sum())
            entry: dict[str, Any] = {
                "range": [idx[0], idx[-1]],
                "kind": "hem" if seam_index == HEM else "seam",
                "length_3d_mm": round(l3, 2),
                "length_2d_mm": round(l2, 2),
                "wiggle_mm": round(wiggle(outline[idx]), 2),
            }
            if seam_index != HEM:
                s = seams[seam_index]
                mate = s["panels"][1] if s["panels"][0] == name else s["panels"][0]
                entry.update({"seam": s["id"], "mate": mate, "lap_side": s["lap_side"]})
            entry["_points"] = idx
            edges.append(entry)
        s1, s2, area = singular_values(flat.vertices, flat.faces, flat.uv)
        worst = np.maximum(s1 - 1, 1 - s2)
        order = np.argsort(worst)
        share = np.cumsum(area[order]) / area.sum()
        at = min(int(np.searchsorted(share, q_limit)), len(order) - 1)
        quantile = float(worst[order][at])
        stretch = {
            "max_pct": round(float(worst.max()) * PERCENT, 3),
            "quantile_pct": round(quantile * PERCENT, 3),
            "max_stretch_pct": round(float(s1.max() - 1) * PERCENT, 3),
            "max_compression_pct": round(float(1 - s2.min()) * PERCENT, 3),
            "mean_pct": round(float((worst * area).sum() / area.sum()) * PERCENT, 3),
            "area_pct": round(
                (float(np.abs(_areas(flat.uv, flat.faces)).sum() / area.sum()) - 1) * PERCENT, 4
            ),
        }
        width, length = narrow_width(outline)
        pen = _pen_marks(name, outline, edges, v3, tick_spacing, tick_length, label_h)
        patterns.append(PanelPattern(k, name, outline, flat, edges, pen, stretch, width, length))
    return patterns, cut_report


def wiggle(points: Array) -> float:
    """How far an edge zig-zags: the largest distance between the edge and itself smoothed
    over WIGGLE_WINDOW_MM (a smooth curve stays within a fraction of a mm). A corner or a step
    (up to three sharp turns close together, where a wall ends, say) is not a zig-zag and is
    left out; WIGGLE_MIN_TURNS or more sharp turns, each within WIGGLE_CORNER_GAP_MM of the
    next, are."""
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    if s[-1] <= WIGGLE_WINDOW_MM:
        return 0.0
    at = np.arange(0.0, s[-1], WIGGLE_STEP_MM)
    p = np.column_stack([np.interp(at, s, points[:, k]) for k in range(points.shape[1])])
    w = int(WIGGLE_WINDOW_MM / WIGGLE_STEP_MM)
    kernel = np.ones(w + 1) / (w + 1)
    smooth = np.column_stack(
        [np.convolve(p[:, k], kernel, mode="valid") for k in range(p.shape[1])]
    )
    inner = p[w // 2 : w // 2 + len(smooth)]
    dev = np.linalg.norm(inner - smooth, axis=1)
    # sharp turns: direction change over a few mm
    k = max(int(WIGGLE_TURN_SPAN_MM / WIGGLE_STEP_MM), 1)
    if len(p) > 2 * k + 1:
        d1, d2 = p[k:-k] - p[: -2 * k], p[2 * k :] - p[k:-k]
        cos = (d1 * d2).sum(1) / np.maximum(
            np.linalg.norm(d1, axis=1) * np.linalg.norm(d2, axis=1), 1e-12
        )
        sharp = np.flatnonzero(cos < math.cos(math.radians(WIGGLE_SHARP_DEG))) + k
        if len(sharp):
            groups = np.split(sharp, np.flatnonzero(np.diff(sharp) > k) + 1)
            corners = np.array([g.mean() for g in groups]) * WIGGLE_STEP_MM
            # corners closer together than the gap form a cluster; a cluster of fewer than
            # WIGGLE_MIN_TURNS turns is a corner or a step, not a zig-zag
            clusters = np.split(
                corners, np.flatnonzero(np.diff(corners) > WIGGLE_CORNER_GAP_MM) + 1
            )
            pos = at[w // 2 : w // 2 + len(smooth)]
            for cl in clusters:
                if len(cl) < WIGGLE_MIN_TURNS:
                    for c in cl:
                        dev[np.abs(pos - c) <= WIGGLE_WINDOW_MM] = 0.0
    return float(dev.max()) if len(dev) else 0.0


def _areas(uv: Array, f: IntArray) -> Array:
    e1, e2 = uv[f[:, 1]] - uv[f[:, 0]], uv[f[:, 2]] - uv[f[:, 0]]
    return (e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2


def _pen_marks(
    name: str,
    outline: Array,
    edges: list[dict[str, Any]],
    v3: Array,
    spacing: float,
    tick: float,
    height: float,
) -> list[dict[str, Any]]:
    poly = shapely.Polygon(outline)
    marks: list[dict[str, Any]] = []
    centre = shapely.ops.polylabel(poly, tolerance=height / 2) if poly.is_valid else poly.centroid
    marks.append(
        {"type": "label", "at": [round(centre.x, 1), round(centre.y, 1)], "text": name.upper()}
    )
    marks.append(
        {
            "type": "arrow_up",
            "at": [round(centre.x, 1), round(centre.y + ARROW_ABOVE_LABEL * height, 1)],
            "length": 4 * height,
        }
    )
    for e in edges:
        if e["kind"] != "seam":
            continue
        idx = e["_points"]
        p2, p3 = outline[idx], v3[idx]
        # positions along the seam measured in 3D, from the end with the smaller 3D coordinates,
        # so both sides of the seam put their marks at the same places
        s3 = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p3, axis=0), axis=1))])
        flip = tuple(p3[-1].round(3)) < tuple(p3[0].round(3))
        if flip:
            s3 = s3[-1] - s3
        total = float(s3.max())
        order = np.argsort(s3)
        for j, at in enumerate(np.arange(spacing, total - spacing / 2, spacing)):
            x = np.interp(at, s3[order], p2[order, 0])
            y = np.interp(at, s3[order], p2[order, 1])
            i = int(np.clip(np.searchsorted(s3[order], at), 1, len(order) - 1))
            a, b = p2[order[i - 1]], p2[order[i]]
            t = (b - a) / (np.linalg.norm(b - a) or 1.0)
            inward = np.array([-t[1], t[0]])  # the outline runs counter-clockwise
            if not poly.contains(shapely.Point(x + inward[0], y + inward[1])):
                inward = -inward
            marks.append(
                {
                    "type": "tick",
                    "at": [round(float(x), 2), round(float(y), 2)],
                    "dir": [round(float(inward[0]), 4), round(float(inward[1]), 4)],
                    "length": tick,
                    "pair": f"{e['seam']}:t{j + 1}",
                }
            )
        mid = len(idx) // 2
        a, b = p2[max(mid - 1, 0)], p2[min(mid + 1, len(idx) - 1)]
        t = (b - a) / (np.linalg.norm(b - a) or 1.0)
        inward = np.array([-t[1], t[0]])
        at = p2[mid] + inward * (tick + height)
        if not poly.contains(shapely.Point(*at)):
            at = p2[mid] - inward * (tick + height)
        marks.append(
            {
                "type": "seam_label",
                "at": [round(float(at[0]), 1), round(float(at[1]), 1)],
                "text": f"TO {e['mate'].upper()}",
            }
        )
    return marks


def pattern_set(
    model_dir: Path,
    params: EffectiveParams,
    patterns: list[PanelPattern],
    cut_report: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    tolerance = _p(params, "seams.seam_tolerance_mm")
    limit = _p(params, "fabric.max_allowed_stretch_pct")
    q_limit = _p(params, "flatten.stretch_quantile")
    usable = _p(params, "roll.usable_width_mm")
    # ease: the two sides of every seam compared
    # a seam may reach a panel in more than one part (either side of a wall); each panel's
    # parts are added up before the two panels are compared
    per_panel: dict[str, dict[str, float]] = {}
    for p in patterns:
        for e in p.edges:
            if e["kind"] == "seam":
                side = per_panel.setdefault(e["seam"], {})
                side[p.name] = side.get(p.name, 0.0) + e["length_2d_mm"]
    sides = {seam: list(by_panel.values()) for seam, by_panel in per_panel.items()}
    for p in patterns:
        for e in p.edges:
            if e["kind"] == "seam":
                lengths = sides[e["seam"]]
                ease = max(lengths) - min(lengths) if len(lengths) > 1 else 0.0
                e["ease_mm"] = round(ease, 2)
        if p.stretch["quantile_pct"] > limit:
            warnings.append(
                f"panel {p.name} stretches {p.stretch['quantile_pct']:.1f} % over more than "
                f"{(1 - q_limit) * PERCENT:.1f} % of its area (limit {limit:g} %); "
                "an extra seam would help"
            )
        if p.width_mm > usable:
            warnings.append(
                f"panel {p.name} is {p.width_mm:.0f} mm wide flat, "
                f"more than the roll ({usable:g} mm)"
            )
    max_wiggle = _p(params, "seams.max_wiggle_mm")
    for p in patterns:
        for e in p.edges:
            if e["wiggle_mm"] > max_wiggle:
                what = f"seam to {e['mate']}" if e["kind"] == "seam" else "hem"
                warnings.append(
                    f"panel {p.name}: the {what} is not a smooth line (zig-zags "
                    f"{e['wiggle_mm']:.1f} mm, limit {max_wiggle:g} mm)"
                )
    for seam, lengths in sorted(sides.items()):
        if len(lengths) > 1 and max(lengths) - min(lengths) > tolerance:
            diff = max(lengths) - min(lengths)
            warnings.append(
                f"seam {seam}: the two sides differ by {diff:.1f} mm (recorded as ease)"
            )
    model = json.loads((model_dir / "model.json").read_text(encoding="utf-8"))
    fabric = str(params["fabric.profile"])
    doc: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "engine_version": __version__,
        "model_id": model["id"],
        "model_sha256": model["source"]["sha256"],
        "parameter_hash": params.hash(),
        "parameters": params.tree(),
        "parameter_sources": params.sources(),
        "fabric_profile": fabric,
        "fabric_compensation": bool(params["flatten.fabric_compensation"]),
        "summary": {
            "panels": len(patterns),
            "max_stretch_pct": max(p.stretch["quantile_pct"] for p in patterns),
            "fabric_area_m2": round(
                sum(float(np.abs(_areas(p.flat.uv, p.flat.faces)).sum()) for p in patterns) / 1e6, 4
            ),
            "hem_length_mm": cut_report["hem_length_mm"],
        },
        "panels": [
            {
                "id": f"P{p.index + 1}",
                "name": p.name,
                "quantity": 1,
                "mirror": False,
                "outline_mm": [[round(float(x), 2), round(float(y), 2)] for x, y in p.outline],
                "edges": [{k: v for k, v in e.items() if not k.startswith("_")} for e in p.edges],
                "pen": p.pen,
                "stretch": p.stretch,
                "flat_width_mm": round(p.width_mm, 1),
                "flat_length_mm": round(p.length_mm, 1),
                "fits_roll": bool(p.width_mm <= usable),
                "solver_iterations": p.flat.iterations,
            }
            for p in patterns
        ],
        "warnings": warnings,
    }
    return doc, warnings
