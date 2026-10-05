"""The drawing's views, read by the program itself (ADR-075).

Every view on the workshop's drawings is a picture the CAD program rendered of the cover, with
a transparency mask: the mask is the exact silhouette of the cover seen from that side. This
module turns each picture into a polygon on the page (in points), sorts the views (a 3D view;
orthographic views: the plan seen from above and elevations from the front or the side) and
finds the drawing's scale from the sizes written on it: the scale at which the most written
sizes are lengths of the silhouettes.

The cover's solid is built from these views in coverengine/drawing_solid.py.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

CM = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(cm|in|\"|”)?", re.I)
IN_CM = 2.54
SIMPLIFY_PX = 1.2  # param-ok: silhouette smoothing in picture pixels
ISO_DEG = 30.0  # param-ok: an isometric view draws horizontal edges at ±30°
ISO_SHARE = 0.25  # param-ok: a view with this share of its outline at ±30° is a 3D view
SCALE_TOL = 0.012  # param-ok: two scales agree within 1.2 %
MATCH_TOL = 0.015  # param-ok: a written size matches a length within 1.5 % (or 1 cm)
MIN_SHARE = 0.12  # param-ok: an outline piece shorter than this share of its view is no size
SCALE_RANGE = (0.1, 3.0)  # param-ok: cm per point; the sheets draw covers 50-500 cm on A4


@dataclass
class View:
    page: int
    rect: tuple[float, float, float, float]  # x0, y0, x1, y1 on the page, points, y down
    outline: np.ndarray  # the silhouette, page points, y UP (x right)
    kind: str = "ortho"  # "iso" | "plan" | "front" | "side" | "ortho"
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def size(self) -> tuple[float, float]:
        lo, hi = self.outline.min(axis=0), self.outline.max(axis=0)
        return float(hi[0] - lo[0]), float(hi[1] - lo[1])


def _silhouette(mask: np.ndarray) -> np.ndarray | None:
    """The largest outline of the mask, in picture pixels (x right, y down)."""
    import shapely
    from skimage import measure

    padded = np.pad(mask.astype(np.float64), 1)
    contours = measure.find_contours(padded, 0.5)  # param-ok: the mask's edge
    if not contours:
        return None
    best = max(contours, key=lambda c: shapely.Polygon(c).area if len(c) > 3 else 0.0)
    poly = shapely.Polygon(best[:, ::-1] - 1).simplify(SIMPLIFY_PX)  # (row, col) -> (x, y)
    if poly.is_empty or poly.geom_type != "Polygon":
        return None
    return np.asarray(poly.exterior.coords)[:-1]


def views(pdf: Path) -> list[View]:
    """Every rendered view with a transparency mask, as a silhouette on its page."""
    import pymupdf

    doc = pymupdf.open(pdf)
    out = []
    for pn, page in enumerate(doc.pages()):
        for im in page.get_images(full=True):
            xref, smask = im[0], im[1]
            if not smask:
                continue
            m = pymupdf.Pixmap(doc, smask)
            mask = np.frombuffer(m.samples, dtype=np.uint8).reshape(m.height, m.width, m.n)[..., 0]
            px = _silhouette(mask > 127)  # param-ok: half of the 8-bit mask
            if px is None:
                continue
            for r in page.get_image_rects(xref):
                sx, sy = r.width / m.width, r.height / m.height
                pts = np.column_stack([r.x0 + px[:, 0] * sx, -(r.y0 + px[:, 1] * sy)])
                out.append(View(pn, (r.x0, r.y0, r.x1, r.y1), pts))
    if out:  # a logo in the order table is no view: much smaller than the views
        big = max(_area(v) for v in out)
        out = [v for v in out if _area(v) >= MIN_VIEW_SHARE * big]
    for v in out:
        v.kind = "iso" if _iso_share(v.outline) >= ISO_SHARE else "ortho"
        v.meta["iso_share"] = round(_iso_share(v.outline), 3)
    return out


MIN_VIEW_SHARE = 0.08  # param-ok: a picture smaller than this share of the largest is no view


def _area(v: View) -> float:
    return (v.rect[2] - v.rect[0]) * (v.rect[3] - v.rect[1])


def _iso_share(outline: np.ndarray) -> float:
    """The share of the outline's length running at ±30° (the receding edges of a 3D view)."""
    d = np.roll(outline, -1, axis=0) - outline
    length = np.hypot(d[:, 0], d[:, 1])
    ang = np.degrees(np.arctan2(d[:, 1], d[:, 0])) % 180
    near = (np.abs(ang - ISO_DEG) < 4) | (np.abs(ang - (180 - ISO_DEG)) < 4)  # param-ok: deg
    return float(length[near].sum() / max(length.sum(), 1e-9))


