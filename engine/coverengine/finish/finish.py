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


def _roomy(runs: list[HemRun], s_at: float, need: float) -> float:
    """Where along a side a vent goes: `s_at`, unless the piece of hem there is too short for a
    vent (a narrow end piece, C27); then the nearest point on a piece long enough (so the count
    on the drawing is kept, owner 5 Oct 2026)."""
    acc, spans = 0.0, []
    for r in runs:
        spans.append((acc, acc + r.length, r.length >= need))
        acc += r.length
    for lo, hi, ok in spans:
        if lo <= s_at <= hi and ok:
            return s_at
    roomy = [(lo, hi) for lo, hi, ok in spans if ok]
    if not roomy:
        return s_at  # nowhere roomier: warned as before
    lo, hi = min(roomy, key=lambda sp: min(abs(s_at - sp[0]), abs(s_at - sp[1])))
    return float(np.clip(s_at, lo + need / 2, hi - need / 2))


def per_side(lengths: dict[str, float], params: EffectiveParams) -> dict[str, int]:
    """Vents per side of the cover: one per full metre of that side, at least one (owner, 1 Oct
    2026: each side separately; 2.10 m: 2, 2.90 m: 2, 3.10 m: 3, 1.40 m: 1). A number written
    on the drawing (`features.vents_total`) always wins: spread over the sides by length."""
    total = int(params["features.vents_total"])
    if total <= 0 or not lengths:
        return {k: vent_count(v, params) for k, v in lengths.items()}
    # the drawing's own number (owner, 5 Oct 2026): spread by length, largest remainder first
    whole = sum(lengths.values()) or 1.0
    exact = {k: total * v / whole for k, v in lengths.items()}
    out = {k: int(x) for k, x in exact.items()}
    for k in sorted(exact, key=lambda k: (out[k] - exact[k], k))[: total - sum(out.values())]:
        out[k] += 1
    return out


@dataclass
class HemRun:
    panel: str
    points: Array  # along the hem, in the panel's own coordinates
    length: float


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


def place_vents(
    panels: list[dict[str, Any]], params: EffectiveParams
) -> tuple[dict[str, list[Array]], list[str]]:
    """Vent openings per skirt panel (rectangles in the panel's coordinates), and warnings."""
    warnings: list[str] = []
    order = skirt_order(panels)
    runs = _hem_runs(panels, order)
    # only on skirt pieces tall enough for a vent (a low front gives its vents to the sides)
    need = (
        _p(params, "features.vent_above_hem_mm")
        + _p(params, "features.vent_height_mm")
        + _p(params, "stitching.allowance_mm")
    )
    height = {p["name"]: float(np.ptp(np.asarray(p["outline_mm"])[:, 1])) for p in panels}
    # a low side gets a lower opening, same width, at least vent_min_height_mm (owner, 1 Oct
    # 2026); the plastic insert, the hood and the membrane stay the same size
    least = need - _p(params, "features.vent_height_mm") + _p(params, "features.vent_min_height_mm")
    tall = [r for r in runs if height.get(r.panel, 0.0) >= least]
    runs = tall  # a side lower than that gets no vent (warned below)
    total = sum(r.length for r in runs)
    out: dict[str, list[Array]] = {}
    # one per full metre of each side, at least one per side (owner, 1 Oct 2026)
    sides: dict[str, list[HemRun]] = {}
    for r in runs:
        sides.setdefault(side_of(r.panel), []).append(r)
    low = sorted({side_of(r.panel) for r in _hem_runs(panels, order)} - set(sides))
    for side in low:
        warnings.append(
            f"no air vent on the {side.removeprefix('skirt-') or 'skirt'}: the skirt there is "
            f"lower than {least / MM_PER_CM:.1f} cm"
        )
    if total <= 0:
        return out, warnings
    shares = per_side({k: sum(r.length for r in v) for k, v in sides.items()}, params)
    w = _p(params, "features.vent_width_mm")
    full_h = h = _p(params, "features.vent_height_mm")
    above = _p(params, "features.vent_above_hem_mm")
    clear = _p(params, "features.vent_seam_clearance_mm")
    allowance = _p(params, "stitching.allowance_mm")
    by_name = {p["name"]: p for p in panels}
    k = 0
    for side, side_runs in sides.items():
        side_total = sum(r.length for r in side_runs)
        n = shares[side]
        for j in range(n):
            k += 1
            s_at = (j + 0.5) * side_total / n  # param-ok: the middle of each share
            s_at = _roomy(side_runs, s_at, w + 2 * allowance)
            acc = 0.0
            for r in side_runs:
                if s_at <= acc + r.length or r is side_runs[-1]:
                    local = s_at - acc
                    # a short side still gets its vent (owner, 1 Oct 2026): centred, as far
                    # from the seams as it can be, at least the seam allowance
                    gap = clear if r.length >= w + 2 * clear else (r.length - w) / 2
                    lo, hi = w / 2 + gap, r.length - w / 2 - gap
                    if gap < allowance:
                        warnings.append(
                            f"no room for air vent {k} on {r.panel}: {r.length / MM_PER_CM:.0f} cm "
                            f"of hem, a vent needs {(w + 2 * allowance) / MM_PER_CM:g} cm"
                        )
                        break
                    local = float(np.clip(local, lo, hi))
                    centre, t = _point_along(r.points, local)
                    up = np.array([-t[1], t[0]])  # into the panel (counter-clockwise outline)
                    base = centre + up * above
                    poly = shapely.Polygon(np.asarray(by_name[r.panel]["outline_mm"]))
                    # the height of the piece where the vent goes (a sloping piece is lower at
                    # one end), over the vent's whole width
                    local = _height_at(poly, centre, t, up, w)
                    room_h = local - above - allowance
                    h = min(full_h, math.floor(room_h / MM_PER_CM) * MM_PER_CM)  # whole cm
                    if h < _p(params, "features.vent_min_height_mm"):
                        warnings.append(
                            f"no air vent {k} on {r.panel}: only {local / MM_PER_CM:.1f} cm high "
                            "there"
                        )
                        break
                    least_h = _p(params, "features.vent_min_height_mm")

                    # a curved or sloping piece: lower the opening a cm at a time until it fits
                    rect = _opening(base, t, up, w, h)
                    while not _fits(poly, rect, allowance) and h - MM_PER_CM >= least_h:
                        h -= MM_PER_CM
                        rect = _opening(base, t, up, w, h)
                    if not _fits(poly, rect, allowance):
                        warnings.append(
                            f"air vent {k} does not fit in {r.panel}, even "
                            f"{least_h / MM_PER_CM:g} cm high: the piece is too low or too "
                            "curved there"
                        )
                    out.setdefault(r.panel, []).append(rect)
                    break
                acc += r.length
    return out, warnings


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


def finish(doc: dict[str, Any], params: EffectiveParams) -> tuple[list[Piece], list[str]]:
    """Finished pieces from a PatternSet (`pattern.json`)."""
    warnings: list[str] = []
    panels = doc["panels"]
    ids = {p["name"]: p["id"] for p in panels}
    label = _p(params, "pen.label_height_mm")
    welded = params["construction.method"] == "welded"
    overlap = _p(params, "welding.overlap_mm")
    vents, vent_warnings = place_vents(panels, params)
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
