"""Size drawing (`sizes.pdf`): the calculated cover drawn and dimensioned like a workshop
drawing, so the sizes can be checked by hand against a cover that fits.

Page 1: top view, front and side view and a 3D view of the finished cover, with the main sizes
and a title block. Page 2 (and on): every size as a table: the key sizes, next to the reference
cover's where one exists (`<model dir>/reference.json` or `testdata/reference/<id>.json`, with a
`compare` map, FORMATS.md), then every seam (length on the cover and on both flat panels) and
every panel. Then one page per flat panel with the length of each edge.

All sizes are seam to seam on the finished cover, in cm, without seam allowances or hem. The
PDF is built from the files `cover cut` and `cover flatten` write, so it can be redrawn any time
(`cover drawing`), and the same input gives the same file.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import igl
import numpy as np
import shapely
from matplotlib.axes import Axes
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.figure import Figure
from numpy.typing import NDArray

from coverengine import __version__
from coverengine.params import EffectiveParams
from coverengine.params.registry import repo_root

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]

SIZES_PDF = "sizes.pdf"
MM_PER_CM = 10.0  # param-ok: unit conversion
MM_PER_INCH = 25.4  # param-ok: unit conversion
A4_MM = (210.0, 297.0)  # param-ok: paper size
DPI = 200  # param-ok: resolution of the shaded surfaces in the PDF
# Colours, like the reference drawing: blue-grey cover, black seams, magenta hem.
TOP_RGB = np.array([0.66, 0.68, 0.78])  # param-ok: display colour
SKIRT_RGB = np.array([0.52, 0.54, 0.64])  # param-ok: display colour
HEM_COLOUR, SEAM_COLOUR, DIM_COLOUR = "#e0147a", "black", "#222"
OK_COLOUR, OFF_COLOUR = "#1a7f37", "#c62828"
SHADE_MIN = 0.55  # param-ok: display, darkest shading of a surface facing away from the light
# A skirt point's height is taken from the skirt within this plan distance (mm).
COLUMN_MM = 20.0  # param-ok: geometric search radius
# The hem is simplified with this tolerance (mm) to find its longest straight run.
STRAIGHT_MM = 3.0  # param-ok: geometric tolerance
# A panel's typical width is the median across its length between these fractions.
WIDTH_SPAN = (0.2, 0.8)  # param-ok: measurement definition
# Paper scales tried for a panel page, largest drawing first.
SCALES = (1, 2, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100)  # param-ok: drawing scales
# A panel label is drawn in a view when this share of the panel faces the viewer.
VISIBLE_SHARE = 0.3  # param-ok: display
ISO_EYE = (0.55, -1.0, 0.75)  # param-ok: 3D view direction, from front right, above
FONT = 7.0  # param-ok: base font size (pt)
ROW_MM = 5.2  # param-ok: table row height on paper
CELL_MID = 0.5  # param-ok: layout, middle of a title block cell (and a smaller font step)
HASH_CHARS = 8  # param-ok: layout, characters of the parameter hash shown


@dataclass
class View:
    name: str
    eye: Array  # towards the viewer
    right: Array
    up: Array


def _views() -> dict[str, View]:
    x, y, z = np.eye(3)
    eye = np.array(ISO_EYE) / np.linalg.norm(ISO_EYE)
    right = np.cross(-eye, z)
    right /= np.linalg.norm(right)
    return {
        "top": View("top", z, x, y),
        "front": View("front", -y, x, z),
        "side": View("side", x, y, z),
        "iso": View("iso", eye, right, np.cross(right, -eye)),
    }


@dataclass
class Cover:
    """The cut cover in drawing coordinates (the plan turned by `drawing.plan_rotation_deg`)."""

    model_id: str
    vertices: Array  # unzipped mesh
    faces: IntArray
    labels: IntArray  # panel index per face
    points: Array  # position of every original (welded) vertex
    welded: IntArray  # faces in original vertex ids
    names: list[str]
    regions: list[str]
    seams: list[dict[str, Any]]
    seam_edges: IntArray  # original vertex ids
    seam_index: IntArray
    hem: IntArray  # original vertex ids around the hem, in order
    hem_z: float
    hem_length: float
    area_m2: float
    doc: dict[str, Any]  # the PatternSet
    rotation_deg: float

    @property
    def normals(self) -> Array:
        tri = self.points[self.welded]
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        out: Array = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        return out


def load_cover(model_dir: Path, doc: dict[str, Any], params: EffectiveParams) -> Cover:
    data = np.load(model_dir / "panels.npz")
    cut = json.loads((model_dir / "panels.json").read_text(encoding="utf-8"))
    hull = json.loads((model_dir / "hull.json").read_text(encoding="utf-8"))
    angle = float(params["drawing.plan_rotation_deg"])  # type: ignore[arg-type]
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    turn = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    vertices = np.asarray(data["vertices"], dtype=np.float64) @ turn.T
    original = np.asarray(data["original_vertex"], dtype=np.int64)
    points = np.zeros((int(original.max()) + 1, 3))
    points[original] = vertices
    faces = np.asarray(data["faces"], dtype=np.int64)
    welded = original[faces]
    hem = np.asarray(igl.boundary_loop(welded.astype(np.int32)), dtype=np.int64)
    return Cover(
        model_id=str(cut["model_id"]),
        vertices=vertices,
        faces=faces,
        labels=np.asarray(data["labels"], dtype=np.int64),
        points=points,
        welded=welded,
        names=[p["name"] for p in cut["panels"]],
        regions=[p["region"] for p in cut["panels"]],
        seams=cut["seams"],
        seam_edges=np.asarray(data["seam_edges"], dtype=np.int64),
        seam_index=np.asarray(data["seam_index"], dtype=np.int64),
        hem=hem,
        hem_z=float(hull["hem"]["height_mm"]),
        hem_length=float(cut["hem_length_mm"]),
        area_m2=float(cut["area_m2"]),
        doc=doc,
        rotation_deg=angle,
    )


# ---------------------------------------------------------------- measurements (mm)


def _panel_doc(cover: Cover, name: str) -> dict[str, Any]:
    for p in cover.doc["panels"]:
        if p["name"] == name:
            return dict(p)
    raise KeyError(f"no panel {name!r}")


def skirt_height_at(cover: Cover, xy: Array) -> float:
    """Height of the skirt above the hem at a plan point on the hem: the highest skirt point
    within COLUMN_MM of it."""
    skirt = np.isin(cover.labels, [i for i, r in enumerate(cover.regions) if r == "skirt"])
    v = np.unique(cover.faces[skirt])
    near = v[np.linalg.norm(cover.vertices[v, :2] - xy, axis=1) <= COLUMN_MM]
    if len(near) == 0:
        return 0.0
    return float(cover.vertices[near, 2].max() - cover.hem_z)


def _hem_run(cover: Cover, name: str) -> Array:
    """The panel's part of the hem in plan, in order along the hem."""
    k = cover.names.index(name)
    mine = np.zeros(len(cover.points), dtype=bool)
    mine[cover.welded[cover.labels == k].ravel()] = True
    on = mine[cover.hem]
    if not on.any():
        return np.zeros((0, 2))
    if not on.all():  # start the loop where the run starts
        start = int(np.flatnonzero(on & ~np.roll(on, 1))[0])
        on, ring = np.roll(on, -start), np.roll(cover.hem, -start)
        stop = int(np.argmin(on)) if not on.all() else len(on)
        return cover.points[ring[:stop], :2]
    return cover.points[cover.hem, :2]