def written_cm(pdf: Path) -> list[float]:
    """Every size written on the drawing, in cm: values with cm, inch values converted when no
    cm value is written beside them (the drawings write "[45.0cm] 17.7in" or only inches)."""
    import pymupdf

    out: list[float] = []
    for page in pymupdf.open(pdf).pages():
        k = _bare_factor(page.get_text())
        for b in page.get_text("blocks"):
            text = b[4]
            if re.search(r"order number|product number|fabric type", text, re.I):
                continue
            vals = [(float(v.replace(",", ".")), (u or "").lower()) for v, u in CM.findall(text)]
            cms = [v for v, u in vals if u == "cm"]
            inch = [v * IN_CM for v, u in vals if u in ("in", '"', "”")]
            bare = [v for v, u in vals if not u]
            if cms:
                out += cms
            elif inch:
                out += inch
            else:
                out += [v * k for v in bare if v >= 5]  # param-ok: a bare number is a size
    return sorted({round(v, 1) for v in out if v > 0})


def lengths_pt(v: View) -> list[float]:
    """The lengths a size on this view can measure: its width and height, and its straight
    outline pieces (merged where they run on in the same direction)."""
    w, h = v.size
    out = [w, h, float(np.hypot(*np.diff(np.vstack([v.outline, v.outline[:1]]), axis=0).T).sum())]
    least = MIN_SHARE * max(w, h)
    d = np.roll(v.outline, -1, axis=0) - v.outline
    seg = np.hypot(d[:, 0], d[:, 1])
    ang = np.arctan2(d[:, 1], d[:, 0])
    run, last = 0.0, None
    for s, a in zip(seg, ang, strict=True):
        if last is not None and abs(math.remainder(a - last, 2 * math.pi)) < math.radians(3):
            run += s
        else:
            if run >= least:
                out.append(run)
            run = s
        last = a
    if run >= least:
        out.append(run)
    return out


def scale(views_: list[View], sizes_cm: list[float]) -> tuple[float, int]:
    """cm per point: the scale at which most written sizes are lengths of the orthographic
    views (all of them drawn at one scale). Returns the scale and how many sizes it explains."""
    ortho = [v for v in views_ if v.kind != "iso"]
    lens = [x for v in ortho for x in lengths_pt(v)]
    if not lens or not sizes_cm:
        return 0.0, 0
    lo, hi = SCALE_RANGE
    cands = sorted(c / x for c in sizes_cm for x in lens if x > 0 and lo <= c / x <= hi)
    best, n_best = 0.0, 0
    for s in cands:
        n = sum(1 for c in sizes_cm if any(abs(x * s - c) <= max(1.0, MATCH_TOL * c) for x in lens))
        if n > n_best or (n == n_best and best and s < best):
            best, n_best = s, n
    return best, n_best


def sort_views(views_: list[View], s: float) -> None:
    """Name the orthographic views. An elevation stands on the ground: its bottom is one straight
    line across its whole width (the hem, open at the bottom). The plan is the other one. An
    elevation as wide as the plan is the front; as wide as the plan is deep, the side."""
    ortho = [v for v in views_ if v.kind != "iso"]
    for v in ortho:
        v.meta["flat_bottom"] = _flat_bottom(v)
    plans = [v for v in ortho if not v.meta["flat_bottom"]]
    elev = [v for v in ortho if v.meta["flat_bottom"]]
    if not plans and len(elev) >= 2:  # a rectangular plan also has a flat bottom edge
        plans = [max(elev, key=lambda v: v.size[1] / max(v.size[0], 1e-9))]
        elev = [v for v in elev if v is not plans[0]]
    for v in plans:
        v.kind = "plan"
    if not plans:
        for v in elev:
            v.kind = "front"
        return
    pk = float(plans[0].meta.get("scale", s))
    pw, pd = plans[0].size[0] * pk, plans[0].size[1] * pk
    for v in elev:
        w = v.size[0] * float(v.meta.get("scale", s))
        v.kind = "front" if abs(w - pw) <= abs(w - pd) else "side"


