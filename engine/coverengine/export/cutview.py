"""The cutting file as the studio shows it (ADR-147): cut.dxf read back and drawn as SVG.

The studio's "Cutting file" view must show exactly what the cutting table gets, so it is drawn
from the DXF's own bytes, never from cut.svg or finished.json. Every entity of the modelspace is
read (blocks exploded), sorted by layer into CUT, PEN and other, and drawn; an entity this
renderer cannot draw is counted in `skipped`, never silently left out.

Pieces are found in the file itself: every closed CUT ring that is not inside another is a
piece's outline, a ring inside it one of its openings (the vents), and the PEN lines and texts
inside it are its marks. Its name is the label the export writes ("P3 SKIRT-BACK", the largest
"P<n> ..." text inside it). Its edges run from corner to corner of the outline, a corner being
a turn of more than `desk.preview_corner_deg`.

`render` returns the SVG (y down, millimetres, 0.1 mm) and the meta the viewer needs (the sheet,
each piece's name, box, corners and edge lengths; no outline). `watermarked` adds the visible
"PREVIEW – NOT FOR CUTTING" across the drawing. `compare` says what changed between two
renderings, piece by piece (added, removed, size, outline, pen only), from the private geometry
kept with each rendering on the server (`GEOMETRY`), which the API never sends.
"""

from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import escape

import ezdxf
import numpy as np
import shapely
from ezdxf import path as dxfpath
from numpy.typing import NDArray

from coverengine.export.strokefont import text_width

Array = NDArray[np.float64]

VERSION = 1  # param-ok: the renderer's version, part of the cache key
WATERMARK = "PREVIEW – NOT FOR CUTTING"
GEOMETRY = "_geometry"  # the meta's private part: outlines for compare(), never sent
PAD_MM = 20.0  # param-ok: the drawing's margin
CAP_TO_FONT = 1.4  # param-ok: a DXF text height is its capital height; an SVG font-size is larger
# $INSUNITS → millimetres (0 unitless and R12 files: millimetres, as our export writes them)
UNITS_MM = {0: 1.0, 1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0}  # param-ok: unit conversion
LABEL = re.compile(r"^P\d+\b")
# the export's revision stamp ("<model> r<hash>", finish.py): it changes with every parameter
# hash, so compare() does not count it as a change of the piece's marks
STAMP = re.compile(r"^\S+ r[0-9a-f]{6}$")
TEXT_TYPES = ("TEXT", "MTEXT", "ATTRIB")


@dataclass
class Line:
    kind: str  # cut | pen | other
    points: Array  # n x 2, sheet millimetres, y up
    closed: bool


@dataclass
class Text:
    kind: str
    text: str
    at: tuple[float, float]  # the anchor, y up
    height: float
    rotation: float  # degrees, counter-clockwise
    anchor: str  # start | middle | end
    baseline: str  # alphabetic | middle | hanging | text-after-edge
    fit: float | None  # the stroke font's width of a left-aligned TEXT (the export's layout)


@dataclass
class Drawing:
    lines: list[Line] = field(default_factory=list)
    texts: list[Text] = field(default_factory=list)
    skipped: Counter[str] = field(default_factory=Counter)
    layers: dict[str, str] = field(default_factory=dict)  # file layer → cut | pen | other
    unit_mm: float = 1.0


def fingerprint(data: bytes) -> str:
    """As coverapi.desk.file_fingerprint: what a Desk approval records (ADR-120)."""
    return hashlib.sha256(data).hexdigest()[:20]  # param-ok: the Desk's fingerprint length


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _kind(layer: str, cut_layer: str, pen_layer: str) -> str:
    if layer.upper() == cut_layer.upper():
        return "cut"
    if layer.upper() == pen_layer.upper():
        return "pen"
    return "other"