def skirt_heights(cover: Cover, name: str) -> tuple[float, float, float]:
    """Height of a skirt panel above the hem: in the middle of its hem, and the lowest and
    highest along it (the outer tenth at each end left out, where the corner seams run)."""
    run = _hem_run(cover, name)
    if len(run) < 2:
        return 0.0, 0.0, 0.0
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(run, axis=0), axis=1))])
    at = np.linspace(0.1 * s[-1], 0.9 * s[-1], 41)  # param-ok: stations along the skirt
    heights = [
        skirt_height_at(cover, np.array([np.interp(t, s, run[:, 0]), np.interp(t, s, run[:, 1])]))
        for t in at
    ]
    return heights[len(heights) // 2], min(heights), max(heights)


def skirt_height(cover: Cover, name: str) -> float:
    return skirt_heights(cover, name)[0]


def straight_hem(cover: Cover) -> tuple[float, Array]:
    """The longest straight run of the hem in plan: its length and its two end points."""
    ring = shapely.LinearRing(cover.points[cover.hem, :2]).simplify(STRAIGHT_MM)
    pts = np.asarray(ring.coords)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    i = int(np.argmax(seg))
    return float(seg[i]), pts[i : i + 2]


def panel_width(cover: Cover, name: str) -> float:
    """Typical width of a flat panel: the median width across its long axis."""
    poly = shapely.Polygon(_panel_doc(cover, name)["outline_mm"]).buffer(0)
    if isinstance(poly, shapely.MultiPolygon):
        poly = max(poly.geoms, key=lambda g: g.area)
    rect = np.asarray(poly.minimum_rotated_rectangle.exterior.coords)[:3]
    a, b = rect[1] - rect[0], rect[2] - rect[1]
    axis = a if np.linalg.norm(a) >= np.linalg.norm(b) else b
    axis = axis / np.linalg.norm(axis)
    across = np.array([-axis[1], axis[0]])
    pts = np.asarray(poly.exterior.coords)
    along = pts @ axis
    lo, hi = along.min(), along.max()
    reach = float(np.ptp(pts @ across)) + 1.0
    widths = []
    for t in np.linspace(lo + WIDTH_SPAN[0] * (hi - lo), lo + WIDTH_SPAN[1] * (hi - lo), 25):
        base = axis * t + across * float((pts @ across).min() - 0.5)  # param-ok: layout
        line = shapely.LineString([base, base + across * reach])
        widths.append(float(poly.intersection(line).length))
    return float(np.median(widths))


def seam_sides(cover: Cover) -> dict[str, dict[str, float]]:
    """Flat length of every seam on each of its panels."""
    out: dict[str, dict[str, float]] = {}
    for p in cover.doc["panels"]:
        for e in p["edges"]:
            if e["kind"] == "seam":
                side = out.setdefault(e["seam"], {})
                side[p["name"]] = side.get(p["name"], 0.0) + float(e["length_2d_mm"])
    return out


def measure(cover: Cover, key: str) -> float | None:
    """A size by name (the keys a reference's `compare` map uses), in mm."""
    kind, _, arg = key.partition(":")
    try:
        if kind == "total_height":
            return float(cover.vertices[:, 2].max() - cover.hem_z)
        if kind == "plan_extent_a":
            return float(np.ptp(cover.vertices[:, 0]))
        if kind == "plan_extent_b":
            return float(np.ptp(cover.vertices[:, 1]))
        if kind == "hem_length" and not arg:
            return cover.hem_length
        if kind == "hem_length":
            p = _panel_doc(cover, arg)
            return float(sum(e["length_3d_mm"] for e in p["edges"] if e["kind"] == "hem"))
        if kind == "straight_hem":
            return straight_hem(cover)[0]
        if kind == "skirt_height":
            return skirt_height(cover, arg)
        if kind == "skirt_lowest":
            return skirt_heights(cover, arg)[1]
        if kind == "skirt_highest":
            return skirt_heights(cover, arg)[2]
        if kind == "panel_width":
            return panel_width(cover, arg)
        if kind == "seam_length":
            return float(next(s["length_mm"] for s in cover.seams if s["id"] == arg))
    except (KeyError, StopIteration, ValueError):
        return None
    return None


def key_sizes(cover: Cover) -> list[tuple[str, str]]:
    """(label, measure key) of the sizes listed for every cover."""
    rows = [
        ("Total height (hem to top)", "total_height"),
        ("Top view, across", "plan_extent_a"),
        ("Top view, depth", "plan_extent_b"),
        ("Hem length (bottom circumference)", "hem_length"),
        ("Longest straight run of the hem", "straight_hem"),
    ]
    for name, region in zip(cover.names, cover.regions, strict=True):
        if region == "skirt":
            rows.append((f"Skirt height, middle of {name}", f"skirt_height:{name}"))
            rows.append((f"Skirt height, lowest along {name}", f"skirt_lowest:{name}"))
            rows.append((f"Skirt height, highest along {name}", f"skirt_highest:{name}"))
            rows.append((f"Hem length of {name}", f"hem_length:{name}"))
    return rows


def find_reference(model_dir: Path, model_id: str) -> dict[str, Any] | None:
    for path in (
        model_dir / "reference.json",
        repo_root() / "testdata" / "reference" / f"{model_id}.json",
    ):
        if path.is_file():
            doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return doc
    return None


def comparison(cover: Cover, reference: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Rows of the key-size table: label, calculated, reference (or None), in mm."""
    rows: list[dict[str, Any]] = []
    covered: set[str] = set()
    if reference:
        dims = reference.get("dimensions_mm", {})
        for ref_key, spec in reference.get("compare", {}).items():
            if ref_key not in dims:
                continue
            rows.append(
                {
                    "label": spec.get("label", ref_key),
                    "calculated": measure(cover, spec["measure"]),
                    "reference": float(dims[ref_key]),
                }
            )
            covered.add(spec["measure"])
    for label, key in key_sizes(cover):
        if key not in covered:
            rows.append({"label": label, "calculated": measure(cover, key), "reference": None})
    return rows


# ---------------------------------------------------------------- drawing helpers


def cm(mm: float) -> str:
    return f"{mm / MM_PER_CM:.1f} cm"


def _dim(ax: Axes, a: Array, b: Array, offset: float, text: str, size: float = FONT) -> None:
    """An aligned dimension between a and b, drawn `offset` mm to the left of a→b."""
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    d = b - a
    n = np.array([-d[1], d[0]]) / (np.linalg.norm(d) or 1.0)
    a2, b2 = a + n * offset, b + n * offset
    gap = n * np.sign(offset) * abs(offset) * 0.1  # param-ok: layout
    for p, q in ((a, a2), (b, b2)):
        ax.plot(
            *np.column_stack([p + gap, q + n * np.sign(offset) * abs(offset) * 0.15]),
            color=DIM_COLOUR,
            lw=0.4,
        )
    ax.annotate(
        "",
        xy=tuple(b2),
        xytext=tuple(a2),
        arrowprops={
            "arrowstyle": "<|-|>",
            "color": DIM_COLOUR,
            "lw": 0.5,  # param-ok: layout
            "shrinkA": 0,
            "shrinkB": 0,
            "mutation_scale": 6,
        },
    )
    angle = math.degrees(math.atan2(d[1], d[0]))
    if angle > 90 or angle <= -90:  # param-ok: degrees
        angle -= 180
    mid = (a2 + b2) / 2
    ax.text(
        float(mid[0]),
        float(mid[1]),
        text,
        rotation=angle,
        rotation_mode="anchor",
        ha="center",
        va="bottom" if offset >= 0 else "top",
        fontsize=size,
        color=DIM_COLOUR,
        bbox={
            "facecolor": "white",
            "edgecolor": "none",
            "pad": 0.5,  # param-ok: layout
            "alpha": 0.8,
        },  # param-ok: layout
    )


def _projected(cover: Cover, view: View, points: Array) -> Array:
    return np.column_stack([points @ view.right, points @ view.up])


def _shaded(ax: Axes, cover: Cover, view: View) -> None:
    n = cover.normals
    facing = n @ view.eye > 0
    faces = cover.welded[facing]
    depth = (cover.points[faces] @ view.eye).mean(axis=1)
    order = np.argsort(depth, kind="stable")
    light = view.eye + 0.5 * view.up - 0.3 * view.right  # param-ok: light from above left
    light /= np.linalg.norm(light)
    shade = SHADE_MIN + (1 - SHADE_MIN) * np.clip(n[facing] @ light, 0, 1)
    top = np.array([r == "top" for r in cover.regions])[cover.labels[facing]]
    rgb = np.where(top[:, None], TOP_RGB, SKIRT_RGB) * shade[:, None]
    p2 = _projected(cover, view, cover.points)
    polys = PolyCollection(
        list(p2[faces[order]]),
        facecolors=rgb[order],
        edgecolors=rgb[order],
        linewidths=0.2,
        rasterized=True,
    )
    ax.add_collection(polys)
    # seams and hem where the surface next to them faces the viewer
    visible = _edge_visibility(cover, facing)
    seams = cover.seam_edges[visible[: len(cover.seam_edges)]]
    ax.add_collection(
        LineCollection(list(p2[seams]), colors=SEAM_COLOUR, linewidths=0.5)  # param-ok: layout
    )  # param-ok: layout
    hem = np.column_stack([cover.hem, np.roll(cover.hem, -1)])
    ax.add_collection(
        LineCollection(
            list(p2[hem[visible[len(cover.seam_edges) :]]]), colors=HEM_COLOUR, linewidths=1.0
        )
    )
    lo, hi = p2.min(axis=0), p2.max(axis=0)
    ax.set_xlim(lo[0], hi[0])
    ax.set_ylim(lo[1], hi[1])
    ax.set_aspect("equal")
    ax.axis("off")
    # panel names
    for k, name in enumerate(cover.names):
        mine = cover.labels == k
        if view.name == "top" and cover.regions[k] != "top":
            continue
        area = np.linalg.norm(
            np.cross(*(np.diff(cover.points[cover.welded[mine]], axis=1).transpose(1, 0, 2))),
            axis=1,
        )
        seen = facing[mine]
        if area.sum() == 0 or area[seen].sum() < VISIBLE_SHARE * area.sum():
            continue
        centre = (cover.points[cover.welded[mine][seen]].mean(axis=1) * area[seen, None]).sum(
            0
        ) / area[seen].sum()
        at = _projected(cover, view, centre[None])[0]
        ax.text(
            float(at[0]),
            float(at[1]),
            name,
            fontsize=FONT - 1,
            ha="center",
            va="center",
            color="#111",
            zorder=5,  # param-ok: layout
        )


def _edge_visibility(cover: Cover, facing: NDArray[np.bool_]) -> NDArray[np.bool_]:
    """Per seam edge, then per hem edge: whether a face next to it faces the viewer."""
    hem = np.column_stack([cover.hem, np.roll(cover.hem, -1)])
    edges = np.vstack([cover.seam_edges, hem])
    size = int(cover.points.shape[0])
    keys = np.sort(edges, axis=1) @ np.array([size, 1])
    f = cover.welded
    face_edges = np.sort(np.stack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]], axis=1), axis=2)
    face_keys = (face_edges @ np.array([size, 1])).ravel()
    face_seen = np.repeat(facing, 3)
    seen_keys = np.unique(face_keys[face_seen])
    return np.isin(keys, seen_keys)


def _seam_path(cover: Cover, index: int) -> Array:
    """The seam's points in order (walking its edges from one end)."""
    edges = cover.seam_edges[cover.seam_index == index]
    nbr: dict[int, list[int]] = {}
    for a, b in edges.tolist():
        nbr.setdefault(a, []).append(b)
        nbr.setdefault(b, []).append(a)
    start = min((v for v, n in nbr.items() if len(n) == 1), default=min(nbr))
    path, seen = [start], {start}
    while True:
        nxt = [v for v in nbr[path[-1]] if v not in seen]
        if not nxt:
            break
        path.append(min(nxt))
        seen.add(path[-1])
    return cover.points[path]


def _midpoint(points: Array) -> Array:
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))])
    i = int(np.clip(np.searchsorted(s, s[-1] / 2), 0, len(points) - 1))
    return points[i]


