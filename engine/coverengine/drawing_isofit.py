"""Heights fitted to the drawing's 3D view (phase 4 of the drawings plan, ADR-091).

Many workshop drawings show a corner sofa's real shape only in the 3D view: the top view gives
the footprint (an L, a C, a V), but no elevation is drawn, so the views reader (drawing_solid)
can only stand the footprint straight up, a flat block. Its silhouette fits the 3D view well
(the back is the highest line), yet it is the wrong cover: the seat is lower than the back.

Here the footprint is kept and the heights over it are fitted:

1. **The shape family.** Over the footprint the top's height follows a profile from the back
   edge (the outside of the L, C or V): a flat strip along the back at the back height, a straight
   slope down to the front height at the arm's depth (the machinery of plan_profile, ADR-084).
   An arm may end in a hip: the end wall is lower and the top falls to it over a given length
   (C4, C8). The walls stand on the footprint up to the top.
2. **Only written sizes.** Every height, the strip, the end height and the hip's length is one of
   the sizes written on the drawing; nothing is guessed. The footprint's own lengths along the back
   and its depth must be written too.
3. **The 3D view decides.** Each candidate is drawn as the CAD program draws its 3D view, its
   silhouette and its creases (where two faces meet at an angle); the drawing's picture gives its
   silhouette (the mask) and its creases (where the shading changes). The candidate whose creases
   lie on the picture's and whose silhouette covers it best wins. It is only taken when its
   silhouette covers the 3D view at least `drawing.min_iou` (the same check as every reader).

Everything is deterministic and AI-free (route A). Sizes in cm as on the drawings, the surface
in mm, z up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from coverengine import drawing_views as dv
from coverengine.drawn import MM, Piece
from coverengine.errors import CoverError
from coverengine.params import EffectiveParams

ISO_ELEVATION = math.degrees(math.atan(1 / math.sqrt(2)))  # 35.26°: the isometric view
CORNERS_DEG = (45.0, 135.0, 225.0, 315.0)  # param-ok: the four corners an iso view is seen from
STEP_CM = 6.0  # param-ok: the top mesh, at most this coarse
FIT_STEP_CM = 20.0  # param-ok: ... and while fitting (a flat piece needs no fine mesh)
CUT_REACH_CM = 2000.0  # param-ok: a corner seam reaches right across the cover
SIMPLIFY_CM = 0.3  # param-ok: the footprint's outline, smoothed (as plan_profile)
CORNER_CM = 1.5  # param-ok: the footprint's corners, found on an outline smoothed this much
HULL_NEAR_CM = 2.0  # param-ok: a corner this close to the convex hull is on the outside
WALL_TURN_DEG = 20.0  # param-ok: the outline turning more than this is a corner between walls
PAD_PARTS = 8  # param-ok: the grid reaches past the picture by this part of its width
SLIVER_MM2 = 1.0  # param-ok: a triangle smaller than this (twice its area, mm²) is no face


def _params(params: EffectiveParams) -> dict[str, float]:
    keys = ("min_iou", "isofit_px", "isofit_crease_deg", "isofit_shade_step",
            "isofit_edge_px", "isofit_edge_weight", "isofit_trust_share", "isofit_size_tol",
            "isofit_height_min_cm", "isofit_height_max_cm", "isofit_strip_share",
            "isofit_hip_share", "isofit_end_share", "isofit_min_gain",
            "isofit_min_crease")  # fmt: skip
    return {k: float(params[f"drawing.{k}"]) for k in keys}  # type: ignore[arg-type]


# --- the picture -----------------------------------------------------------------------------


@dataclass
class Picture:
    """The 3D view's picture on a pixel grid: its mask, its creases, and how a point in cm (the
    sheet's scale, y up) lands on the grid."""

    mask: np.ndarray  # bool, rows x cols
    edges: np.ndarray  # bool: the silhouette and the shading's steps
    px_cm: float  # cm per pixel
    centroid: np.ndarray  # the mask's centre, pixels (col, row)
    pad: int
    far: np.ndarray  # each pixel's distance to the picture's nearest crease