def _flat_bottom(v: View) -> bool:
    lo = v.outline[:, 1].min()
    w = v.size[0]
    near = v.outline[np.abs(v.outline[:, 1] - lo) < max(0.6, 0.004 * w)]  # param-ok: pt
    return bool(len(near) >= 2 and np.ptp(near[:, 0]) >= 0.9 * w)  # param-ok: across 90 %


ARROW_MAX_PT = 9.0  # param-ok: an arrowhead is a small filled triangle
TEXT_REACH_PT = 30.0  # param-ok: a size's text sits this close to its dimension line
COLLINEAR = 0.05  # param-ok: radians off the line between the two tips


@dataclass
class Dimension:
    page: int
    a: np.ndarray  # arrow tips, page points, y up
    b: np.ndarray
    value_cm: float
    text: str

    @property
    def length_pt(self) -> float:
        return float(np.linalg.norm(self.b - self.a))


def _arrows(page: Any) -> list[tuple[np.ndarray, np.ndarray]]:
    """Every filled arrowhead on the page: (tip, unit direction it points), y up."""
    out = []
    for d in page.get_drawings():
        if d.get("fill") is None:  # one filled path may hold many arrowheads
            continue
        pts: list[tuple[float, float]] = []
        for it in d["items"]:
            if it[0] != "l":
                pts = []
                continue
            p, q = (it[1].x, -it[1].y), (it[2].x, -it[2].y)
            if not pts:
                pts = [p, q]
            elif math.dist(pts[-1], p) < 1e-3:
                pts.append(q)
            else:
                pts = [p, q]
            tri = _triangle(pts)
            if tri is not None:
                out.append(tri)
                pts = []
    return out


def _triangle(pts: list[tuple[float, float]]) -> tuple[np.ndarray, np.ndarray] | None:
    uniq: list[tuple[float, float]] = []
    for p in pts:
        if all(math.dist(p, u) > 1e-3 for u in uniq):
            uniq.append(p)
    if len(uniq) != 3:  # param-ok: a triangle
        return None
    t = np.array(uniq)
    if np.ptp(t, axis=0).max() > ARROW_MAX_PT:
        return None

    # the tip has the sharpest corner
    def corner(i: int) -> float:
        a, b, c = t[i], t[(i + 1) % 3], t[(i + 2) % 3]
        u, v = b - a, c - a
        return float(np.arccos(np.clip(u @ v / (np.linalg.norm(u) * np.linalg.norm(v)), -1, 1)))

    i = min(range(3), key=corner)
    tip = t[i]
    base = (t[(i + 1) % 3] + t[(i + 2) % 3]) / 2
    d = tip - base
    n = np.linalg.norm(d)
    return (tip, d / n) if n > 1e-6 else None


INCHES_NOTE = re.compile(r"dimensions\s+are\s+in\s+inch", re.I)


def _bare_factor(text: str) -> float:
    """A bare number is cm, unless the sheet says all dimensions are in inches (C8)."""
    return IN_CM if INCHES_NOTE.search(text) else 1.0


def _size_texts(page: Any) -> list[tuple[np.ndarray, float, str, np.ndarray]]:
    """Text blocks holding one size: (centre, cm, text). cm wins; inches when only inches."""
    out = []
    k = _bare_factor(page.get_text())
    for b in page.get_text("blocks"):
        text = b[4]
        vals = [(float(v.replace(",", ".")), (u or "").lower()) for v, u in CM.findall(text)]
        cms = [v for v, u in vals if u == "cm"]
        inch = [v * IN_CM for v, u in vals if u in ("in", '"', "”")]
        bare = [v * k for v, u in vals if not u and v >= 5]  # param-ok: a bare size
        val = cms[0] if cms else (inch[0] if inch else (bare[0] if len(bare) == 1 else None))
        if val:
            half = np.array([(b[2] - b[0]) / 2, (b[3] - b[1]) / 2])
            out.append((np.array([(b[0] + b[2]) / 2, -(b[1] + b[3]) / 2]), val, text.strip(), half))
    return out