# ---------------------------------------------------------------- pages


def _overview(cover: Cover, params: EffectiveParams, reference: dict[str, Any] | None) -> Figure:
    fig = Figure(figsize=(A4_MM[0] / MM_PER_INCH, A4_MM[1] / MM_PER_INCH))
    views = _views()
    v = cover.vertices
    lo, hi = v.min(axis=0), v.max(axis=0)
    span = float(max(np.ptp(v[:, 0]), np.ptp(v[:, 1])))
    pad = 0.12 * span  # param-ok: room for dimensions around a view

    fig.text(0.05, 0.975, f"{cover.model_id}: calculated cover", fontsize=11, weight="bold")
    fig.text(
        0.05,
        0.96,
        "Sizes seam to seam on the finished cover, without seam allowances or hem.",
        fontsize=FONT,
    )

    # top view
    ax = fig.add_axes((0.05, 0.59, 0.62, 0.34))
    _shaded(ax, cover, views["top"])
    ax.plot(
        [lo[0], hi[0], hi[0], lo[0], lo[0]],
        [lo[1], lo[1], hi[1], hi[1], lo[1]],
        ls="--",
        lw=0.4,
        color="#777",
    )
    _dim(ax, np.array([hi[0], lo[1]]), np.array([lo[0], lo[1]]), pad * 0.35, cm(hi[0] - lo[0]))
    _dim(ax, np.array([lo[0], lo[1]]), np.array([lo[0], hi[1]]), pad * 0.35, cm(hi[1] - lo[1]))
    length, ends = straight_hem(cover)
    if length > 0.2 * span:  # param-ok: only a real straight side is dimensioned
        inside = shapely.Polygon(cover.points[cover.hem, :2])
        mid = ends.mean(axis=0)
        d = ends[1] - ends[0]
        n = np.array([-d[1], d[0]]) / np.linalg.norm(d)
        a, b = (
            (ends[0], ends[1])
            if not inside.contains(shapely.Point(*(mid + n)))
            else (ends[1], ends[0])
        )
        _dim(ax, a, b, pad * 0.3, cm(length))
    for i, seam in enumerate(cover.seams):
        a, b = seam["panels"]
        if cover.regions[cover.names.index(a)] == cover.regions[cover.names.index(b)] == "top":
            m = _midpoint(_seam_path(cover, i))
            ax.text(
                m[0],
                m[1],
                cm(seam["length_mm"]),
                fontsize=FONT - 1.5,
                ha="center",
                va="center",
                color="black",
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.4, "alpha": 0.75},
            )
    ax.set_xlim(lo[0] - pad, hi[0] + pad)
    ax.set_ylim(lo[1] - pad, hi[1] + pad)
    ax.set_title("Top view", fontsize=FONT + 1, loc="left")
    note = f"Hem (bottom circumference): {cm(cover.hem_length)}\nTop seams: length on the cover"
    if cover.rotation_deg:
        note += f"\nTurned {cover.rotation_deg:g}° from the 3D model"
    fig.text(0.70, 0.90, note, fontsize=FONT, va="top")

    # front and side view
    height = hi[2] - cover.hem_z
    for name, box, (a0, a1) in (
        ("front", (0.05, 0.36, 0.50, 0.22), (lo[0], hi[0])),  # param-ok: layout
        ("side", (0.58, 0.36, 0.38, 0.22), (lo[1], hi[1])),
    ):
        ax = fig.add_axes(box)
        _shaded(ax, cover, views[name])
        axis = 0 if name == "front" else 1
        pad_v = 0.15 * max(a1 - a0, height)  # param-ok: room for dimensions
        _dim(ax, np.array([a1, cover.hem_z]), np.array([a0, cover.hem_z]), pad_v * 0.4, cm(a1 - a0))
        _dim(ax, np.array([a1, cover.hem_z]), np.array([a1, hi[2]]), -pad_v * 0.55, cm(height))
        # the skirt at both ends of the view
        for end, sign in ((a0, 1.0), (a1, -1.0)):
            ring = cover.points[cover.hem]
            at = ring[
                int(np.argmin(np.abs(ring[:, axis] - end) + 1e-3 * np.abs(ring[:, 1 - axis])))
            ]
            h = skirt_height_at(cover, at[:2])
            if h > 0:
                _dim(
                    ax,
                    np.array([end, cover.hem_z]),
                    np.array([end, cover.hem_z + h]),
                    sign * pad_v * 0.25,
                    cm(h),
                )
        ax.set_xlim(a0 - pad_v, a1 + pad_v)
        ax.set_ylim(cover.hem_z - pad_v, hi[2] + pad_v * 0.5)  # param-ok: layout
        ax.set_title(
            "Front view" if name == "front" else "Side view (from the right)",
            fontsize=FONT + 1,
            loc="left",
        )

    # 3D view
    ax = fig.add_axes((0.10, 0.10, 0.80, 0.25))  # param-ok: layout
    _shaded(ax, cover, views["iso"])
    ax.set_title("3D view", fontsize=FONT + 1, loc="left")

    _title_block(fig, cover, params, reference)
    return fig