def picture(pdf: Path, iso: dv.View, px: int, shade_step: float) -> Picture:
    """The iso view's own image (RGB and its transparency mask) on a grid `px` pixels wide."""
    import pymupdf
    from PIL import Image
    from scipy import ndimage

    doc = pymupdf.open(pdf)
    page = doc[iso.page]
    for im in page.get_images(full=True):
        xref, smask = im[0], im[1]
        if not smask:
            continue
        rects = page.get_image_rects(xref)
        if any(
            abs(r.x0 - iso.rect[0]) < 1 and abs(r.y0 - iso.rect[1]) < 1 for r in rects
        ):  # param-ok: pt
            break
    else:
        raise CoverError("the 3D view's picture was not found")
    rgb = pymupdf.Pixmap(doc, xref)
    if rgb.n != 3:  # param-ok: RGB
        rgb = pymupdf.Pixmap(pymupdf.csRGB, rgb)
    m = pymupdf.Pixmap(doc, smask)
    w0, h0 = m.width, m.height
    pt_w = iso.rect[2] - iso.rect[0]
    cols = int(px)
    rows = max(1, round(cols * (iso.rect[3] - iso.rect[1]) / pt_w))
    img = Image.frombytes("RGB", (rgb.width, rgb.height), rgb.samples).resize(
        (cols, rows), Image.Resampling.BOX
    )
    msk = Image.frombytes("L", (w0, h0), m.samples[:: m.n] if m.n > 1 else m.samples)
    msk = msk.resize((cols, rows), Image.Resampling.BOX)
    lum = np.asarray(img.convert("L"), dtype=np.float64)
    mask = np.asarray(msk, dtype=np.float64) > 127  # param-ok: half of the 8-bit mask
    lab, n = ndimage.label(mask)
    if n > 1:  # the cover is the largest blob (a stray strip of another picture is not)
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        mask = lab == (int(np.argmax(sizes)) + 1)
    step = np.hypot(ndimage.sobel(lum, 0), ndimage.sobel(lum, 1)) / 8.0  # param-ok: Sobel's sum
    inner = ndimage.binary_erosion(mask, iterations=2)
    edges = (inner & (step > shade_step)) | (mask & ~ndimage.binary_erosion(mask))
    k = float(iso.meta["scale"])
    px_cm = pt_w * k / cols
    pad = cols // PAD_PARTS
    mask, edges = np.pad(mask, pad), np.pad(edges, pad)
    rr, cc = np.nonzero(mask)
    far = ndimage.distance_transform_edt(~edges)
    return Picture(mask, edges, px_cm, np.array([cc.mean(), rr.mean()]), pad, far)


# --- drawing a candidate as the CAD program draws its 3D view ---------------------------------