def _text(e: Any, kind: str, scale: float) -> Text | None:
    t = e.dxftype()
    if t == "MTEXT":
        content = e.plain_text().replace("\n", " ").strip()
        at = e.dxf.insert
        height = float(e.dxf.char_height)
        rot = float(e.get_rotation())
        attach = int(e.dxf.get("attachment_point", 1))
        anchor = ("start", "middle", "end")[(attach - 1) % 3]
        baseline = ("hanging", "middle", "text-after-edge")[(attach - 1) // 3]
        fit = None
    else:
        content = str(e.dxf.text)
        halign, valign = int(e.dxf.get("halign", 0)), int(e.dxf.get("valign", 0))
        left = halign == 0 and valign == 0
        at = e.dxf.insert if left or not e.dxf.hasattr("align_point") else e.dxf.align_point
        height = float(e.dxf.height)
        rot = float(e.dxf.get("rotation", 0.0))
        anchor = {1: "middle", 2: "end", 4: "middle"}.get(halign, "start")
        baseline = {1: "text-after-edge", 2: "middle", 3: "hanging"}.get(valign, "alphabetic")
        if halign == 4:  # MIDDLE: centred both ways
            baseline = "middle"
        fit = text_width(content, height) * scale if left else None
    if not content:
        return None
    return Text(kind, content, (float(at.x) * scale, float(at.y) * scale), height * scale, rot,
                anchor, baseline, fit)  # fmt: skip


def _walk(entities: Any, out: Drawing, cut_layer: str, pen_layer: str, flat: float,
          depth: int = 0) -> None:  # fmt: skip
    s = out.unit_mm
    for e in entities:
        t = e.dxftype()
        layer = str(e.dxf.get("layer", "0"))
        kind = _kind(layer, cut_layer, pen_layer)
        out.layers.setdefault(layer, kind)
        if t == "INSERT" and depth < 8:  # param-ok: nesting depth guard
            try:
                _walk(e.virtual_entities(), out, cut_layer, pen_layer, flat, depth + 1)
            except Exception:  # noqa: BLE001 - a broken block is counted, not fatal
                out.skipped[t] += 1
            continue
        if t in TEXT_TYPES:
            item = _text(e, kind, s)
            if item is not None:
                out.texts.append(item)
            continue
        if t == "POINT":
            p = e.dxf.location
            out.lines.append(Line(kind, np.array([[p.x * s, p.y * s]] * 2), False))
            continue
        try:
            p = dxfpath.make_path(e)
        except (TypeError, ValueError):
            out.skipped[t] += 1
            continue
        for sub in p.sub_paths() if p.has_sub_paths else [p]:
            pts = np.array([(v.x, v.y) for v in sub.flattening(flat / s)], dtype=np.float64)
            if len(pts) == 0:
                continue
            if len(pts) == 1:
                pts = np.vstack([pts, pts])
            closed = bool(sub.is_closed) or (
                len(pts) > 2 and bool(np.allclose(pts[0], pts[-1]))  # param-ok: a ring
            )
            if closed and np.allclose(pts[0], pts[-1]) and len(pts) > 1:
                pts = pts[:-1]
            out.lines.append(Line(kind, pts * s, closed and len(pts) >= 3))  # param-ok: a ring


def read(data: bytes, cut_layer: str, pen_layer: str, flatten_mm: float) -> Drawing:
    """Every modelspace entity of a DXF, in millimetres."""
    doc = ezdxf.read(io.StringIO(_decode(data)))
    out = Drawing()
    units = int(doc.header.get("$INSUNITS", 0))
    out.unit_mm = UNITS_MM.get(units, 1.0)
    _walk(doc.modelspace(), out, cut_layer, pen_layer, flatten_mm)
    return out


@dataclass
class Piece:
    outer: int  # index in Drawing.lines
    polygon: Any
    openings: list[int] = field(default_factory=list)
    pen: list[int] = field(default_factory=list)
    texts: list[int] = field(default_factory=list)
    name: str = ""


def find_pieces(dr: Drawing) -> tuple[list[Piece], list[int]]:
    """Closed CUT rings nested by containment: even depth a piece, odd depth an opening of the
    ring around it. Returns the pieces and the CUT lines that belong to none (open ones)."""
    rings = [i for i, ln in enumerate(dr.lines) if ln.kind == "cut" and ln.closed]
    polys = {}
    for i in rings:
        poly = shapely.make_valid(shapely.Polygon(dr.lines[i].points))
        polys[i] = poly if not poly.is_empty else shapely.Polygon(dr.lines[i].points).buffer(0)
    order = sorted(rings, key=lambda i: -float(polys[i].area))
    tree = shapely.STRtree([polys[i] for i in order])
    parent: dict[int, int | None] = {}
    depth: dict[int, int] = {}
    for k, i in enumerate(order):
        rep = shapely.Point(dr.lines[i].points[0])
        best: int | None = None
        for j in tree.query(rep):
            other = order[int(j)]
            if other == i or int(j) > k:
                continue  # only larger (earlier) rings can hold this one
            if polys[other].covers(rep) and polys[other].area > polys[i].area:
                if best is None or polys[other].area < polys[best].area:
                    best = other
        parent[i] = best
        depth[i] = 0 if best is None else depth[best] + 1
    pieces: dict[int, Piece] = {}
    for i in order:
        if depth[i] % 2 == 0:
            pieces[i] = Piece(i, polys[i])
        else:
            holder = parent[i]
            assert holder is not None
            pieces[holder].openings.append(i)
    ordered = sorted(pieces.values(), key=lambda p: p.outer)  # the file's order
    loose = [i for i, ln in enumerate(dr.lines) if ln.kind == "cut" and not ln.closed]
    if ordered:
        pen = [i for i, ln in enumerate(dr.lines) if ln.kind != "cut"]
        _assign(ordered, pen, [dr.lines[i].points[len(dr.lines[i].points) // 2] for i in pen],
                "pen")  # fmt: skip
        _assign(ordered, list(range(len(dr.texts))), [_text_point(t) for t in dr.texts], "texts")
        _labels_outside(dr, ordered)
    for n, pc in enumerate(ordered):
        pc.name = _name(dr, pc) or f"#{n + 1}"
    return ordered, loose


def _text_point(t: Text) -> tuple[float, float]:
    """Where a text lies, for finding its piece: the middle of a left-aligned one."""
    if t.anchor == "start" and not t.rotation:
        width = t.fit if t.fit else t.height * len(t.text) * 0.6  # param-ok: average advance
        return t.at[0] + width / 2, t.at[1] + t.height / 2
    return t.at


def _assign(pieces: list[Piece], items: list[int], points: list[Any], attr: str) -> None:
    """Each item to the smallest piece whose outline holds its point (pieces never overlap on
    the sheet, but be safe), vectorised: a big cover has thousands of PEN lines."""
    if not items:
        return
    xy = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    free = np.ones(len(items), dtype=bool)
    for pc in sorted(pieces, key=lambda p: float(p.polygon.area)):
        x0, y0, x1, y1 = pc.polygon.bounds
        box = free & (xy[:, 0] >= x0) & (xy[:, 0] <= x1) & (xy[:, 1] >= y0) & (xy[:, 1] <= y1)
        if not box.any():
            continue
        cand = np.flatnonzero(box)
        hit = cand[shapely.intersects_xy(pc.polygon, xy[cand, 0], xy[cand, 1])]
        getattr(pc, attr).extend(items[k] for k in hit)
        free[hit] = False
    for pc in pieces:
        getattr(pc, attr).sort()


def _labels_outside(dr: Drawing, pieces: list[Piece]) -> None:
    """A piece's label lies at its middle, which for a thin or bent piece can fall just outside
    its outline: such a label goes to the nearest piece without one, when that piece is clearly
    the nearest (less than half as far as the next)."""
    taken = {i for pc in pieces for i in pc.texts}
    for i, t in enumerate(dr.texts):
        if i in taken or not LABEL.match(t.text):
            continue
        pt = shapely.Point(_text_point(t))
        dist = sorted((float(pc.polygon.distance(pt)), k) for k, pc in enumerate(pieces))
        near = pieces[dist[0][1]]
        clear = len(dist) == 1 or dist[0][0] * 2 < dist[1][0]
        if clear and not any(LABEL.match(dr.texts[j].text) for j in near.texts):
            near.texts.append(i)
            near.texts.sort()


def _name(dr: Drawing, pc: Piece) -> str:
    texts = [dr.texts[i] for i in pc.texts]
    labels = [t for t in texts if LABEL.match(t.text)]
    pick = labels or [t for t in texts if not STAMP.match(t.text)]
    if not pick:
        return ""
    return max(pick, key=lambda t: t.height).text.strip()


def corners(ring: Array, corner_deg: float) -> list[int]:
    """Indices of the vertices where the closed ring turns more than corner_deg."""
    n = len(ring)
    if n < 3:  # param-ok: a ring
        return []
    prev = ring - np.roll(ring, 1, axis=0)
    nxt = np.roll(ring, -1, axis=0) - ring
    a = np.arctan2(prev[:, 1], prev[:, 0])
    b = np.arctan2(nxt[:, 1], nxt[:, 0])
    turn = np.abs((b - a + np.pi) % (2 * np.pi) - np.pi)
    ok = (np.linalg.norm(prev, axis=1) > 0) & (np.linalg.norm(nxt, axis=1) > 0)
    return [int(i) for i in np.flatnonzero(ok & (turn > math.radians(corner_deg)))]


def edges(ring: Array, corner_deg: float, min_edge_mm: float) -> list[dict[str, Any]]:
    """The outline from corner to corner: each edge's length along the outline (mm), its two
    corners and the point halfway along it, in sheet millimetres (y up). An edge shorter than
    min_edge_mm (a seam allowance's cut-off corner, a step of a curve) is joined to the shorter
    of its neighbours, so the list names the sides a person measures; the lengths still add up
    to the whole outline."""
    n = len(ring)
    seg = np.linalg.norm(np.roll(ring, -1, axis=0) - ring, axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(cum[-1])
    cs = corners(ring, corner_deg) or [0]

    def span(s: int, e: int) -> float:
        d = float(cum[e] - cum[s])
        return d if d > 0 else d + total

    while len(cs) > 3:  # param-ok: a piece keeps at least three sides
        lens = [span(cs[k], cs[(k + 1) % len(cs)]) for k in range(len(cs))]
        k = int(np.argmin(lens))
        if lens[k] >= min_edge_mm:
            break
        prev, nxt = lens[k - 1], lens[(k + 1) % len(cs)]
        del cs[k if prev <= nxt else (k + 1) % len(cs)]
    out = []
    for k, s in enumerate(cs):
        e = cs[(k + 1) % len(cs)]
        length = span(s, e) if len(cs) > 1 else total
        at = (float(cum[s]) + length / 2) % total if total > 0 else 0.0
        j = min(int(np.searchsorted(cum, at, side="right")) - 1, n - 1)
        f = (at - float(cum[j])) / float(seg[j]) if seg[j] > 0 else 0.0
        mid = ring[j] + f * (ring[(j + 1) % n] - ring[j])
        out.append({"length_mm": round(length, 1), "a": ring[s], "b": ring[e], "mid": mid})
    return out


def _num(v: float) -> str:
    s = f"{v:.1f}"
    return "0" if s in ("-0.0", "0.0") else s.rstrip("0").rstrip(".")


class _Frame:
    """Sheet millimetres (y up) → the SVG's (y down, a margin round the drawing)."""

    def __init__(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.x0, self.y1 = x0 - PAD_MM, y1 + PAD_MM
        self.w, self.h = (x1 - x0) + 2 * PAD_MM, (y1 - y0) + 2 * PAD_MM

    def pt(self, p: Any) -> tuple[float, float]:
        return round(float(p[0]) - self.x0, 1), round(self.y1 - float(p[1]), 1)

    def d(self, pts: Array, closed: bool) -> str:
        xy = np.column_stack([pts[:, 0] - self.x0, self.y1 - pts[:, 1]]).round(1)
        head = f"M{_num(xy[0, 0])} {_num(xy[0, 1])}"
        rel = np.diff(xy, axis=0).round(1)
        body = "l" + " ".join(f"{_num(dx)} {_num(dy)}" for dx, dy in rel) if len(rel) else ""
        return head + body + ("z" if closed else "")


def _bounds(dr: Drawing) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for ln in dr.lines:
        xs += [float(ln.points[:, 0].min()), float(ln.points[:, 0].max())]
        ys += [float(ln.points[:, 1].min()), float(ln.points[:, 1].max())]
    for t in dr.texts:
        xs += [t.at[0], t.at[0] + (t.fit or t.height)]
        ys += [t.at[1], t.at[1] + t.height]
    if not xs:
        return 0.0, 0.0, 1.0, 1.0
    return min(xs), min(ys), max(xs), max(ys)


def _local(points: Array, origin: Array) -> list[list[float]]:
    return (points - origin).round(1).tolist()  # type: ignore[no-any-return]


def render(data: bytes, cut_layer: str, pen_layer: str, flatten_mm: float, corner_deg: float,
           min_edge_mm: float) -> tuple[str, dict[str, Any]]:  # fmt: skip
    """The SVG (without watermark) and the meta of a cut.dxf's bytes."""
    dr = read(data, cut_layer, pen_layer, flatten_mm)
    pieces, loose = find_pieces(dr)
    fr = _Frame(*_bounds(dr))
    owner = {}
    for n, pc in enumerate(pieces):
        for i in [pc.outer, *pc.openings, *pc.pen]:
            owner[i] = n
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" class="cv-sheet" '
        f'viewBox="0 0 {_num(fr.w)} {_num(fr.h)}" width="{_num(fr.w)}mm" height="{_num(fr.h)}mm" '
        f'data-fingerprint="{fingerprint(data)}">',
        "<!--WATERMARK-TITLE-->",
        '<g class="cv-cut" fill="none" stroke="#d40000" stroke-width="1" '
        'vector-effect="non-scaling-stroke">',
    ]
    for n, pc in enumerate(pieces):
        rings = [pc.outer, *pc.openings]
        d = " ".join(fr.d(dr.lines[i].points, True) for i in rings)
        out.append(f'<path class="cv-piece" data-piece="{n}" fill-rule="evenodd" '
                   f'vector-effect="non-scaling-stroke" d="{d}"/>')  # fmt: skip
    for i, ln in enumerate(dr.lines):
        if ln.kind == "cut" and i not in owner:
            out.append(f'<path class="cv-loose" vector-effect="non-scaling-stroke" '
                       f'd="{fr.d(ln.points, ln.closed)}"/>')  # fmt: skip
    out.append("</g>")
    for kind, colour in (("pen", "#0047d4"), ("other", "#7a7a7a")):
        out.append(f'<g class="cv-{kind}" fill="none" stroke="{colour}" stroke-width="0.8" '
                   f'vector-effect="non-scaling-stroke">')  # fmt: skip
        groups: dict[int | None, list[str]] = {}
        for i, ln in enumerate(dr.lines):
            if ln.kind == kind:
                groups.setdefault(owner.get(i), []).append(fr.d(ln.points, ln.closed))
        for holder, ds in groups.items():
            attr = f' data-piece="{holder}"' if holder is not None else ""
            out.append(f'<path{attr} vector-effect="non-scaling-stroke" d="{" ".join(ds)}"/>')
        out.append("</g>")
    text_owner = {i: n for n, pc in enumerate(pieces) for i in pc.texts}
    out.append('<g class="cv-text" fill="#0047d4" stroke="none" '
               'font-family="Arial, Helvetica, sans-serif">')  # fmt: skip
    for i, t in enumerate(dr.texts):
        x, y = fr.pt(t.at)
        attrs = [f'x="{_num(x)}"', f'y="{_num(y)}"', f'font-size="{_num(t.height * CAP_TO_FONT)}"']
        if t.kind != "pen":
            attrs.append(f'class="cv-text-{t.kind}"')
        if t.anchor != "start":
            attrs.append(f'text-anchor="{t.anchor}"')
        if t.baseline != "alphabetic":
            attrs.append(f'dominant-baseline="{t.baseline}"')
        if t.fit:
            attrs.append(f'textLength="{_num(t.fit)}" lengthAdjust="spacingAndGlyphs"')
        if t.rotation:
            attrs.append(f'transform="rotate({_num(-t.rotation)} {_num(x)} {_num(y)})"')
        if i in text_owner:
            attrs.append(f'data-piece="{text_owner[i]}"')
        out.append(f"<text {' '.join(attrs)}>{escape(t.text)}</text>")
    out.append("</g>")
    out.append("<!--WATERMARK-->")
    out.append("</svg>")
    meta_pieces = []
    geometry = []
    for n, pc in enumerate(pieces):
        ring = dr.lines[pc.outer].points
        lo, hi = ring.min(axis=0), ring.max(axis=0)
        es = edges(ring, corner_deg, min_edge_mm)
        meta_pieces.append({
            "index": n,
            "name": pc.name,
            "size_mm": [round(float(hi[0] - lo[0]), 1), round(float(hi[1] - lo[1]), 1)],
            "box": [*fr.pt((lo[0], hi[1])), *fr.pt((hi[0], lo[1]))],  # x0 y0 x1 y1, y down
            "centre": list(fr.pt((lo + hi) / 2)),
            "area_m2": round(float(pc.polygon.area) / 1e6, 4),  # param-ok: mm² → m²
            "perimeter_mm": round(sum(e["length_mm"] for e in es), 1),
            "openings": len(pc.openings),
            "edges": [{"length_mm": e["length_mm"], "a": list(fr.pt(e["a"])),
                       "b": list(fr.pt(e["b"])), "mid": list(fr.pt(e["mid"]))}
                      for e in es],  # fmt: skip
            "texts": sorted(dr.texts[i].text for i in pc.texts),
        })  # fmt: skip
        geometry.append({
            "outer": _local(ring, lo),
            "openings": [_local(dr.lines[i].points, lo) for i in pc.openings],
            "pen": [_local(dr.lines[i].points, lo) for i in pc.pen],
            "pen_texts": sorted(
                [dr.texts[i].text, *(np.round(np.array(dr.texts[i].at) - lo, 0).tolist())]
                for i in pc.texts if not STAMP.match(dr.texts[i].text)
            ),
        })  # fmt: skip
    counts = Counter(ln.kind for ln in dr.lines)
    meta = {
        "version": VERSION,
        "fingerprint": fingerprint(data),
        "sheet_mm": [round(fr.w, 1), round(fr.h, 1)],
        "pad_mm": PAD_MM,
        "layers": {
            "cut": counts.get("cut", 0),
            "pen": counts.get("pen", 0),
            "other": counts.get("other", 0),
            "texts": sum(1 for t in dr.texts if t.kind == "pen"),
            "names": sorted(dr.layers),
        },
        "loose_cut": len(loose),
        "skipped": dict(sorted(dr.skipped.items())),
        "pieces": meta_pieces,
        GEOMETRY: geometry,
    }
    return "\n".join(out) + "\n", meta


def public(meta: dict[str, Any]) -> dict[str, Any]:
    """The meta without the private geometry."""
    return {k: v for k, v in meta.items() if not k.startswith("_")}


def watermarked(svg: str, meta: dict[str, Any], note: str = "") -> str:
    """The rendering with "PREVIEW – NOT FOR CUTTING" drawn across it and in its title. The
    words are part of the drawing (not a page overlay), so a saved SVG or a screenshot keeps
    them."""
    w, h = meta["sheet_mm"]
    size = _wm_size(w, h)
    text_w = size * 0.62 * len(WATERMARK)  # param-ok: a sans-serif's average advance
    step_x, step_y = text_w * 1.25, size * 5  # param-ok: layout of the watermark
    marks = []
    y = size * 3
    row = 0
    while y < h + size:
        x = -text_w / 3 if row % 2 else 0.0  # param-ok: rows offset
        while x < w:
            turn = f"rotate(-18 {_num(x + text_w / 2)} {_num(y)})"  # param-ok: the slant
            marks.append(f'<text x="{_num(x)}" y="{_num(y)}" transform="{turn}">'
                         f"{escape(WATERMARK)}</text>")  # fmt: skip
            x += step_x
        y += step_y
        row += 1
    band = band_mm(meta)
    label = f"{WATERMARK}{' · ' + note if note else ''}"
    wm = (
        f'<g class="cv-watermark" pointer-events="none" font-family="Arial, Helvetica, '
        f'sans-serif" font-weight="700">'
        f'<g fill="#c00000" fill-opacity="0.16" font-size="{_num(size)}">{"".join(marks)}</g>'
        f'<rect x="0" y="{_num(-band)}" width="{_num(w)}" height="{_num(band)}" fill="#c00000"/>'
        f'<text x="{_num(w / 2)}" y="{_num(-band * 0.32)}" text-anchor="middle" fill="#ffffff" '
        f'font-size="{_num(size * 0.9)}">{escape(label)}</text></g>'
    )
    title = f"<title>{escape(WATERMARK)}</title><desc>{escape(note)}</desc>"
    # the band goes above the drawing (the viewBox grows upwards), so it hides no piece; the
    # meta's coordinates stay as they are
    head = f'viewBox="0 0 {_num(w)} {_num(h)}" width="{_num(w)}mm" height="{_num(h)}mm"'
    grown = (f'viewBox="0 {_num(-band)} {_num(w)} {_num(h + band)}" width="{_num(w)}mm" '
             f'height="{_num(h + band)}mm" data-watermark="1"')  # fmt: skip
    out = svg.replace(head, grown, 1)
    return out.replace("<!--WATERMARK-TITLE-->", title, 1).replace("<!--WATERMARK-->", wm, 1)


def band_mm(meta: dict[str, Any]) -> float:
    """How far the watermark's band reaches above the drawing (the viewBox's new top)."""
    w, h = meta["sheet_mm"]
    return float(_num(_wm_size(w, h) * 1.6))  # param-ok: layout of the watermark


def _wm_size(w: float, h: float) -> float:
    return max(30.0, min(250.0, min(w, h) / 12))  # param-ok: layout of the watermark


def clean(svg: str) -> str:
    """The rendering of an approved cut file: no watermark."""
    return svg.replace("<!--WATERMARK-TITLE-->\n", "", 1).replace("<!--WATERMARK-->\n", "", 1)


def _hausdorff(a: Any, b: Any) -> float:
    if a.is_empty and b.is_empty:
        return 0.0
    if a.is_empty or b.is_empty:
        return math.inf
    return float(shapely.hausdorff_distance(a, b))


def _lines(rings: list[list[list[float]]], closed: bool) -> Any:
    parts = []
    for r in rings:
        pts = r + r[:1] if closed and r else r
        if len(pts) >= 2:  # param-ok: a line
            parts.append(shapely.LineString(pts))
    return shapely.MultiLineString(parts) if parts else shapely.MultiLineString()


def compare(a: dict[str, Any], b: dict[str, Any], tol_mm: float) -> dict[str, Any]:
    """What changed from rendering a (older) to b (newer), piece by piece, matched by name (and
    copy). Status per piece: added, removed, size (its box changed by more than tol_mm),
    outline (same box, the outline or its openings moved more than tol_mm), pen (the cut is the
    same, its PEN marks or texts changed: a pen-only change, as the vent logo of ADR-146), same.
    The export's revision stamp is not a change."""

    def by_name(m: dict[str, Any]) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {}
        for p in m["pieces"]:
            out.setdefault(p["name"], []).append(p["index"])
        return out

    na, nb = by_name(a), by_name(b)
    ga, gb = a[GEOMETRY], b[GEOMETRY]
    rows = []
    names = list(dict.fromkeys([*nb, *na]))
    for name in names:
        ia, ib = na.get(name, []), nb.get(name, [])
        for k in range(max(len(ia), len(ib))):
            pa = a["pieces"][ia[k]] if k < len(ia) else None
            pb = b["pieces"][ib[k]] if k < len(ib) else None
            row: dict[str, Any] = {"name": name, "a": pa and pa["index"], "b": pb and pb["index"],
                                   "before_mm": pa and pa["size_mm"],
                                   "after_mm": pb and pb["size_mm"]}  # fmt: skip
            if pa is None or pb is None:
                row["status"] = "added" if pa is None else "removed"
                rows.append(row)
                continue
            ea, eb = ga[pa["index"]], gb[pb["index"]]
            dw = max(abs(x - y) for x, y in zip(pa["size_mm"], pb["size_mm"], strict=True))
            outline = max(
                _hausdorff(_lines([ea["outer"]], True), _lines([eb["outer"]], True)),
                _hausdorff(_lines(ea["openings"], True), _lines(eb["openings"], True)),
            )
            pen = _hausdorff(_lines(ea["pen"], False), _lines(eb["pen"], False))
            ta = Counter(t[0] for t in ea["pen_texts"])
            tb = Counter(t[0] for t in eb["pen_texts"])
            moved = sorted(set(map(tuple, map(_round_text, ea["pen_texts"])))
                           ^ set(map(tuple, map(_round_text, eb["pen_texts"]))))  # fmt: skip
            row["texts_added"] = sorted((tb - ta).elements())
            row["texts_removed"] = sorted((ta - tb).elements())
            row["openings"] = [pa["openings"], pb["openings"]]
            if dw > tol_mm:
                row["status"] = "size"
            elif outline > tol_mm or pa["openings"] != pb["openings"]:
                row["status"] = "outline"
            elif pen > tol_mm or moved:
                row["status"] = "pen"
            else:
                row["status"] = "same"
            row["moved_mm"] = round(min(max(outline, 0.0), 1e6), 1)  # param-ok: display cap
            rows.append(row)
    counts = Counter(r["status"] for r in rows)
    cut_same = all(r["status"] in ("same", "pen") for r in rows)
    return {
        "a": a["fingerprint"],
        "b": b["fingerprint"],
        "same_file": a["fingerprint"] == b["fingerprint"],
        "pieces": rows,
        "counts": {
            s: counts.get(s, 0) for s in ("added", "removed", "size", "outline", "pen", "same")
        },  # fmt: skip
        "cut_same": cut_same,
        "pen_only": cut_same and counts.get("pen", 0) > 0,
        "tolerance_mm": tol_mm,
    }


def _round_text(t: list[Any]) -> list[Any]:
    """A pen text with its place rounded to whole centimetres, for "moved"."""
    return [t[0], *(round(float(v) / 10) for v in t[1:])]  # param-ok: mm → cm