def vent_count(hem_mm: float, params: EffectiveParams) -> int:
    if int(params["features.vents_total"]) > 0:  # the drawing's own number wins (owner)
        return int(params["features.vents_total"])
    per_m = float(params["features.vents_per_metre"])  # type: ignore[arg-type]
    return max(
        int(params["features.vents_min"]), int(hem_mm / 1000.0 * per_m)
    )  # param-ok: mm per m


def _title_block(
    fig: Figure, cover: Cover, params: EffectiveParams, reference: dict[str, Any] | None
) -> None:
    ax = fig.add_axes((0.05, 0.015, 0.90, 0.07))
    ax.set_xlim(0, 3)
    ax.set_ylim(0, 3)
    ax.axis("off")
    summary = cover.doc["summary"]
    cells = [
        ("Model", cover.model_id),
        ("Fabric", f"{params['fabric.profile']}, roll {cm(float(params['roll.width_mm']))}"),  # type: ignore[arg-type]
        ("Panels", f"{summary['panels']}, {summary['fabric_area_m2']:.2f} m² flat"),
        ("Fit", f"{params['hull.clearance_mm']} mm clearance, {params['hull.edge']}"),
        ("Hem", f"open bottom, {cm(cover.hem_z)} above ground"),
        (
            "Air vents",
            f"{vent_count(cover.hem_length, params)} × "
            f"{cm(float(params['features.vent_width_mm']))} × "  # type: ignore[arg-type]
            f"{cm(float(params['features.vent_height_mm']))} (M5)",
        ),  # type: ignore[arg-type]
        ("Engine", f"{__version__}, parameters {cover.doc['parameter_hash'][:HASH_CHARS]}"),
        ("Reference", "compared on page 2" if reference else "none"),
        ("Stretch", f"worst panel {summary['max_stretch_pct']:.1f} %"),
    ]
    for i, (k, v) in enumerate(cells):
        col, row = i % 3, 2 - i // 3
        ax.add_patch(_rect(col, row))
        mid, size = row + CELL_MID, FONT - CELL_MID
        ax.text(col + 0.03, mid, f"{k}: ", fontsize=size, color="#1f3fbf", va="center")
        ax.text(col + 0.22, mid, v, fontsize=size, va="center")


