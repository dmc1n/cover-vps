"""The owner's S44 / Cover 110 (the Blocchi 2-seater moon right) from its vector drawing (ADR-052).

The top view in testdata/models/cover.pdf holds the outline (pink) and the seams (black) as
lines; they are read as they are, scaled by the drawn 197.0 cm, and every piece is made of flat
triangles between its drawn edges, with the heights from the drawing: the back and the strip
at 88.0 cm, the front and the bottom of the nose at 40.6 cm, the diagonal seams running down
between. Piecewise flat pieces lie flat exactly. Walls stand under the outline.

    uv run python scripts/s44_cover.py testdata/models/cover.pdf out/drawn/drawing-s44.glb
"""

from __future__ import annotations

import sys

import numpy as np
import pymupdf
import shapely

sys.path.insert(0, "engine")
from coverengine.drawn import Piece, scene  # noqa: E402

HB, HF = 880.0, 406.0  # back and front height (mm): 88.0 and 40.6 cm on the drawing
WIDTH_MM = 1970.0  # the drawn width: 197.0 cm


def strokes(
    pdf: str,
) -> tuple[dict[str, list[list[tuple[float, float]]]], float, float, float]:
    """The top view's pink outline pieces and black seams, as point lists in page points."""
    page = pymupdf.open(pdf)[0]
    out: dict[str, list[list[tuple[float, float]]]] = {"outline": [], "seam": []}
    for p in page.get_drawings():
        r, w = p["rect"], p.get("width") or 0
        if not (r.y1 <= 280 and r.x1 <= 300 and r.x0 >= 70) or w < 0.6:  # the top view
            continue
        col = tuple(round(x, 2) for x in (p.get("color") or ()))
        kind = "outline" if col == (1.0, 0.0, 0.5) else "seam" if col == (0.0, 0.0, 0.0) else None
        if kind is None:
            continue
        cur: list[tuple[float, float]] = []
        for it in p["items"]:
            a, b = (it[1].x, it[1].y), (it[-1].x, it[-1].y)
            if cur and np.hypot(cur[-1][0] - a[0], cur[-1][1] - a[1]) > 0.05:
                out[kind].append(cur)
                cur = []
            if not cur:
                cur = [a]
            cur.append(b)
        if cur:
            out[kind].append(cur)
    xs = [x for s in out["outline"] for x, _ in s]
    ys = [y for s in out["outline"] for _, y in s]
    return out, min(xs), min(ys), WIDTH_MM / (max(xs) - min(xs))


def main(pdf: str, out_glb: str) -> None:
    st, x0, y0, scale = strokes(pdf)

    def mm(p: tuple[float, float]) -> tuple[float, float]:
        # y towards the front, as drawn (the page's y runs down, from the back to the front)
        return (round((p[0] - x0) * scale, 2), round((p[1] - y0) * scale, 2))

    lines = [shapely.LineString([mm(p) for p in s]) for s in st["outline"] + st["seam"]]
    noded = shapely.node(shapely.MultiLineString(lines))
    faces = list(shapely.polygonize(noded.geoms).geoms)
    outline = shapely.union_all(faces)
    ring = shapely.LineString(outline.exterior.coords)
    seams = [shapely.LineString([mm(p) for p in s]) for s in st["seam"]]
    # the corners of the pieces: (x, y) -> height

    def z_of(p: tuple[float, float]) -> float:
        pt = shapely.Point(p)
        on_outline = ring.distance(pt) < 1.0
        on_seam = any(s.distance(pt) < 1.0 for s in seams)
        if on_seam and not on_outline:  # strip edge and the seams' inner ends: the back height
            return HB
        if on_outline:
            return outline_z(p)
        return HB

    # heights along the outline: the back arc (from the straight end round to the nose) high,
    # the front and the nose low; where a seam reaches the outline the height changes
    coords = np.asarray(ring.coords)[:-1]
    corner = int(np.argmin(coords[:, 1] - 0.001 * coords[:, 0]))  # the back corner of the end
    order = np.roll(np.arange(len(coords)), -corner)
    pts = coords[order]
    if abs(pts[1][0] - pts[0][0]) < 1.0:  # the next point is on the end: walk the other way,
        pts = np.vstack([pts[:1], pts[1:][::-1]])  # along the back
    seam_ends = [i for i, p in enumerate(pts)
                 if any(shapely.Point(p).distance(s) < 1.0 for s in seams)]  # fmt: skip
    # the back runs to the first seam end that is not on the straight end; the tip descends to
    # the next; the rest (nose, front) is low; the straight end climbs back to the corner
    end_x = pts[0][0]
    off_end = [i for i in seam_ends if abs(pts[i][0] - end_x) > 1.0]
    i_tip, i_low = off_end[0], off_end[1]
    zs = np.full(len(pts), HF)
    zs[: i_tip + 1] = HB
    seg = np.linalg.norm(np.diff(pts[i_tip : i_low + 1], axis=0), axis=1)
    t = np.concatenate([[0], np.cumsum(seg)]) / max(seg.sum(), 1e-9)
    zs[i_tip : i_low + 1] = HB + (HF - HB) * t
    on_end = np.abs(pts[:, 0] - end_x) < 1.0
    strip_corner = [i for i in seam_ends if on_end[i]]
    for i in np.flatnonzero(on_end):  # the end: high above the strip's seam, then down
        if strip_corner and pts[i][1] <= pts[strip_corner[0]][1] + 1.0:
            zs[i] = HB
    table = {(round(p[0], 1), round(p[1], 1)): z for p, z in zip(pts, zs, strict=True)}

    def outline_z(p: tuple[float, float]) -> float:
        key = (round(p[0], 1), round(p[1], 1))
        if key in table:
            return table[key]
        k = int(np.argmin(np.linalg.norm(pts - np.asarray(p), axis=1)))
        return float(zs[k])

    pieces = []
    names = {}
    for k, f in enumerate(sorted(faces, key=lambda g: -g.area)):
        c = f.centroid
        names[k] = f"top-{k + 1}"
        tris = []
        for tri in shapely.constrained_delaunay_triangles(f).geoms:
            corners = np.asarray(tri.exterior.coords)[:3]
            tris.append([(float(x), float(y), z_of((x, y))) for x, y in corners])
        pieces.append(Piece(names[k], tris))
        del c
    # walls under the outline, split where a seam reaches it and at the end's corners
    cuts = sorted(
        set(seam_ends) | {0} | {int(i) for i in np.flatnonzero(np.diff(on_end.astype(int)) != 0)}
    )
    cuts.append(len(pts))
    for w, (a, b) in enumerate(zip(cuts[:-1], cuts[1:], strict=True)):
        quads = []
        for i in range(a, b):
            j = (i + 1) % len(pts)
            (xa, ya), (xb, yb) = pts[i], pts[j]
            quads.append([(xa, ya, 0.0), (xb, yb, 0.0), (xb, yb, zs[j]), (xa, ya, zs[i])])
        if quads:
            pieces.append(Piece(f"wall-{w + 1}", quads))
    sc = scene(pieces)
    sc.export(out_glb)
    print(f"{len(faces)} top pieces, {len(pieces) - len(faces)} walls; outline "
          f"{ring.length / 10:.1f} cm; {out_glb}")  # fmt: skip


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
