"""Finished patterns (M5): every flat panel with its seam allowances and hem, the air vents, and
the pen marks for sewing; plus the extra pieces (vent hoods and membranes).

Input: the PatternSet from `cover flatten` (`pattern.json`, seam to seam). Output: the finished
PatternSet (`finished.json`, FORMATS.md). Rules (ADR-030):

- Double-stitched seams: `stitching.allowance_mm` on both panels of a seam
  (`stitching.sides: both`) or only on the lap-side panel (`lap`).
- Welded seams: `welding.overlap_mm` on the lap-side panel only; the under panel gets a guide
  line on the pen layer where the upper panel's edge lands.
- Hem: `hem.allowance_mm` below the hem line; the fold line (the hem line) on the pen layer.
- Where two allowances meet at a corner the corner is square: each allowance runs on until it
  meets the other.
- Air vents (owner, 2026-09-30): `features.vent_*`, one per full metre of hem, at least one,
  spread evenly along the hem, kept `features.vent_seam_clearance_mm` from vertical seams; the
  opening is cut in the skirt panel.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import shapely
from numpy.typing import NDArray

from coverengine import __version__
from coverengine.params import EffectiveParams

Array = NDArray[np.float64]

FORMAT_VERSION = 1
FINISHED_JSON = "finished.json"
# Cut outlines are simplified to this (mm); far below the machine's accuracy.
SIMPLIFY_MM = 0.1  # param-ok: geometric tolerance
MM_PER_M = 1000.0  # param-ok: unit conversion
MM_PER_CM = 10.0  # param-ok: unit conversion
# Pen mark sizes, in label heights.
MARK_LENGTH = 2.0  # param-ok: layout, cord exit mark length in label heights


@dataclass
class Piece:
    """One piece to cut: a panel with allowances, or an extra piece (vent hood, membrane)."""

    id: str
    name: str
    quantity: int
    cut: Array  # closed outline, mm, counter-clockwise, no repeated end point
    net: Array | None  # the seam-to-seam outline (panels only)
    openings: list[Array] = field(default_factory=list)  # cut out of the piece
    pen_lines: list[Array] = field(default_factory=list)  # polylines on the pen layer
    pen_text: list[tuple[str, Array, float]] = field(default_factory=list)  # text, at, height
    edges: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""


def _p(params: EffectiveParams, key: str) -> float:
    return float(params[key])  # type: ignore[arg-type]


def edge_indices(n: int, rng: list[int]) -> list[int]:
    i0, i1 = rng
    return [(i0 + j) % n for j in range((i1 - i0) % n + 1)]


def allowance_of(edge: dict[str, Any], panel: str, params: EffectiveParams) -> float:
    """The allowance (mm) added outside this edge of this panel."""
    if edge["kind"] == "hem":
        return _p(params, "hem.allowance_mm")
    lap = edge.get("lap_side") == panel
    if params["construction.method"] == "welded":
        return _p(params, "welding.overlap_mm") if lap else 0.0
    if params["stitching.sides"] == "lap":
        return _p(params, "stitching.allowance_mm") if lap else 0.0
    return _p(params, "stitching.allowance_mm")


def _tangent(pts: Array, at_end: bool) -> Array:
    d = pts[-1] - pts[-2] if at_end else pts[1] - pts[0]
    n = float(np.linalg.norm(d))
    return d / n if n else np.array([1.0, 0.0])


def cut_outline(outline: Array, edges: list[dict[str, Any]], distances: list[float]) -> Array:
    """The panel grown outward by each edge's own distance; corners square."""
    n = len(outline)
    base = shapely.Polygon(outline)
    parts = [base]
    for k, (e, d) in enumerate(zip(edges, distances, strict=True)):
        if d <= 0:
            continue
        pts = outline[edge_indices(n, e["range"])]
        if len(pts) < 2:
            continue
        before = distances[k - 1]
        after = distances[(k + 1) % len(edges)]
        # run on past both ends by the neighbour's allowance, so the two meet in a square corner
        start = pts[0] - _tangent(pts, False) * before
        end = pts[-1] + _tangent(pts, True) * after
        line = shapely.LineString(np.vstack([start, pts, end]))
        # the outline runs counter-clockwise: outside is on the right (negative side)
        strip = line.buffer(-d, single_sided=True, cap_style="flat", join_style="mitre")
        parts.append(strip)
    try:
        grown = shapely.unary_union(parts)
    except shapely.errors.GEOSException:  # an outline that touches itself: repair and retry
        grown = shapely.unary_union([shapely.make_valid(g).buffer(0) for g in parts])
    if isinstance(grown, shapely.MultiPolygon):
        grown = max(grown.geoms, key=lambda g: g.area)
    grown = shapely.Polygon(grown.exterior).simplify(SIMPLIFY_MM)
    ring = shapely.geometry.polygon.orient(grown, sign=1.0)
    return np.asarray(ring.exterior.coords, dtype=np.float64)[:-1]