def _rect(x: float, y: float) -> Any:
    from matplotlib.patches import Rectangle

    return Rectangle((x, y), 1, 1, fill=False, lw=0.4, edgecolor="#999")


class _TablePages:
    """Tables flowed over A4 pages."""

    def __init__(self, title: str) -> None:
        self.pages: list[Figure] = []
        self.title = title
        self._new()

    def _new(self) -> None:
        self.fig = Figure(figsize=(A4_MM[0] / MM_PER_INCH, A4_MM[1] / MM_PER_INCH))
        self.pages.append(self.fig)
        self.y = A4_MM[1] - 15.0  # param-ok: top margin (mm)
        if len(self.pages) == 1:
            self._text(15.0, self.y, self.title, FONT + 4, bold=True)  # param-ok: layout
            self.y -= 2 * ROW_MM

    def _text(
        self,
        x: float,
        y: float,
        s: str,
        size: float = FONT,
        bold: bool = False,
        colour: str = "black",
        ha: str = "left",
    ) -> None:
        self.fig.text(
            x / A4_MM[0],
            y / A4_MM[1],
            s,
            fontsize=size,
            weight="bold" if bold else "normal",
            color=colour,
            ha=ha,
            va="center",
        )

    def note(self, s: str) -> None:
        for line in s.split("\n"):
            if self.y < 20.0:  # param-ok: bottom margin (mm)
                self._new()
            self._text(15.0, self.y, line, FONT)  # param-ok: left margin (mm)
            self.y -= ROW_MM * 0.8

    def table(
        self, title: str, columns: list[tuple[str, float, str]], rows: list[list[Any]]
    ) -> None:
        """columns: (header, width mm, "l" or "r"); a row cell is text or (text, colour)."""

        def header() -> None:
            self._text(15.0, self.y, title, FONT + 2, bold=True)  # param-ok: layout
            self.y -= ROW_MM
            self._row([(h, "black") for h, _, _ in columns], columns, bold=True)

        if self.y < 40.0:  # param-ok: keep a title with its first rows (mm)
            self._new()
        header()
        for r in rows:
            if self.y < 20.0:  # param-ok: bottom margin (mm)
                self._new()
                header()
            self._row([c if isinstance(c, tuple) else (str(c), "black") for c in r], columns)
        self.y -= ROW_MM

    def _row(
        self,
        cells: list[tuple[str, str]],
        columns: list[tuple[str, float, str]],
        bold: bool = False,
    ) -> None:
        x = 15.0  # param-ok: left margin (mm)
        for (text, colour), (_, width, align) in zip(cells, columns, strict=True):
            self._text(
                x + (width - 1.5 if align == "r" else 0.0),
                self.y,
                text,
                FONT,
                bold,
                colour,
                "right" if align == "r" else "left",
            )
            x += width
        self.fig.add_artist(_line(15.0, x, self.y - ROW_MM / 2))  # param-ok: layout
        self.y -= ROW_MM