def _camera(azimuth_deg: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    a, e = math.radians(azimuth_deg), math.radians(ISO_ELEVATION)
    right = np.array([math.cos(a), -math.sin(a), 0.0])
    up = np.array([math.sin(a) * math.sin(e), math.cos(a) * math.sin(e), math.cos(e)])
    return right, up, np.cross(right, up)


def render(verts_mm: np.ndarray, faces: np.ndarray, pic: Picture, azimuth: float,
           crease_deg: float) -> tuple[np.ndarray, np.ndarray]:  # fmt: skip
    """The candidate seen isometrically on the picture's grid, its centre on the picture's:
    (mask, creases). A crease: neighbouring pixels whose faces differ by more than
    `crease_deg`, or the silhouette."""
    from scipy import ndimage

    right, up, toward = _camera(azimuth)
    v = verts_mm / MM
    uv = np.column_stack([v @ right, -(v @ up)]) / pic.px_cm  # pixels, rows down
    depth = -(v @ toward)
    tri = v[faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    nl = np.linalg.norm(n, axis=1)
    ok = nl > 1e-9
    n[ok] /= nl[ok, None]
    rows, cols = pic.mask.shape
    # first on a grid centred on the picture's centre; then moved so the masks' centres meet
    off = np.array([cols / 2, rows / 2]) - (uv.min(axis=0) + uv.max(axis=0)) / 2
    fid = _raster(uv + off, depth, faces[ok], np.nonzero(ok)[0], rows, cols)
    mask = fid >= 0
    if not mask.any():
        return mask, mask
    rr, cc = np.nonzero(mask)
    shift = np.round(pic.centroid - np.array([cc.mean(), rr.mean()])).astype(int)
    mask = np.roll(mask, (shift[1], shift[0]), axis=(0, 1))
    fid = np.roll(fid, (shift[1], shift[0]), axis=(0, 1))
    nrm = np.where(mask[..., None], n[np.clip(fid, 0, None)], 0.0)
    cos = math.cos(math.radians(crease_deg))
    crease = np.zeros_like(mask)
    for ax in (0, 1):
        d = np.abs((nrm * np.roll(nrm, 1, axis=ax)).sum(axis=2))
        both = mask & np.roll(mask, 1, axis=ax)
        crease |= both & (d < cos)
    crease |= mask & ~ndimage.binary_erosion(mask)
    return mask, crease


def _raster(p: np.ndarray, depth: np.ndarray, faces: np.ndarray, ids: np.ndarray, rows: int,
            cols: int) -> np.ndarray:  # fmt: skip
    """Which face is seen at each pixel (-1: none): every triangle's pixels at once, grouped by
    the size of their box, the nearest face winning (a z-buffer)."""
    tri = p[faces]  # n x 3 x 2 (col, row)
    z = depth[faces]
    lo = np.floor(tri.min(axis=1)).astype(np.int64)
    span = np.ceil(tri.max(axis=1)).astype(np.int64) - lo + 1
    bw = 2 ** np.ceil(np.log2(np.maximum(span, 1))).astype(np.int64)
    pix_all, z_all, f_all = [], [], []
    for key in np.unique(bw, axis=0):
        sel = np.nonzero((bw == key).all(axis=1))[0]
        mx, my = np.meshgrid(np.arange(key[0]), np.arange(key[1]))
        gx, gy = mx.reshape(-1), my.reshape(-1)
        for chunk in np.array_split(
            sel, max(1, len(sel) * len(gx) // 4_000_000 + 1)
        ):  # param-ok: memory
            t = tri[chunk]
            x = lo[chunk, 0, None] + gx[None, :]
            y = lo[chunk, 1, None] + gy[None, :]
            a, b, c = t[:, 0], t[:, 1], t[:, 2]
            den = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (
                a[:, 1] - c[:, 1]
            )
            good = np.abs(den) > 1e-12
            den = np.where(good, den, 1.0)[:, None]
            w0 = ((b[:, 1, None] - c[:, 1, None]) * (x - c[:, 0, None])
                  + (c[:, 0, None] - b[:, 0, None]) * (y - c[:, 1, None])) / den  # fmt: skip
            w1 = ((c[:, 1, None] - a[:, 1, None]) * (x - c[:, 0, None])
                  + (a[:, 0, None] - c[:, 0, None]) * (y - c[:, 1, None])) / den  # fmt: skip
            w2 = 1 - w0 - w1
            eps = -1e-9
            inside = (w0 >= eps) & (w1 >= eps) & (w2 >= eps) & good[:, None]
            inside &= (x >= 0) & (x < cols) & (y >= 0) & (y < rows)
            zz = w0 * z[chunk, 0, None] + w1 * z[chunk, 1, None] + w2 * z[chunk, 2, None]
            pix_all.append((y * cols + x)[inside])
            z_all.append(zz[inside])
            f_all.append(np.broadcast_to(ids[chunk, None], x.shape)[inside])
    fid = np.full(rows * cols, -1, dtype=np.int64)
    if pix_all:
        pix, zs, fs = np.concatenate(pix_all), np.concatenate(z_all), np.concatenate(f_all)
        order = np.lexsort((fs, zs, pix))  # nearest first; the face's number breaks a tie
        pix, fs = pix[order], fs[order]
        first = np.ones(len(pix), dtype=bool)
        first[1:] = pix[1:] != pix[:-1]
        fid[pix[first]] = fs[first]
    return fid.reshape(rows, cols)


SHADE_RGB = (160, 165, 190)  # param-ok: the CAD program's grey-blue
SHADE_AMBIENT = 0.45  # param-ok: light everywhere; the rest from one lamp
LAMP = (0.3, 0.5, 1.0)  # param-ok: the lamp, (right, up, towards the viewer)
MARGIN_PX = 12  # param-ok: white round a shaded picture


def shaded(verts_mm: np.ndarray, faces: np.ndarray, azimuth: float, px_cm: float,
           crease_deg: float) -> tuple[np.ndarray, np.ndarray]:  # fmt: skip
    """A picture of the cover seen isometrically, shaded as a CAD program does (white round
    it, the creases drawn dark): (RGB, mask). For the comparison sheets and test drawings."""
    from scipy import ndimage

    right, up, toward = _camera(azimuth)
    v = verts_mm / MM
    uv = np.column_stack([v @ right, -(v @ up)]) / px_cm
    uv -= uv.min(axis=0) - MARGIN_PX
    cols, rows = (np.ceil(uv.max(axis=0)) + MARGIN_PX).astype(int)
    tri = v[faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    nl = np.linalg.norm(n, axis=1)
    ok = nl > 1e-9
    n[ok] /= nl[ok, None]
    n[(n @ toward) < 0] *= -1  # the side seen
    fid = _raster(uv, -(v @ toward), faces[ok], np.nonzero(ok)[0], int(rows), int(cols))
    mask = fid >= 0
    lamp = np.array(LAMP) / np.linalg.norm(LAMP)
    lit = SHADE_AMBIENT + (1 - SHADE_AMBIENT) * np.clip(
        n @ (lamp[0] * right + lamp[1] * up + lamp[2] * toward), 0, 1)  # fmt: skip
    img = np.full((int(rows), int(cols), 3), 255.0)
    img[mask] = lit[fid[mask], None] * np.array(SHADE_RGB)
    nrm = np.where(mask[..., None], n[np.clip(fid, 0, None)], 0.0)
    cos = math.cos(math.radians(crease_deg))
    crease = mask & ~ndimage.binary_erosion(mask)
    for ax in (0, 1):
        d = (nrm * np.roll(nrm, 1, axis=ax)).sum(axis=2)
        crease |= mask & np.roll(mask, 1, axis=ax) & (d < cos)
    img[crease] *= 0.35  # param-ok: a crease drawn dark
    return img.astype(np.uint8), mask


def score(
    mask: np.ndarray, crease: np.ndarray, pic: Picture, edge_px: float
) -> tuple[float, float]:
    """(IoU of the silhouettes, how well the creases lie on each other: an F-score in which a
    crease counts fully on the picture's and less the further it lies, nothing from `edge_px`)."""
    from scipy import ndimage

    iou = float((mask & pic.mask).sum() / max((mask | pic.mask).sum(), 1))
    if not crease.any() or not pic.edges.any():
        return iou, 0.0
    d_pic = pic.far
    d_mod = ndimage.distance_transform_edt(~crease)
    prec = float(np.clip(1 - d_pic[crease] / edge_px, 0, 1).mean())
    rec = float(np.clip(1 - d_mod[pic.edges] / edge_px, 0, 1).mean())
    f = 2 * prec * rec / max(prec + rec, 1e-9)
    return iou, f


# --- the footprint and the heights over it ------------------------------------------------------


@dataclass
class Footprint:
    """The cover seen from above (cm, the sheet's frame: x right, y towards the back)."""

    plan: Any  # shapely Polygon
    back: Any  # LineString: the outside of the L, C or V
    ends: list[Any]  # LineStrings: the arms' ends
    depth: float  # the arm's depth from the back edge
    back_cm: list[float]  # the lengths of the back edge's straight bits


@dataclass(frozen=True)
class Heights:
    back: float  # the back height
    front: float  # the front height, at the arm's depth
    strip: float = 0.0  # a flat strip along the back
    end: float | None = None  # an arm's end wall, lower: the top falls to it ...
    hip: float = 0.0  # ... over this length
    fall: float = 0.0  # the strip falls this much (cm) from the back to its front edge


def _corners(plan: Any) -> np.ndarray:
    return np.asarray(plan.simplify(CORNER_CM).exterior.coords)[:-1]


def footprints(plan: Any, end_share: float) -> list[Footprint]:
    """The ways the footprint can stand: its back edge is the longest run of corners on the
    convex hull, without the short bits at its two ends (the arms' ends: shorter than
    `end_share` of the longest bit). A footprint that is convex all round (a straight sofa)
    can have its back along any of its long sides."""
    import shapely

    pts = _corners(plan)
    n = len(pts)
    hull = plan.convex_hull.exterior
    on = np.array([hull.distance(shapely.Point(p)) < HULL_NEAR_CM for p in pts])
    runs: list[list[int]] = []
    if on.all():  # convex: each long side may be the back
        lens = [float(np.linalg.norm(pts[(i + 1) % n] - pts[i])) for i in range(n)]
        for i in range(n):
            if lens[i] >= end_share * max(lens):
                runs.append([(i - 1) % n, i, (i + 1) % n, (i + 2) % n])
    else:
        best: list[int] = []
        for start in range(n):
            if on[start] and not on[start - 1]:
                k = 0
                while on[(start + k) % n] and k < n:
                    k += 1
                if k > len(best):
                    best = [(start + i) % n for i in range(k)]
        runs.append(best)
    out = []
    for run in runs:
        seg = [
            float(np.linalg.norm(pts[b] - pts[a])) for a, b in zip(run[:-1], run[1:], strict=True)
        ]
        if not seg:
            continue
        lo, hi = 0, len(run) - 1
        ends = []
        convex = bool(on.all())  # the sides beside the back are its ends, however long
        if (convex or seg[0] < end_share * max(seg)) and hi - lo > 1:
            ends.append(shapely.LineString(pts[[run[0], run[1]]]))
            lo += 1
        if (convex or seg[-1] < end_share * max(seg)) and hi - lo > 1:
            ends.append(shapely.LineString(pts[[run[-2], run[-1]]]))
            hi -= 1
        back = shapely.LineString(pts[run[lo : hi + 1]])
        if back.length <= 0:
            continue
        ring = np.asarray(plan.exterior.coords)
        depth = max(back.distance(shapely.Point(p)) for p in ring)
        out.append(Footprint(plan, back, ends, float(depth), seg[lo:hi]))
    return out


def height(fp: Footprint, h: Heights, xy: np.ndarray) -> np.ndarray:
    """The top's height (cm) at points over the footprint: the profile by the distance from the
    back edge, lowered towards an arm's end over the hip's length."""
    import shapely

    pts = shapely.points(xy)
    d = shapely.distance(fp.back, pts)
    prof = [(0.0, h.back)]
    if h.strip > 0:
        prof.append((h.strip, h.back - h.fall))
    prof.append((fp.depth, h.front))
    p = np.array(prof)
    z = np.interp(d, p[:, 0], p[:, 1])
    if h.end is not None and h.hip > 0 and fp.ends:
        t = np.min([shapely.distance(e, pts) for e in fp.ends], axis=0)
        w = np.clip(t / h.hip, 0.0, 1.0)
        z = h.end + (z - h.end) * w
    return np.asarray(z, dtype=np.float64)


@dataclass
class Layout:
    """The footprint cut into the top's pieces (each a flat region, triangulated) and the walls
    (runs along the outline): what does not change when only the heights do."""

    tops: list[tuple[str, np.ndarray, np.ndarray]]  # name, xy (cm), triangles
    walls: list[tuple[str, np.ndarray]]  # name, xy along the outline (cm)


def _bisectors(fp: Footprint) -> list[Any]:
    """Seams from each corner of the back edge into the cover, halving its angle: where the
    two arms' slopes meet (the fold of the distance from the back edge)."""
    import shapely

    c = np.asarray(fp.back.coords)
    out = []
    for i in range(1, len(c) - 1):
        d1, d2 = c[i] - c[i - 1], c[i + 1] - c[i]
        d1, d2 = d1 / np.linalg.norm(d1), d2 / np.linalg.norm(d2)
        n1, n2 = np.array([-d1[1], d1[0]]), np.array([-d2[1], d2[0]])
        bis = n1 + n2
        if np.linalg.norm(bis) < 1e-9:
            continue
        bis /= np.linalg.norm(bis)
        if not fp.plan.contains(shapely.Point(c[i] + bis * CORNER_CM * 2)):
            bis = -bis
        half = math.acos(float(np.clip(n1 @ bis, -1, 1)))
        reach = fp.depth / max(math.cos(half), 1e-3) * 1.2  # param-ok: a little past the front
        out.append(
            shapely.LineString([c[i] - bis * CORNER_CM, c[i] + bis * min(reach, CUT_REACH_CM)])
        )
    return out


def layout(
    fp: Footprint, strip: float, hip: float, has_end: bool, roll_cm: float, step: float = STEP_CM
) -> Layout:
    import shapely
    from shapely.ops import split

    from coverengine.plan_profile import _tri_region

    plan = fp.plan
    zones: list[tuple[str, Any]] = []
    rest = plan
    if has_end and hip > 0 and fp.ends:
        hz = shapely.union_all([e.buffer(hip, cap_style="flat") for e in fp.ends])
        zones.append(("hip", plan.intersection(hz)))
        rest = plan.difference(hz)
    if strip > 0:
        sb = fp.back.buffer(strip, quad_segs=32)
        zones = [("strip", rest.intersection(sb)), ("slope", rest.difference(sb)), *zones]
    else:
        zones = [("slope", rest), *zones]
    lines = _bisectors(fp)
    tops: list[tuple[str, np.ndarray, np.ndarray]] = []
    for kind, geom in zones:
        g0 = geom.buffer(0)
        parts = [
            g for g in getattr(g0, "geoms", [g0]) if g.geom_type == "Polygon" and g.area > 1.0
        ]  # param-ok: cm², no slivers
        for ln in lines:
            nxt = []
            for g in parts:
                nxt += [x for x in split(g, ln).geoms if x.area > 1.0]  # param-ok: cm²
            parts = nxt
        for g in parts:
            for k, sub in enumerate(_roll_strips(g, roll_cm)):
                v, f = _tri_region(sub, step)
                tops.append((f"{kind}-{len(tops) + 1}" + (chr(97 + k) if k else ""), v, f))
    return Layout(tops, _walls(fp, tops))


def _walls(
    fp: Footprint, tops: list[tuple[str, np.ndarray, np.ndarray]]
) -> list[tuple[str, np.ndarray]]:
    """The walls on the outline, through the points the top pieces have there (so they meet
    point to point), split where the outline turns a corner."""
    import shapely

    ring = fp.plan.exterior
    total = ring.length
    on = np.vstack([v for _, v, _ in tops])
    on = on[shapely.distance(ring, shapely.points(on)) < 1e-6]  # param-ok: cm, on the outline
    s = set(np.round(shapely.line_locate_point(ring, shapely.points(on)), 6).tolist())
    corners = _corners(fp.plan)
    m = len(corners)
    cuts = []
    for i in range(m):
        u, w = corners[i] - corners[i - 1], corners[(i + 1) % m] - corners[i]
        if math.degrees(abs(math.atan2(u[0] * w[1] - u[1] * w[0], u @ w))) > WALL_TURN_DEG:
            cuts.append(round(float(ring.project(shapely.Point(corners[i]))), 6))
    cuts = sorted(set(cuts)) or [0.0]
    s |= set(cuts)
    pos = np.array(sorted(x % total for x in s))
    walls: list[tuple[str, np.ndarray]] = []
    for i, a in enumerate(cuts):
        b = cuts[i + 1] if i + 1 < len(cuts) else cuts[0] + total
        sel = [x for x in pos if a <= x <= b] + [x + total for x in pos if x + total <= b]
        if b >= total and (b - total) not in sel and b not in sel:
            sel.append(b)
        sel = sorted(set(sel))
        if len(sel) < 2:  # param-ok: a wall needs two points
            continue
        xy = np.array([ring.interpolate(x % total).coords[0] for x in sel])
        walls.append((_wall_name(fp, xy, len(walls) + 1), xy))
    return walls


def _wall_name(fp: Footprint, xy: np.ndarray, i: int) -> str:
    import shapely

    mid = shapely.Point((xy[len(xy) // 2] + xy[(len(xy) - 1) // 2]) / 2)
    if fp.back.distance(mid) < HULL_NEAR_CM:
        return f"back-{i}"
    if any(e.distance(mid) < HULL_NEAR_CM for e in fp.ends):
        return f"end-{i}"
    return f"front-{i}"


def _roll_strips(g: Any, roll_cm: float) -> list[Any]:
    """A top piece wider than the roll in every direction is cut along its length."""
    import shapely
    from shapely.ops import split

    rect = np.asarray(g.minimum_rotated_rectangle.exterior.coords)[:4]
    e1, e2 = rect[1] - rect[0], rect[2] - rect[1]
    short, long_ = (e1, e2) if np.linalg.norm(e1) <= np.linalg.norm(e2) else (e2, e1)
    n = math.ceil(float(np.linalg.norm(short)) / roll_cm)
    if n <= 1:
        return [g]
    u = long_ / np.linalg.norm(long_)
    base = rect[0] if short is e2 else rect[1]
    step = short if short is e2 else -short
    parts = [g]
    for k in range(1, n):
        p = base + step * (k / n)
        ln = shapely.LineString([p - u * CUT_REACH_CM, p + u * CUT_REACH_CM])
        parts = [x for q in parts for x in split(q, ln).geoms]
    return parts


def surface(
    fp: Footprint, h: Heights, lay: Layout
) -> tuple[np.ndarray, np.ndarray, list[tuple[str, slice]]]:
    """The cover surface (mm, the sheet's frame) as one mesh: vertices, triangles, and which
    triangles belong to which piece."""
    vs, fs, names = [], [], []
    off = nf = 0
    for name, xy, f in lay.tops:
        z = height(fp, h, xy)
        vs.append(np.column_stack([xy, z]) * MM)
        fs.append(f + off)
        names.append((name, slice(nf, nf + len(f))))
        off += len(xy)
        nf += len(f)
    for name, xy in lay.walls:
        z = height(fp, h, xy)
        k = len(xy)
        top = np.column_stack([xy, z])
        bot = np.column_stack([xy, np.zeros(k)])
        vs.append(np.vstack([bot, top]) * MM)
        i = np.arange(k - 1)
        f = np.vstack(
            [np.column_stack([i, i + 1, k + i + 1]), np.column_stack([i, k + i + 1, k + i])]
        )
        fs.append(f + off)
        names.append((name, slice(nf, nf + len(f))))
        off += 2 * k
        nf += len(f)
    return np.vstack(vs), np.vstack(fs), names


def pieces(fp: Footprint, h: Heights, lay: Layout) -> list[Piece]:
    """As drawn.scene expects them: faces in mm, y towards the front."""
    from coverengine.drawn import conform

    v, f, names = surface(fp, h, lay)
    tri = v[f]
    area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    keep = area > SLIVER_MM2
    out = [Piece(name, [[(float(x), -float(y), float(z)) for x, y, z in v[t]]
                        for t, k in zip(f[sl], keep[sl], strict=True) if k])
           for name, sl in names]  # fmt: skip
    return conform([p for p in out if p.faces])


# --- the fit -------------------------------------------------------------------------------------

ROUNDS = 3  # param-ok: rounds of fitting one group of heights after the other
SCALE_FIX_SHARE = 0.06  # param-ok: the top view's scale is corrected by written lengths this close
AZIMUTH_NEAR = 0.05  # param-ok: corners whose block fits this close to the best are all tried
STRIP_MIN_CM = 5.0  # param-ok: a strip or a hip narrower than this is no strip


def _near(x: float, sizes: list[float], tol: float) -> float | None:
    """The written size within tolerance of x (2.5 %, or as many cm per 100), the nearest."""
    near = [s for s in sizes if abs(s - x) <= max(tol * x, tol * 100.0)]  # param-ok: % or cm
    return min(near, key=lambda s: abs(s - x)) if near else None


def _plan(read: dict[str, Any], tol: float) -> tuple[Any, float] | None:
    """The top view's outline in cm, its scale corrected so its long lengths along the outside
    are the written ones (the views' scale is a median over the sheet)."""
    import shapely

    ortho = [v for v in read["views"] if v.kind == "plan"] or [
        v for v in read["views"] if v.kind != "iso"]  # fmt: skip
    if not ortho:
        return None
    v = max(ortho, key=lambda v: v.size[0] * v.size[1])
    plan = shapely.Polygon(v.outline * float(v.meta["scale"])).buffer(0)
    if plan.geom_type != "Polygon":
        return None
    plan = plan.simplify(SIMPLIFY_CM)
    pts = _corners(plan)
    lens = [float(np.linalg.norm(pts[(i + 1) % len(pts)] - pts[i])) for i in range(len(pts))]
    ratios = []
    for L in sorted(lens, reverse=True)[:4]:  # param-ok: the longest bits
        w = _near(L, read["sizes_cm"], SCALE_FIX_SHARE)
        if w:
            ratios.append(w / L)
    fix = float(np.median(ratios)) if ratios else 1.0
    if abs(fix - 1) > tol / 10:  # param-ok: a real correction, not rounding
        plan = shapely.affinity.scale(plan, fix, fix, origin=(0, 0))
    else:
        fix = 1.0
    return plan, fix


def lengths(fp: Footprint, sizes: list[float], tol: float) -> dict[str, Any]:
    """The footprint's own lengths (the back edge's bits, the depth) found among the written
    sizes."""
    mine = [*fp.back_cm, fp.depth]
    hits = [_near(x, sizes, tol) for x in mine]
    return {"lengths_cm": [round(x, 1) for x in mine],
            "written_cm": [None if h is None else round(h, 1) for h in hits],
            "matched": sum(h is not None for h in hits), "of": len(mine)}  # fmt: skip


@dataclass
class _Eval:
    fp: Footprint
    pic: Picture
    p: dict[str, float]
    roll_cm: float
    layouts: dict[tuple[float, float, bool], Layout]
    seen: dict[tuple[Any, ...], tuple[float, float, float]]

    def __call__(self, h: Heights, az: float) -> tuple[float, float, float]:
        key = (h, az)
        if key not in self.seen:
            lk = (h.strip, h.hip, h.end is not None)
            if lk not in self.layouts:
                self.layouts[lk] = layout(self.fp, h.strip, h.hip, h.end is not None,
                                          self.roll_cm, FIT_STEP_CM)  # fmt: skip
            v, f, _ = surface(self.fp, h, self.layouts[lk])
            m, c = render(v, f, self.pic, az, self.p["isofit_crease_deg"])
            iou, crease = score(m, c, self.pic, self.p["isofit_edge_px"])
            self.seen[key] = (iou + self.p["isofit_edge_weight"] * crease, iou, crease)
        return self.seen[key]


def _distinct(h: Heights) -> bool:
    """A written size measures one thing: no two of the heights are the same written size (a
    flat top, the front as high as the back, is the one exception)."""
    vals = [h.strip, h.hip, h.end or 0.0] + ([h.front] if h.front < h.back else [])
    used = [v for v in vals if v > 0] + [h.back]
    return len(used) == len(set(used))


def _descend(
    ev: _Eval, az: float, sizes: list[float]
) -> tuple[Heights, tuple[float, float, float]]:
    """The heights, one group after the other, each the best of the written sizes."""
    p, fp = ev.p, ev.fp
    lo, hi = p["isofit_height_min_cm"], p["isofit_height_max_cm"]
    tall = [s for s in sizes if lo <= s <= hi]
    strips = [0.0] + [s for s in sizes if STRIP_MIN_CM <= s <= p["isofit_strip_share"] * fp.depth]
    hips = [s for s in sizes if STRIP_MIN_CM <= s <= p["isofit_hip_share"] * min(fp.back_cm)]
    # the back: the block that fits the silhouette best
    hb = max(tall, key=lambda s: (ev(Heights(s, s), az)[1], -s))
    h = Heights(hb, hb)
    best = ev(h, az)

    def profile(h: Heights) -> list[Heights]:
        return [Heights(h.back, f, s, h.end, h.hip) for s in strips for f in tall if f <= h.back]

    def ends(h: Heights) -> list[Heights]:
        if not fp.ends:
            return []
        return [Heights(h.back, h.front, h.strip)] + [
            Heights(h.back, h.front, h.strip, e, L) for e in tall if e < h.front for L in hips
        ]

    def back(h: Heights) -> list[Heights]:
        return [Heights(b, h.front, h.strip, h.end, h.hip) for b in tall if b >= h.front]

    for _ in range(ROUNDS):
        start = h
        for group in (profile, ends, back):  # each starts from the best so far
            for c in group(h):
                if not _distinct(c):
                    continue
                s = ev(c, az)
                if s[0] > best[0]:
                    h, best = c, s
        if h == start:
            break
    return h, best


def fit(pdf: Path, read: dict[str, Any], params: EffectiveParams, roll_cm: float) -> dict[str, Any]:
    """The best footprint and heights for the drawing's 3D view. {"fit": ..., "why": ...}; the
    fit holds the footprint, heights, the corner it is seen from, its IoU and crease score, and
    the footprint's lengths against the written ones."""
    p = _params(params)
    iso = next((v for v in read["views"] if v.kind == "iso"), None)
    if iso is None:
        return {"fit": None, "why": "no 3D view"}
    got = _plan(read, p["isofit_size_tol"])
    if got is None:
        return {"fit": None, "why": "no top view"}
    plan, fix = got
    pic = picture(pdf, iso, int(p["isofit_px"]), p["isofit_shade_step"])
    return fit_picture(plan, sorted(set(read["sizes_cm"])), pic, params, roll_cm, fix)


def fit_picture(plan: Any, sizes: list[float], pic: Picture, params: EffectiveParams,
                roll_cm: float, fix: float = 1.0) -> dict[str, Any]:  # fmt: skip
    """The fit of a footprint (cm, the sheet's frame) to a picture, the heights chosen from
    `sizes`."""
    p = _params(params)
    tall = [s for s in sizes if p["isofit_height_min_cm"] <= s <= p["isofit_height_max_cm"]]
    if not tall:
        return {"fit": None, "why": "no written height"}
    best: dict[str, Any] | None = None
    for fp in footprints(plan, p["isofit_end_share"]):
        ev = _Eval(fp, pic, p, roll_cm, {}, {})
        mid = tall[len(tall) // 2]
        blocks = {az: ev(Heights(mid, mid), az)[1] for az in CORNERS_DEG}
        top = max(blocks.values())
        for az in CORNERS_DEG:
            if blocks[az] < top - AZIMUTH_NEAR:
                continue
            h, s = _descend(ev, az, sizes)
            if best is None or s[0] > best["score"]:
                best = {"fp": fp, "heights": h, "azimuth": az, "score": s[0], "iou": s[1],
                        "crease": s[2], "scale_fix": fix,
                        "lengths": lengths(fp, sizes, p["isofit_size_tol"])}  # fmt: skip
    if best is None:
        return {"fit": None, "why": "no back edge found on the top view"}
    return {"fit": best, "why": None}


def solid_score(
    mesh_mm: Any, pdf: Path, read: dict[str, Any], params: EffectiveParams
) -> dict[str, float]:
    """Any solid (the views' block, a live cover) scored the same way: the best corner."""
    p = _params(params)
    iso = next(v for v in read["views"] if v.kind == "iso")
    pic = picture(pdf, iso, int(p["isofit_px"]), p["isofit_shade_step"])
    v, f = np.asarray(mesh_mm.vertices), np.asarray(mesh_mm.faces)
    best = {"score": -1.0, "iou": 0.0, "crease": 0.0, "azimuth": 0.0}
    for az in CORNERS_DEG:
        m, c = render(v, f, pic, az, p["isofit_crease_deg"])
        iou, crease = score(m, c, pic, p["isofit_edge_px"])
        s = iou + p["isofit_edge_weight"] * crease
        if s > best["score"]:
            best = {"score": s, "iou": iou, "crease": crease, "azimuth": az}
    return best


def why_not(best: dict[str, Any], params: EffectiveParams) -> list[str]:
    """Why a fit cannot be taken (nothing: it can): its silhouette, its creases, the footprint's
    lengths against the written ones."""
    p = _params(params)
    out = []
    if best["iou"] < p["min_iou"]:
        out.append(f"the fitted heights fit the 3D view only {best['iou']:.0%} "
                   f"(needs {p['min_iou']:.0%})")  # fmt: skip
    if best["crease"] < p["isofit_min_crease"]:
        out.append(f"the fitted shape's creases lie on the 3D view's only {best['crease']:.0%} "
                   f"(needs {p['isofit_min_crease']:.0%})")  # fmt: skip
    L = best["lengths"]
    if L["matched"] < p["isofit_trust_share"] * L["of"]:
        out.append(f"only {L['matched']} of the top view's {L['of']} lengths are written on "
                   "the drawing")  # fmt: skip
    return out


def info(best: dict[str, Any]) -> dict[str, Any]:
    """What was fitted, for drawing_read.json and the Desk's card."""
    h: Heights = best["heights"]
    return {
        "back_cm": h.back, "front_cm": h.front, "strip_cm": h.strip, "end_cm": h.end,
        "hip_cm": h.hip, "depth_cm": round(best["fp"].depth, 1),
        "back_lengths_cm": [round(x, 1) for x in best["fp"].back_cm],
        "arm_ends": len(best["fp"].ends), "seen_from_deg": best["azimuth"],
        "fits_3d_view": round(float(best["iou"]), 3), "creases": round(float(best["crease"]), 3),
        "lengths": best["lengths"], "scale_fix": round(float(best["scale_fix"]), 4),
    }  # fmt: skip


def describe(best: dict[str, Any]) -> list[str]:
    h: Heights = best["heights"]
    back = " + ".join(f"{x:.0f}" for x in best["fp"].back_cm)
    out = [f"top view's footprint, back edge {back} cm",
           f"back {h.back:g} cm" + (f" with a {h.strip:g} cm strip" if h.strip else "")
           + f", front {h.front:g} cm at {best['fp'].depth:.0f} cm deep"]  # fmt: skip
    if h.end is not None:
        out.append(f"arm ends {h.end:g} cm high, the top falling to them over {h.hip:g} cm")
    out.append(f"heights fitted to the 3D view ({best['iou']:.0%}, creases {best['crease']:.0%})")
    return out


def build(best: dict[str, Any], roll_cm: float, strip_fall_deg: float = 0.0) -> list[Piece]:
    """The fitted cover's pieces at full detail; the flat strip along the back falls by
    `strip_fall_deg` towards the seat when asked (water off a flat strip, domain rule 12)."""
    import dataclasses

    h: Heights = best["heights"]
    if strip_fall_deg > 0 and h.strip > 0:
        h = dataclasses.replace(h, fall=h.strip * math.tan(math.radians(strip_fall_deg)))
    lay = layout(best["fp"], h.strip, h.hip, h.end is not None, roll_cm)
    return pieces(best["fp"], h, lay)