def inward_line(pts: Array, poly: shapely.Polygon, d: float) -> Array | None:
    """The polyline moved `d` into the panel (for a weld guide line)."""
    line = shapely.LineString(pts)
    moved = line.offset_curve(d)  # left = inside for a counter-clockwise outline
    if moved.is_empty:
        return None
    if isinstance(moved, shapely.MultiLineString):
        moved = max(moved.geoms, key=lambda g: g.length)
    out = np.asarray(moved.coords, dtype=np.float64)
    if not poly.buffer(1.0).contains(shapely.Point(out[len(out) // 2])):
        return None
    return out


def vent_count(hem_mm: float, params: EffectiveParams) -> int:
    per_m = _p(params, "features.vents_per_metre")
    return max(int(params["features.vents_min"]), int(hem_mm / MM_PER_M * per_m))


def _opening(base: Array, t: Array, up: Array, w: float, h: float) -> Array:
    """A vent opening w wide and h high, its bottom edge centred on `base`."""
    return np.array([base - t * w / 2, base + t * w / 2, base + t * w / 2 + up * h,
                     base - t * w / 2 + up * h])  # fmt: skip


def _fits(poly: Any, rect: Array, allowance: float) -> bool:
    return bool(poly.contains(shapely.Polygon(rect).buffer(allowance, join_style="mitre")))


def _height_at(poly: Any, centre: Array, t: Array, up: Array, width: float) -> float:
    """How high the piece is above its hem at `centre`, the least over `width` along it."""
    reach = float(np.ptp(np.asarray(poly.exterior.coords), axis=0).max()) * 2
    out = math.inf
    for f in (-0.5, 0.0, 0.5):  # param-ok: both ends and the middle of the vent
        p = centre + t * width * f
        line = shapely.LineString([p - up * reach * 0.01, p + up * reach])  # param-ok: start
        cut = poly.intersection(line)  # just below the hem line
        out = min(out, float(cut.length) if not cut.is_empty else 0.0)
    return out


def side_of(panel: str) -> str:
    """The side of the cover a skirt piece is on: skirt-front-2 -> skirt-front."""
    return re.sub(r"-\d+$", "", panel)


@dataclass(frozen=True)
class Walls:
    """What the 3D cover tells about each piece, for the vents (`vent_walls`): the pieces on an
    inner wall, and the way each piece faces (a unit vector in plan, out of the cover)."""

    inner: frozenset[str] = frozenset()
    facing: dict[str, tuple[float, float]] = field(default_factory=dict)


PROBE_MM = 50.0  # param-ok: a point this far beside a wall tells out from in (as vents3d)
EDGE_ON_MM2 = 2.0  # param-ok: twice a triangle's plan area below this: upright, edge-on
GROW_MM = 1.0  # param-ok: the footprint grown this much (the triangles' own seams)


def vent_walls(model_dir: Any, params: EffectiveParams) -> Walls:
    """For every piece, from `panels.npz`: whether its bottom lies on an inner wall (an L, U or
    C shape's walls facing its own open corner: half of its bottom edge or more lies
    `features.vent_inner_mm` or more inside the footprint's convex hull; ADR-093, they get vents
    unless `features.vent_inner_walls` is off, ADR-109), and which way
    its lower part faces (ADR-101: the vents go round all sides of the cover)."""
    import json
    from pathlib import Path

    npz, pj = Path(model_dir) / "panels.npz", Path(model_dir) / "panels.json"
    if not npz.is_file() or not pj.is_file():
        return Walls()
    names = [p["name"] for p in json.loads(pj.read_text(encoding="utf-8"))["panels"]]
    data = np.load(npz)
    v, f, labels = data["vertices"], data["faces"], data["labels"]
    hull = shapely.MultiPoint(v[:, :2]).convex_hull
    deep = _p(params, "features.vent_inner_mm")
    band = _p(params, "features.vent_above_hem_mm") + _p(params, "features.vent_height_mm")
    near = _p(params, "features.vent_above_hem_mm")
    tri = v[f]
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    normal = np.cross(e1, e2)
    # seen from above, the cover covers what its not-upright faces cover (as vents3d)
    flat = np.abs(normal[:, 2]) > EDGE_ON_MM2
    footprint = shapely.union_all([shapely.Polygon(t[:, :2]) for t in tri[flat]]).buffer(GROW_MM)
    inner, facing = set(), {}
    for i, name in enumerate(names):
        mine = labels == i
        if not mine.any():
            continue
        t = tri[mine]
        z0 = float(t[:, :, 2].min())
        pts = t.reshape(-1, 3)
        bottom = np.unique(pts[pts[:, 2] <= z0 + near][:, :2].round(), axis=0)
        if not len(bottom):
            continue
        # half the bottom or more that far in (a round piece's middle lies inside, its wall not)
        if float(np.median(shapely.distance(hull.exterior, shapely.points(bottom)))) >= deep:
            inner.add(name)
        low = t[:, :, 2].mean(axis=1) <= z0 + band
        n = normal[mine][low][:, :2].sum(axis=0)
        size = float(np.linalg.norm(n))
        if size <= 0:
            continue
        d = n / size
        probe = bottom.mean(axis=0) + d * PROBE_MM
        if footprint.contains(shapely.Point(float(probe[0]), float(probe[1]))):
            d = -d  # cover beyond it: that was the inside
        facing[name] = (float(d[0]), float(d[1]))
    return Walls(frozenset(inner), facing)


def inner_skirts(model_dir: Any, params: EffectiveParams) -> frozenset[str]:
    """Skirt pieces on an inner wall (ADR-093), see `vent_walls`."""
    return frozenset(n for n in vent_walls(model_dir, params).inner if n.startswith("skirt"))


def _spread(
    pieces: list[str],
    lengths: dict[str, float],
    n: int,
    same: Any,
) -> dict[str, int]:
    """`n` vents over `pieces` (Rens, 8 Oct 2026: "the right number, but too many at the back"):
    first one per piece, a side not served yet before one that is, the longest first; then each
    further vent to the piece with the most length per vent (the longest walls get two)."""
    order = sorted(pieces, key=lambda p: (-lengths[p], p))
    counts = dict.fromkeys(order, 0)
    served: list[str] = []
    left = n
    while left > 0 and any(counts[p] == 0 for p in order):
        new = [p for p in order if counts[p] == 0 and not any(same(p, q) for q in served)]
        p = new[0] if new else next(q for q in order if counts[q] == 0)
        counts[p] = 1
        served.append(p)
        left -= 1
    while left > 0 and order:
        p = max(order, key=lambda q: (lengths[q] / (counts[q] + 1), -order.index(q)))
        counts[p] += 1
        left -= 1
    return counts


def per_side(
    lengths: dict[str, float], params: EffectiveParams, same: Any = None
) -> dict[str, int]:
    """Vents per side of the cover: one per full metre of that side, at least one (owner, 1 Oct
    2026: each side separately; 2.10 m: 2, 2.90 m: 2, 3.10 m: 3, 1.40 m: 1). A number written
    on the drawing (`features.vents_total`) always wins: one on every side first, then the
    longest sides get more (Rens, 8 Oct 2026; ADR-101)."""
    total = int(params["features.vents_total"])
    if total <= 0 or not lengths:
        return {k: vent_count(v, params) for k, v in lengths.items()}
    return _spread(list(lengths), lengths, total, same or (lambda a, b: a == b))


@dataclass
class HemRun:
    panel: str
    points: Array  # along the hem, in the panel's own coordinates
    length: float
    kind: str = "hem"  # hem: the cover's lower end; above: the seam over a skirt too low for a vent


def _hem_runs(panels: list[dict[str, Any]], skirt_order: list[str]) -> list[HemRun]:
    by_name = {p["name"]: p for p in panels}
    runs = []
    for name in skirt_order:
        p = by_name[name]
        outline = np.asarray(p["outline_mm"], dtype=np.float64)
        for e in p["edges"]:
            if e["kind"] == "hem":
                pts = outline[edge_indices(len(outline), e["range"])]
                seg = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())
                runs.append(HemRun(name, pts, seg))
    return runs


def skirt_order(panels: list[dict[str, Any]]) -> list[str]:
    """Skirt panels in order round the cover (following the vertical seams between them)."""
    skirts = [p["name"] for p in panels if p["name"].startswith("skirt")]
    if len(skirts) <= 1:
        return skirts
    nxt: dict[str, list[str]] = {s: [] for s in skirts}
    for p in panels:
        if p["name"] not in nxt:
            continue
        for e in p["edges"]:
            if e["kind"] == "seam" and e.get("mate") in nxt and e["mate"] not in nxt[p["name"]]:
                nxt[p["name"]].append(e["mate"])
    order, seen = [skirts[0]], {skirts[0]}
    while True:
        cand = [s for s in sorted(nxt[order[-1]]) if s not in seen]
        if not cand:
            break
        order.append(cand[0])
        seen.add(cand[0])
    order += [s for s in skirts if s not in seen]
    return order


def _point_along(pts: Array, s: float) -> tuple[Array, Array]:
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    acc = np.concatenate([[0.0], np.cumsum(seg)])
    s = float(np.clip(s, 0.0, acc[-1]))
    i = int(np.clip(np.searchsorted(acc, s) - 1, 0, len(seg) - 1))
    t = (pts[i + 1] - pts[i]) / (seg[i] or 1.0)
    return pts[i] + t * (s - acc[i]), t


def _run(outline: Array, e: dict[str, Any], name: str, kind: str) -> HemRun:
    pts = outline[edge_indices(len(outline), e["range"])]
    return HemRun(name, pts, float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum()), kind)


def vent_bases(
    panels: list[dict[str, Any]], params: EffectiveParams, skip: frozenset[str] = frozenset()
) -> tuple[dict[str, list[HemRun]], list[str]]:
    """Where vents can stand, per piece: the runs of its bottom edge (ADR-101).

    With the edges' heights in `pattern.json` (`z_mm`): every piece's hem at the cover's lower
    end, never a free edge higher up (C24's vent hung upside down from the top of a wall); and
    over a skirt too low for a vent, the seam on top of it (`features.vent_above_low_skirt`;
    a box cover's 12 cm band, Rens 8 Oct 2026). Without them (an older pattern.json): the skirt
    pieces' hems, as before. `skip`: pieces that never get one (the inner walls, only with
    `features.vent_inner_walls` off; ADR-109)."""
    warnings: list[str] = []
    need = (
        _p(params, "features.vent_above_hem_mm")
        + _p(params, "features.vent_min_height_mm")
        + _p(params, "stitching.allowance_mm")
    )
    height = {p["name"]: float(np.ptp(np.asarray(p["outline_mm"])[:, 1])) for p in panels}
    edges = [e for p in panels for e in p["edges"]]
    has_z = bool(edges) and all("z_mm" in e for e in edges)
    out: dict[str, list[HemRun]] = {}
    low: dict[str, float] = {}  # skirt too low for a vent -> the height of its top
    if not has_z:
        for r in _hem_runs(panels, [n for n in skirt_order(panels) if n not in skip]):
            if height.get(r.panel, 0.0) >= need:
                out.setdefault(r.panel, []).append(r)
            else:
                low[r.panel] = 0.0
    else:
        hems = [e["z_mm"][0] for e in edges if e["kind"] == "hem"]
        lowest = min(hems) if hems else 0.0
        reach = _p(params, "features.vent_min_height_mm")  # higher than this is no bottom hem
        for p in panels:
            name = p["name"]
            if name in skip:
                continue
            outline = np.asarray(p["outline_mm"], dtype=np.float64)
            runs = [_run(outline, e, name, "hem") for e in p["edges"]
                    if e["kind"] == "hem" and e["z_mm"][1] <= lowest + reach]  # fmt: skip
            if not runs:
                continue
            top = max(e["z_mm"][1] for e in p["edges"])
            if name.startswith("skirt") and top - lowest < need:
                low[name] = top
                continue
            out[name] = runs
        if params["features.vent_above_low_skirt"]:
            for p in panels:
                name = p["name"]
                if name in skip or name in out or name in low:
                    continue
                outline = np.asarray(p["outline_mm"], dtype=np.float64)
                runs = [_run(outline, e, name, "above") for e in p["edges"]
                        if e["kind"] == "seam" and e.get("mate") in low
                        and e["z_mm"][1] <= low[e["mate"]] + reach]  # fmt: skip
                if runs:
                    out[name] = runs
            # the low skirts handed their vents up; one that found no piece above is warned
            served = {e.get("mate") for p in panels if p["name"] in out for e in p["edges"]}
            low = {k: v for k, v in low.items() if k not in served}
    for name in sorted(low):
        side = side_of(name).removeprefix("skirt-") or "skirt"
        warnings.append(
            f"no air vent on the {side}: the skirt there is lower than {need / MM_PER_CM:.1f} cm"
        )
    return out, warnings


def _explicit(
    text: str, bases: dict[str, list[HemRun]]
) -> tuple[list[tuple[str, float]], list[str]]:
    """`features.vent_positions`: "piece@fraction, ..." -> (piece, mm along its bottom edge)."""
    out, warnings = [], []
    for item in (x.strip() for x in text.split(",")):
        if not item:
            continue
        name, _, frac = item.partition("@")
        name = name.strip()
        try:
            at = float(frac) if frac.strip() else 0.5  # param-ok: no fraction: the middle
        except ValueError:
            warnings.append(f"vent_positions: {item!r} is not piece@fraction")
            continue
        if name not in bases:
            warnings.append(f"vent_positions: {name} has no bottom edge for a vent")
            continue
        total = sum(r.length for r in bases[name])
        out.append((name, float(np.clip(at, 0.0, 1.0)) * total))
    return out, warnings


def _sides(names: list[str], panels: list[dict[str, Any]], same: Any) -> list[list[str]]:
    """Pieces that join and face the same way are one side of the cover (for one per metre)."""
    parent = {n: n for n in names}

    def root(n: str) -> str:
        while parent[n] != n:
            n = parent[n]
        return n

    for p in panels:
        if p["name"] not in parent:
            continue
        for e in p["edges"]:
            m = e.get("mate")
            if e["kind"] == "seam" and m in parent and same(p["name"], m):
                parent[root(m)] = root(p["name"])
    groups: dict[str, list[str]] = {}
    for n in names:
        groups.setdefault(root(n), []).append(n)
    return list(groups.values())


def place_vents(
    panels: list[dict[str, Any]],
    params: EffectiveParams,
    walls: frozenset[str] | Walls = frozenset(),
) -> tuple[dict[str, list[Array]], list[str]]:
    """Vent openings per piece (rectangles in the piece's coordinates), and warnings.

    `walls`: `vent_walls` (or only the set of inner pieces). The rule (ADR-101, Rens 8 Oct 2026):
    every side of the cover gets vents, the seen front too, one in the middle of each piece
    first, a side not served yet before one that is; the drawing's number
    (`features.vents_total`) is kept, the extra ones go to the longest pieces; without a number,
    one per full metre of each side. All at one height (`features.vent_align`). Per model,
    `features.vent_positions` places them by hand."""
    if isinstance(walls, frozenset):
        walls = Walls(inner=walls)
    warnings: list[str] = []
    skip = frozenset() if params["features.vent_inner_walls"] else walls.inner
    bases, base_warnings = vent_bases(panels, params, skip)
    warnings += base_warnings
    w = _p(params, "features.vent_width_mm")
    allowance = _p(params, "stitching.allowance_mm")
    # a piece whose bottom edge is too short for a vent hands it on (the count is kept)
    room = {}
    for name, runs in bases.items():
        longest = max(r.length for r in runs)
        if longest - w >= 2 * allowance:
            room[name] = runs
        else:
            warnings.append(
                f"no room for an air vent on {name}: {longest / MM_PER_CM:.0f} cm "
                f"of hem, a vent needs {(w + 2 * allowance) / MM_PER_CM:g} cm"
            )
    lengths = {n: sum(r.length for r in runs) for n, runs in room.items()}
    cos = math.cos(math.radians(_p(params, "features.vent_wall_angle_deg")))

    def same(a: str, b: str) -> bool:
        fa, fb = walls.facing.get(a), walls.facing.get(b)
        if fa is None or fb is None:
            return side_of(a) == side_of(b)
        return fa[0] * fb[0] + fa[1] * fb[1] >= cos

    places: list[tuple[str, float]] = []
    text = str(params["features.vent_positions"]).strip()
    if text:
        places, more = _explicit(text, room)
        warnings += more
    elif lengths:
        if int(params["features.vents_total"]) > 0:
            counts = per_side(lengths, params, same)
        else:
            counts = {}
            for side in _sides(sorted(lengths), panels, same):
                n = vent_count(sum(lengths[k] for k in side), params)
                counts.update(_spread(side, lengths, n, same))
        for name in sorted(counts, key=lambda k: (-lengths[k], k)):
            k = counts[name]
            places += [(name, (j + 0.5) * lengths[name] / k) for j in range(k)]  # param-ok: middles
    by_name = {p["name"]: p for p in panels}
    out: dict[str, list[Array]] = {}
    for k, (name, s_at) in enumerate(places, start=1):
        acc = 0.0
        runs = room[name]
        for r in runs:
            if s_at <= acc + r.length or r is runs[-1]:
                rect, problem = _vent_at(by_name[name], r, s_at - acc, params, k)
                if problem:
                    warnings.append(problem)
                if rect is not None:
                    out.setdefault(name, []).append(rect)
                break
            acc += r.length
    return out, warnings


def _vent_at(
    panel: dict[str, Any], r: HemRun, local: float, params: EffectiveParams, k: int
) -> tuple[Array | None, str]:
    """One vent opening on `panel`, `local` mm along its bottom run `r`."""
    w = _p(params, "features.vent_width_mm")
    full_h = _p(params, "features.vent_height_mm")
    above = _p(params, "features.vent_above_hem_mm")
    clear = _p(params, "features.vent_seam_clearance_mm")
    allowance = _p(params, "stitching.allowance_mm")
    least_h = _p(params, "features.vent_min_height_mm")
    # a short piece still gets its vent (owner, 1 Oct 2026): centred, as far from the seams
    # as it can be, at least the seam allowance
    gap = clear if r.length >= w + 2 * clear else (r.length - w) / 2
    if gap < allowance:
        return None, (
            f"no room for air vent {k} on {r.panel}: {r.length / MM_PER_CM:.0f} cm "
            f"of hem, a vent needs {(w + 2 * allowance) / MM_PER_CM:g} cm"
        )
    local = float(np.clip(local, w / 2 + gap, r.length - w / 2 - gap))
    centre, t = _point_along(r.points, local)
    up = np.array([-t[1], t[0]])  # into the panel (counter-clockwise outline)
    poly = shapely.Polygon(np.asarray(panel["outline_mm"]))
    # the height of the piece where the vent goes (a sloping piece is lower at one end), over
    # the vent's whole width
    tall = _height_at(poly, centre, t, up, w)
    room_h = tall - above - allowance
    h = min(full_h, math.floor(room_h / MM_PER_CM) * MM_PER_CM)  # whole cm
    if h < least_h:
        return None, f"no air vent {k} on {r.panel}: only {tall / MM_PER_CM:.1f} cm high there"
    # where on the skirt's height (owner 30 Sep: 5 cm above the hem; a drawing's "at Top")
    lift = above
    align = params["features.vent_align"]
    if r.kind == "hem" and align == "top":
        lift = max(above, tall - _p(params, "features.vent_below_top_mm") - h)
    elif r.kind == "hem" and align == "middle":
        lift = max(above, (tall - h) / 2)
    rect = _opening(centre + up * lift, t, up, w, h)
    # a curved or sloping piece: lower the opening a cm at a time until it fits
    while not _fits(poly, rect, allowance) and h - MM_PER_CM >= least_h:
        h -= MM_PER_CM
        rect = _opening(centre + up * lift, t, up, w, h)
    if not _fits(poly, rect, allowance):
        return rect, (
            f"air vent {k} does not fit in {r.panel}, even {least_h / MM_PER_CM:g} cm high: "
            "the piece is too low or too curved there"
        )
    return rect, ""


def _vent_pieces(count: int, params: EffectiveParams, start: int) -> list[Piece]:
    if count == 0:
        return []
    w = _p(params, "features.vent_width_mm")
    h = _p(params, "features.vent_height_mm")
    a = _p(params, "stitching.allowance_mm")
    depth = _p(params, "features.vent_hood_depth_mm")
    label = _p(params, "pen.label_height_mm")

    def rect(name: str, i: int, width: float, height: float, note: str) -> Piece:
        cut = np.array([[0.0, 0.0], [width, 0.0], [width, height], [0.0, height]])
        return Piece(
            id=f"P{i}",
            name=name,
            quantity=count,
            cut=cut,
            net=None,
            pen_text=[(f"P{i} {name.upper()}", np.array([width / 2, height / 2]), label)],
            note=note,
        )

    def with_logo(piece: Piece, width: float, height: float) -> Piece:
        """Every air vent carries the logo (owner, 1 Oct 2026): its place on the hood, in pen."""
        lw, lh = (
            _p(params, "features.vent_logo_width_mm"),
            _p(params, "features.vent_logo_height_mm"),
        )
        cx, cy = width / 2, height - a - depth / 2 - lh / 2  # on the front of the hood
        box = np.array([[cx - lw / 2, cy], [cx + lw / 2, cy], [cx + lw / 2, cy + lh],
                        [cx - lw / 2, cy + lh], [cx - lw / 2, cy]])  # fmt: skip
        piece.pen_lines.append(box)
        piece.pen_text.append(("LOGO", np.array([cx, cy + lh / 2]), label * 0.8))
        piece.pen_text[0] = (piece.pen_text[0][0], np.array([width / 2, a + label]), label)
        piece.note = "vent hood with the logo; holds the plastic insert"
        return piece

    return [
        with_logo(
            rect(
                "vent-hood",
                start,
                w + 2 * a,
                h + depth + a,
                "vent hood, holds the plastic insert (to confirm)",
            ),
            w + 2 * a,
            h + depth + a,
        )
        if params["features.vent_logo"]
        else rect(
            "vent-hood",
            start,
            w + 2 * a,
            h + depth + a,
            "vent hood, holds the plastic insert (to confirm)",
        ),
        rect(
            "vent-membrane",
            start + 1,
            w + 2 * a,
            h + 2 * a,
            "vent membrane, against dirt (to confirm)",
        ),
    ]


def finish(
    doc: dict[str, Any], params: EffectiveParams, inner: frozenset[str] | Walls = frozenset()
) -> tuple[list[Piece], list[str]]:
    """Finished pieces from a PatternSet (`pattern.json`); `inner`: `vent_walls`, see
    `place_vents`."""
    warnings: list[str] = []
    panels = doc["panels"]
    ids = {p["name"]: p["id"] for p in panels}
    label = _p(params, "pen.label_height_mm")
    welded = params["construction.method"] == "welded"
    overlap = _p(params, "welding.overlap_mm")
    vents, vent_warnings = place_vents(panels, params, inner)
    warnings += vent_warnings
    revision = f"{doc['model_id']} r{doc['parameter_hash'][:6]}"  # param-ok: short revision id
    pieces: list[Piece] = []
    for p in panels:
        outline = np.asarray(p["outline_mm"], dtype=np.float64)
        n = len(outline)
        edges = p["edges"]
        distances = [allowance_of(e, p["name"], params) for e in edges]
        cut = cut_outline(outline, edges, distances)
        piece = Piece(p["id"], p["name"], int(p["quantity"]), cut, outline)
        poly = shapely.Polygon(outline)
        for e, d in zip(edges, distances, strict=True):
            pts = outline[edge_indices(n, e["range"])]
            info = {k: e[k] for k in ("kind", "seam", "mate", "lap_side") if k in e}
            info["allowance_mm"] = d
            info["length_mm"] = e["length_2d_mm"]
            piece.edges.append(info)
            if d > 0:  # the stitch line, or the hem fold line
                piece.pen_lines.append(pts)
            if e["kind"] == "hem" and d > 0 and params["hem.type"] == "drawcord_channel":
                # the bottom drawcord (owner, 1 Oct 2026: every cover): say what the fold is
                mid = pts[len(pts) // 2]
                piece.pen_text.append(
                    (f"HEM {d / MM_PER_CM:g} CM: BOTTOM CORD CHANNEL", mid + [0.0, label],
                     label * 0.6)
                )  # fmt: skip
            if welded and e["kind"] == "seam" and d == 0 and params["welding.guide_line"]:
                guide = inward_line(pts, poly, overlap)
                if guide is not None:
                    piece.pen_lines.append(guide)
        for m in p["pen"]:
            at = np.asarray(m["at"], dtype=np.float64)
            if m["type"] == "label":
                piece.pen_text.append((f"{p['id']} {m['text']}", at, label))
                piece.pen_text.append((revision, at - [0.0, 1.5 * label], label * 0.6))
            elif m["type"] == "seam_label":
                mate = m["text"].removeprefix("TO ").lower()
                ref = ids.get(mate, "")
                piece.pen_text.append(
                    (f"TO {ref} {mate.upper()}".replace("  ", " "), at, label * 0.6)
                )
            elif m["type"] == "arrow_up":
                length = float(m["length"])
                tip = at + [0.0, length]
                head = length / 4
                piece.pen_lines.append(np.array([at, tip]))
                piece.pen_lines.append(np.array([tip + [-head, -head], tip, tip + [head, -head]]))
            elif m["type"] == "tick":
                end = at + np.asarray(m["dir"]) * float(m["length"])
                piece.pen_lines.append(np.array([at, end]))
            elif m["type"] == "fold":  # one piece folded here instead of a seam (ADR-055)
                line = np.asarray(m["points"], dtype=np.float64)
                piece.pen_lines.append(line)
                piece.pen_text.append(("FOLD", line.mean(axis=0), label * 0.6))
        for rect in vents.get(p["name"], []):
            piece.openings.append(rect)
            # where the hood's edge goes: the opening grown by the seam allowance
            ring = shapely.Polygon(rect).buffer(
                _p(params, "stitching.allowance_mm"), join_style="mitre"
            )
            piece.pen_lines.append(np.asarray(ring.exterior.coords, dtype=np.float64))
        pieces.append(piece)
    _cord_exits(pieces, panels, params)
    if params["features.middle_cord"]:
        warnings += _middle_cord(pieces, panels, params)
    total_vents = sum(len(v) for v in vents.values())
    pieces += _vent_pieces(total_vents, params, len(panels) + 1)
    for pc in pieces:
        if not shapely.Polygon(pc.cut).is_valid:
            warnings.append(f"piece {pc.name}: the cut outline crosses itself")
    return pieces, warnings


def _middle_cord(
    pieces: list[Piece], panels: list[dict[str, Any]], params: EffectiveParams
) -> list[str]:
    """Table covers (owner, 1 Oct 2026): a second drawcord halfway up the cover, all round. A
    pen line on every side piece, the same height above the hem everywhere, where the channel
    is stitched in."""
    label = _p(params, "pen.label_height_mm")
    sides = [p for p in panels if p["name"].startswith("skirt")]
    heights = [float(np.ptp(np.asarray(p["outline_mm"])[:, 1])) for p in sides]
    if not heights:
        return ["no side pieces for the middle drawcord"]
    up = min(heights) / 2  # halfway up the lowest side, level all round
    by_name = {pc.name: pc for pc in pieces}
    for p in sides:
        outline = np.asarray(p["outline_mm"], dtype=np.float64)
        poly = shapely.Polygon(outline)
        for e in p["edges"]:
            if e["kind"] != "hem":
                continue
            pts = outline[edge_indices(len(outline), e["range"])]
            line = inward_line(pts, poly, up)
            if line is None:
                continue
            clipped = poly.intersection(shapely.LineString(line))
            for g in getattr(clipped, "geoms", [clipped]):
                if g.length > 0:
                    by_name[p["name"]].pen_lines.append(np.asarray(g.coords, dtype=np.float64))
            mid = line[len(line) // 2]
            by_name[p["name"]].pen_text.append(
                (f"MIDDLE CORD {up / MM_PER_CM:.1f} CM UP", mid + [0.0, label], label * 0.6)
            )
    return []


def _cord_exits(pieces: list[Piece], panels: list[dict[str, Any]], params: EffectiveParams) -> None:
    """Pen marks where the hem cord comes out, spread evenly round the hem."""
    exits = int(params["hem.cord_exits"])
    if exits <= 0 or params["hem.type"] == "plain":
        return
    runs = _hem_runs(panels, skirt_order(panels))
    total = sum(r.length for r in runs)
    if total <= 0:
        return
    by_name = {pc.name: pc for pc in pieces}
    mark = MARK_LENGTH * _p(params, "pen.label_height_mm")
    for k in range(exits):
        s = (k + 1) * total / exits  # half way between the vents
        s %= total
        acc = 0.0
        for r in runs:
            if s <= acc + r.length:
                at, t = _point_along(r.points, s - acc)
                up = np.array([-t[1], t[0]])
                pc = by_name[r.panel]
                pc.pen_lines.append(np.array([at - up * mark, at + up * mark]))
                pc.pen_text.append(("CORD", at + up * (mark * 1.2), mark / 2))
                break
            acc += r.length


def finished_set(
    doc: dict[str, Any], pieces: list[Piece], warnings: list[str], params: EffectiveParams
) -> dict[str, Any]:
    def pts(a: Array) -> list[list[float]]:
        return [[round(float(x), 2), round(float(y), 2)] for x, y in a]

    return {
        "format_version": FORMAT_VERSION,
        "engine_version": __version__,
        "model_id": doc["model_id"],
        "pattern_parameter_hash": doc["parameter_hash"],
        "parameter_hash": params.hash(),
        "construction": params["construction.method"],
        "pieces": [
            {
                "id": pc.id,
                "name": pc.name,
                "quantity": pc.quantity,
                "cut_mm": pts(pc.cut),
                "net_mm": pts(pc.net) if pc.net is not None else None,
                "openings_mm": [pts(o) for o in pc.openings],
                "edges": pc.edges,
                "size_mm": [round(float(v), 1) for v in np.ptp(pc.cut, axis=0)],
                "area_m2": round(shapely.Polygon(pc.cut).area / 1e6, 4),
                "note": pc.note,
            }
            for pc in pieces
        ],
        "warnings": warnings,
    }


def narrow_size(cut: Array) -> tuple[float, float]:
    """Width in the narrowest orientation and the length across it."""
    hull = np.asarray(shapely.MultiPoint(cut).convex_hull.exterior.coords)[:-1]
    best = (math.inf, 0.0)
    for a, b in zip(hull, np.roll(hull, -1, axis=0), strict=True):
        d = b - a
        norm = float(np.linalg.norm(d))
        if norm == 0:
            continue
        d = d / norm
        across = float(np.ptp((hull - a) @ np.array([-d[1], d[0]])))
        if across < best[0]:
            best = (across, float(np.ptp((hull - a) @ d)))
    return best