def _line(x0: float, x1: float, y: float) -> Any:
    from matplotlib.lines import Line2D

    return Line2D([x0 / A4_MM[0], x1 / A4_MM[0]], [y / A4_MM[1]] * 2, lw=0.3, color="#bbb")


def _size_pages(
    cover: Cover, params: EffectiveParams, reference: dict[str, Any] | None
) -> list[Figure]:
    t = _TablePages(f"{cover.model_id}: sizes")
    tol = float(params["tolerance.cover_mm"])  # type: ignore[arg-type]
    t.note(
        "All sizes seam to seam on the finished cover, in cm, without seam allowances or hem.\n"
        "Flat: measured along the edge of the flat pattern piece."
    )
    t.y -= ROW_MM * 0.5  # param-ok: layout
    rows = comparison(cover, reference)
    if reference:
        table = []
        for r in rows:
            calc = "–" if r["calculated"] is None else cm(r["calculated"])
            if r["reference"] is None:
                table.append([r["label"], calc, "", ""])
                continue
            if r["calculated"] is None:
                table.append([r["label"], calc, cm(r["reference"]), ""])
                continue
            d = r["calculated"] - r["reference"]
            colour = OK_COLOUR if abs(d) <= tol else OFF_COLOUR
            table.append(
                [r["label"], calc, cm(r["reference"]), (f"{d / MM_PER_CM:+.1f} cm", colour)]
            )
        t.table(
            "Key sizes",
            [
                ("Size", 85.0, "l"),
                ("Calculated", 30.0, "r"),  # param-ok: layout
                ("Your cover", 30.0, "r"),  # param-ok: layout
                ("Difference", 30.0, "r"),  # param-ok: layout
            ],
            table,
        )
        t.note(f"Difference in green: within the fit tolerance of ±{tol:g} mm.")
        t.y -= ROW_MM * 0.5  # param-ok: layout
    else:
        t.table(
            "Key sizes",
            [("Size", 100.0, "l"), ("Calculated", 30.0, "r")],  # param-ok: layout
            [[r["label"], "–" if r["calculated"] is None else cm(r["calculated"])] for r in rows],
        )

    sides = seam_sides(cover)
    seam_rows = []
    for s in cover.seams:
        a, b = s["panels"]
        la, lb = sides.get(s["id"], {}).get(a), sides.get(s["id"], {}).get(b)
        ease = abs(la - lb) if la is not None and lb is not None else None
        seam_tol = float(params["seams.seam_tolerance_mm"])  # type: ignore[arg-type]
        seam_rows.append(
            [
                s["id"],
                s["kind"],
                cm(s["length_mm"]),
                "" if la is None else f"{a} {cm(la)}",
                "" if lb is None else f"{b} {cm(lb)}",
                ""
                if ease is None
                else (f"{ease:.1f} mm", OK_COLOUR if ease <= seam_tol else OFF_COLOUR),
            ]
        )
    t.table(
        "Seams",
        [
            ("Seam", 42.0, "l"),
            ("Kind", 14.0, "l"),
            ("On the cover", 22.0, "r"),
            ("Flat, first panel", 38.0, "r"),
            ("Flat, second panel", 38.0, "r"),
            ("Difference", 22.0, "r"),
        ],
        seam_rows,
    )
    t.note("Difference between the two flat panels along one seam; it is eased in when sewing.")
    t.y -= ROW_MM * 0.5  # param-ok: layout

    limit = float(params["fabric.max_allowed_stretch_pct"])  # type: ignore[arg-type]
    cut = {p["name"]: p for p in cover.doc["panels"]}
    panel_rows = []
    for k, name in enumerate(cover.names):
        p = cut[name]
        q = p["stretch"]["quantile_pct"]
        panel_rows.append(
            [
                f"{p['id']} {name}",
                cover.regions[k],
                f"{p['flat_length_mm'] / MM_PER_CM:.1f} × {p['flat_width_mm'] / MM_PER_CM:.1f} cm",
                cm(panel_width(cover, name)),
                (f"{q:.1f} %", OK_COLOUR if q <= limit else OFF_COLOUR),
                ("yes", OK_COLOUR) if p["fits_roll"] else ("NO", OFF_COLOUR),
            ]
        )
    t.table(
        "Panels",
        [
            ("Panel", 40.0, "l"),  # param-ok: layout
            ("Region", 16.0, "l"),
            ("Flat size (length × width)", 46.0, "r"),
            ("Typical width", 26.0, "r"),
            ("Stretch", 20.0, "r"),  # param-ok: layout
            ("Fits roll", 20.0, "r"),  # param-ok: layout
        ],
        panel_rows,
    )
    t.note(
        f"Flat size in the narrowest direction. Stretch: the most the flat piece stretches or "
        f"squeezes over {float(params['flatten.stretch_quantile']) * 100:g} % of its area "  # type: ignore[arg-type] # param-ok: layout
        f"(limit {limit:g} %)."
    )
    return t.pages