def dimensions(pdf: Path) -> list[Dimension]:
    """Straight dimensions: two arrowheads on one line pointing away from each other (or
    towards each other), with the size written beside the line."""
    import pymupdf

    out = []
    for pn, page in enumerate(pymupdf.open(pdf).pages()):
        arrows = _arrows(page)
        texts = _size_texts(page)
        used: set[int] = set()
        pairs = []
        for i, (ta, da) in enumerate(arrows):
            for j in range(i + 1, len(arrows)):
                tb, db = arrows[j]
                ab = tb - ta
                dist = float(np.linalg.norm(ab))
                if dist < 2 * ARROW_MAX_PT:
                    continue
                u = ab / dist
                if da @ db > -math.cos(COLLINEAR) or abs(abs(da @ u) - 1) > COLLINEAR:
                    continue
                pairs.append((dist, i, j))
        for dist, i, j in sorted(pairs):  # the nearest partner first
            if i in used or j in used:
                continue
            ta, tb = arrows[i][0], arrows[j][0]
            u = (tb - ta) / dist
            n = np.array([-u[1], u[0]])
            best = None
            for c, val, text, half in texts:
                along = (c - ta) @ u
                off = max(0.0, abs((c - ta) @ n) - abs(half @ np.abs(n)))  # from the text's edge
                if -TEXT_REACH_PT <= along <= dist + TEXT_REACH_PT and off <= TEXT_REACH_PT:
                    if best is None or off < best[0]:
                        best = (off, val, text)
            if best is None:
                continue
            used |= {i, j}
            out.append(Dimension(pn, ta, tb, best[1], best[2]))
    return out


ISO_VERTICAL = math.sqrt(2.0 / 3.0)  # param-ok: an isometric view shortens verticals to 0.816


def _near(v: View, d: Dimension) -> float:
    """How far a dimension's middle is from a view's picture (points; 0 inside)."""
    m = (d.a + d.b) / 2
    x0, y0, x1, y1 = v.rect
    dx = max(x0 - m[0], 0.0, m[0] - x1)
    dy = max(y0 - (-m[1]), 0.0, -m[1] - y1)
    return math.hypot(dx, dy)


def read(pdf: Path) -> dict[str, Any]:
    """The views, their kinds, the dimensions and the scale (cm per point), all read from the
    drawing's own lines.

    - The 3D view: its outline runs at ±30°; when curves hide that, the largest picture (the
      workshop's sheets always draw the 3D view largest).
    - Each dimension belongs to the nearest view. On an orthographic view it gives the scale
      directly; on the 3D view one along an axis (upright or at ±30°) gives it times 0.816.
    - The scale is the median of all of them; the spread is reported.
    """
    vs = views(pdf)
    if vs and not any(v.kind == "iso" for v in vs):  # one picture alone is the 3D view too
        max(vs, key=lambda v: (v.rect[2] - v.rect[0]) * (v.rect[3] - v.rect[1])).kind = "iso"
    dims = dimensions(pdf)
    est: dict[int, list[float]] = {}
    for d in dims:
        same = [v for v in vs if v.page == d.page]
        if not same or d.length_pt <= 0:
            continue
        v = min(same, key=lambda v: _near(v, d))
        r = d.value_cm / d.length_pt
        u = (d.b - d.a) / d.length_pt
        if v.kind == "iso":
            # along any of the three axes an isometric view shortens by the same 0.816:
            # upright, or at ±30° (the plan's two directions)
            ang = math.degrees(math.atan2(abs(u[1]), abs(u[0])))
            if abs(ang - 90) < 3 or abs(ang - ISO_DEG) < 3:  # param-ok: degrees
                est.setdefault(d.page, []).append(r * ISO_VERTICAL)
                v.meta.setdefault("dims", []).append(d.value_cm)
        else:
            est.setdefault(d.page, []).append(r)
            v.meta.setdefault("dims", []).append(d.value_cm)
    sizes = written_cm(pdf)
    # one scale per page (a second page is often drawn at another scale)
    page_scale: dict[int, float] = {}
    hows = []
    for pn, e in sorted(est.items()):
        m = float(np.median(e))
        agree = [x for x in e if abs(x / m - 1) <= SCALE_TOL] or [m]
        page_scale[pn] = float(np.mean(agree))
        hows.append(f"page {pn + 1}: {len(agree)} of {len(e)} dimensions agree")
    if not page_scale:
        s0, n = scale(vs, sizes)
        page_scale = {v.page: s0 for v in vs}
        hows.append(f"no dimension lines; {n} written sizes fit")
    first = next(iter(page_scale.values()))
    for v in vs:
        v.meta["scale"] = page_scale.get(v.page, first)
    s = first
    how = "; ".join(hows)
    sort_views(vs, s)
    return {"views": vs, "dimensions": dims, "scale_cm_per_pt": s, "scale_from": how,
            "sizes_cm": sizes}  # fmt: skip