def _panel_page(cover: Cover, p: dict[str, Any], params: EffectiveParams) -> Figure:
    w_mm, h_mm = A4_MM[1], A4_MM[0]  # landscape
    fig = Figure(figsize=(w_mm / MM_PER_INCH, h_mm / MM_PER_INCH))
    outline = np.asarray(p["outline_mm"], dtype=np.float64)
    lo, hi = outline.min(axis=0), outline.max(axis=0)
    size = hi - lo
    box = (15.0, 32.0, w_mm - 30.0, h_mm - 50.0)  # param-ok: drawing area on the page (mm)
    room = (100.0, 40.0)  # param-ok: paper (mm) kept free for edge labels and dimensions
    scale = next(
        (s for s in SCALES if size[0] / s + room[0] <= box[2] and size[1] / s + room[1] <= box[3]),
        SCALES[-1],
    )
    ax = fig.add_axes((box[0] / w_mm, box[1] / h_mm, box[2] / w_mm, box[3] / h_mm))
    centre = (lo + hi) / 2
    ax.set_xlim(centre[0] - box[2] * scale / 2, centre[0] + box[2] * scale / 2)
    ax.set_ylim(centre[1] - box[3] * scale / 2, centre[1] + box[3] * scale / 2)
    ax.set_aspect("equal")
    ax.axis("off")
    closed = np.vstack([outline, outline[:1]])
    ax.fill(closed[:, 0], closed[:, 1], color=TOP_RGB, alpha=0.25, lw=0)
    n = len(outline)
    poly = shapely.Polygon(outline)
    for e in p["edges"]:
        i0, i1 = e["range"]
        idx = [(i0 + j) % n for j in range((i1 - i0) % n + 1)]
        pts = outline[idx]
        colour = HEM_COLOUR if e["kind"] == "hem" else SEAM_COLOUR
        ax.plot(pts[:, 0], pts[:, 1], color=colour, lw=1.0)
        mid = _midpoint(pts)
        k = int(np.argmin(np.linalg.norm(pts - mid, axis=1)))
        t = pts[min(k + 1, len(pts) - 1)] - pts[max(k - 1, 0)]
        t = t / (np.linalg.norm(t) or 1.0)
        out = np.array([t[1], -t[0]])
        if poly.contains(shapely.Point(*(mid + out * scale))):
            out = -out
        text = ("HEM" if e["kind"] == "hem" else f"to {e['mate']}") + f"  {cm(e['length_2d_mm'])}"
        ax.annotate(
            text,
            xy=tuple(mid),
            xytext=tuple(out * 8),  # param-ok: layout
            textcoords="offset points",
            fontsize=FONT,
            color=colour,
            ha="left" if out[0] > 0.3 else "right" if out[0] < -0.3 else "center",  # param-ok
            va="bottom" if out[1] > 0.3 else "top" if out[1] < -0.3 else "center",
        )  # param-ok
        ax.plot(*mid, marker="o", ms=1.5, color=colour)
    for m in p["pen"]:
        at = np.asarray(m["at"], dtype=np.float64)
        if m["type"] == "tick":
            end = at + np.asarray(m["dir"]) * float(m["length"]) * 2
            ax.plot([at[0], end[0]], [at[1], end[1]], color="#3050c0", lw=0.4)
        elif m["type"] == "fold":  # one piece folded here (ADR-055)
            fold = np.asarray(m["points"], dtype=np.float64)
            ax.plot(fold[:, 0], fold[:, 1], color="#3050c0", lw=0.8, ls="--")
            ax.text(float(at[0]), float(at[1]), "FOLD", fontsize=FONT, color="#3050c0",
                    ha="center", va="bottom")  # fmt: skip
        elif m["type"] == "label":
            ax.text(
                float(at[0]),
                float(at[1]),
                m["text"],
                fontsize=FONT + 3,
                ha="center",
                va="center",
                color="#3050c0",
            )
        elif m["type"] == "arrow_up":
            ax.annotate(
                "",
                xy=(at[0], at[1] + float(m["length"])),
                xytext=tuple(at),
                arrowprops={"arrowstyle": "-|>", "color": "#3050c0", "lw": 0.8},
            )
            ax.text(
                at[0] + float(m["length"]) * 0.15,
                at[1] + float(m["length"]) * 0.5,  # param-ok: layout
                "UP",
                fontsize=FONT,
                color="#3050c0",
                va="center",
            )
    # dimensions outside the edge labels (distances on paper, mm)
    _dim(
        ax, np.array([hi[0], lo[1]]), np.array([lo[0], lo[1]]), 12.0 * scale, cm(size[0])
    )  # param-ok
    _dim(
        ax, np.array([lo[0], lo[1]]), np.array([lo[0], hi[1]]), 42.0 * scale, cm(size[1])
    )  # param-ok
    # title and facts
    fig.text(
        15.0 / w_mm,  # param-ok: layout
        1 - 10.0 / h_mm,  # param-ok: layout
        f"{p['id']}  {p['name']}",
        fontsize=13,
        weight="bold",
        va="top",
    )
    fig.text(
        15.0 / w_mm,  # param-ok: layout
        1 - 17.0 / h_mm,
        f"{cover.model_id} · flat pattern, seam to seam, no allowances · UP = up on the furniture",
        fontsize=FONT,
        va="top",
    )
    usable = float(params["roll.usable_width_mm"])  # type: ignore[arg-type]
    facts = [
        f"Box: {cm(size[0])} × {cm(size[1])}",
        f"Narrowest: {cm(p['flat_width_mm'])} wide, {cm(p['flat_length_mm'])} long "
        f"({'fits' if p['fits_roll'] else 'does NOT fit'} the roll, {cm(usable)} usable)",
        f"Area: {poly.area / 1e6:.3f} m²",
        f"Stretch: {p['stretch']['quantile_pct']:.1f} % "
        f"(worst {p['stretch']['max_pct']:.1f} % at single points)",
        f"Quantity: {p['quantity']}{', mirrored' if p['mirror'] else ''}",
    ]
    for i, f in enumerate(facts):
        fig.text(
            15.0 / w_mm,  # param-ok: layout
            (10.0 + (len(facts) - 1 - i) * 4.2) / h_mm,  # param-ok: layout
            f,
            fontsize=FONT,  # param-ok: layout
        )  # param-ok
    fig.text(
        1 - 15.0 / w_mm,  # param-ok: layout
        10.0 / h_mm,  # param-ok: layout
        f"Scale 1:{scale} on A4. Use the numbers, do not measure the print.",
        fontsize=FONT,
        ha="right",
    )
    fig.text(
        1 - 15.0 / w_mm,  # param-ok: layout
        1 - 10.0 / h_mm,  # param-ok: layout
        "black: seam (to the panel named)   magenta: hem   blue: pen marks",
        fontsize=FONT,
        ha="right",
        va="top",
    )
    return fig


def write_drawing(model_dir: Path, doc: dict[str, Any], params: EffectiveParams, out: Path) -> Path:
    cover = load_cover(model_dir, doc, params)
    reference = find_reference(model_dir, cover.model_id)
    figures = [_overview(cover, params, reference), *_size_pages(cover, params, reference)]
    figures += [_panel_page(cover, p, params) for p in doc["panels"]]
    with PdfPages(
        out, metadata={"CreationDate": None, "Creator": f"cover-pattern-engine {__version__}"}
    ) as pdf:
        for fig in figures:
            pdf.savefig(fig, dpi=DPI)
    from coverengine.export.brand import brand

    return brand(out)
