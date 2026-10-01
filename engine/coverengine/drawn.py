"""Cover surfaces built from the owner's drawings (ADR-046).

Each shape is made from the sizes on the drawing, piece by piece as drawn, and written as one
part per piece; the cover-surface route (`hull.top: given`) then turns every part into one cut
piece. Sizes in cm (as on the drawings), the surface in mm, Z up, open at the bottom; x along
the back, y towards the front.

- box: flat top, four walls (5 pieces);
- sloped box: back higher than the front; a flat strip along the back, a straight slope, an
  optional flat strip along the front; back and front walls, two ends (6 or 7 pieces);
- L shape: the sloped box along two arms, which meet at the corner: the strips split from their
  inside corner to the outside corner, the slopes along the line where they meet (10 pieces);
- round: a cylinder, the top split into strips across the roll, the band into at least two
  pieces (a closed band needs a seam to lie flat).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import trimesh

from coverengine.errors import CoverError

MM = 10.0  # param-ok: cm to mm
Face = list[tuple[float, float, float]]
SHAPES = ("box", "sloped box", "L shape", "round")
ROUND_SEGMENTS = 96  # param-ok: the circle as this many straight bits


@dataclass
class Piece:
    name: str
    faces: list[Face]


def _poly(face: Face) -> tuple[np.ndarray, np.ndarray]:
    v = np.array(face, dtype=np.float64)
    tris = [(0, k, k + 1) for k in range(1, len(face) - 1)]
    return v, np.array(tris, dtype=np.int64)


def scene(pieces: list[Piece]) -> trimesh.Scene:
    """One part per piece, faces turned outward (away from the cover's inside). The shapes are
    drawn with y towards the front; the program's front is -y, so y is turned round here."""
    pieces = [Piece(p.name, [[(x, -y, z) for x, y, z in f] for f in p.faces]) for p in pieces]
    allv = np.vstack([np.array(f) for p in pieces for f in p.faces])
    inside = np.append(allv[:, :2].mean(axis=0), allv[:, 2].max() / 3)
    sc = trimesh.Scene()
    for p in pieces:
        vs, fs, off = [], [], 0
        for f in p.faces:
            v, t = _poly(f)
            vs.append(v)
            fs.append(t + off)
            off += len(v)
        m = trimesh.Trimesh(np.vstack(vs), np.vstack(fs), process=True)
        out = np.einsum("ij,ij->i", m.face_normals, m.triangles_center - inside)
        if float((out * m.area_faces).sum()) < 0:
            m.invert()
        sc.add_geometry(m, node_name=p.name, geom_name=p.name)
    return sc


def _bands(name: str, quad: Face, roll: float) -> list[Piece]:
    """A top piece wider than the roll (from its back edge quad[0..1] to its front edge
    quad[3..2]) split into bands along its length, seams parallel to the back."""
    q = np.array(quad, dtype=np.float64)
    width = float(np.linalg.norm((q[0] + q[1]) / 2 - (q[3] + q[2]) / 2))
    n = max(1, math.ceil(width / roll))
    if n == 1:
        return [Piece(name, [quad])]
    out = []
    for k in range(n):
        t0, t1 = k / n, (k + 1) / n
        a0, b0 = q[0] + (q[3] - q[0]) * t0, q[1] + (q[2] - q[1]) * t0
        a1, b1 = q[0] + (q[3] - q[0]) * t1, q[1] + (q[2] - q[1]) * t1
        out.append(Piece(f"{name}-{k + 1}", [[tuple(a0), tuple(b0), tuple(b1), tuple(a1)]]))
    return out


def _cm(params: dict[str, Any], key: str, default: float | None = None) -> float:
    v = params.get(key, default)
    if v is None:
        raise CoverError(f"the drawing gives no {key}")
    return float(v) * MM


def _strips(name: str, x: float, y0: float, y1: float, z: float, roll: float) -> list[Piece]:
    """A flat top from y0 to y1 across, split along its length into strips the roll can take."""
    n = max(1, math.ceil((y1 - y0) / roll))
    ys = np.linspace(y0, y1, n + 1)
    return [
        Piece(name if n == 1 else f"{name}-{i + 1}",
              [[(0, a, z), (x, a, z), (x, b, z), (0, b, z)]])
        for i, (a, b) in enumerate(zip(ys[:-1], ys[1:], strict=True))
    ]  # fmt: skip


def box(p: dict[str, Any], roll: float = math.inf) -> list[Piece]:
    x, y, h = _cm(p, "length_cm"), _cm(p, "depth_cm"), _cm(p, "height_cm")
    if y > x:  # the long side along x
        x, y = y, x
    return [
        *_strips("top", x, 0.0, y, h, roll),
        Piece("back", [[(0, 0, 0), (x, 0, 0), (x, 0, h), (0, 0, h)]]),
        Piece("front", [[(0, y, 0), (0, y, h), (x, y, h), (x, y, 0)]]),
        Piece("left", [[(0, 0, 0), (0, 0, h), (0, y, h), (0, y, 0)]]),
        Piece("right", [[(x, 0, 0), (x, y, 0), (x, y, h), (x, 0, h)]]),
    ]


def _profile(p: dict[str, Any], depth: float) -> list[tuple[float, float]]:
    """The end profile of a sloped box: (y, z) from the back bottom round to the front bottom."""
    hb, hf = _cm(p, "back_height_cm"), _cm(p, "front_height_cm")
    sb, sf = _cm(p, "back_strip_cm", 0.0), _cm(p, "front_strip_cm", 0.0)
    pts = [(0.0, 0.0), (0.0, hb)]
    if sb > 0:
        pts.append((sb, hb))
    if sf > 0:
        pts.append((depth - sf, hf))
    pts += [(depth, hf), (depth, 0.0)]
    return pts


def sloped_box(p: dict[str, Any], roll: float = math.inf) -> list[Piece]:
    """The ends upright, or leaning in (top_length_cm shorter than length_cm: the front view
    narrower at the top, as in the owner's D1); a leaning end is one flat face through its
    bottom edge and the back top corner."""
    x, y = _cm(p, "length_cm"), _cm(p, "depth_cm")
    prof = _profile(p, y)
    hb = prof[1][1]
    lean = max(0.0, (x - _cm(p, "top_length_cm", x / MM)) / 2)

    def at(side: int, yy: float, zz: float) -> tuple[float, float, float]:
        d = lean * zz / hb  # how far the end has come in at this height
        return (d, yy, zz) if side == 0 else (x - d, yy, zz)

    top = prof[1:-1]  # along the top: back edge ... front edge
    names = []
    if _cm(p, "back_strip_cm", 0.0) > 0:
        names.append("top-back strip")
    names.append("top-slope")
    if _cm(p, "front_strip_cm", 0.0) > 0:
        names.append("top-front strip")
    pieces = []
    for name, (a, b) in zip(names, zip(top[:-1], top[1:], strict=True), strict=True):
        quad = [at(0, *a), at(1, *a), at(1, *b), at(0, *b)]
        pieces += _bands(name, quad, roll)
    hf = prof[-2][1]
    pieces += [
        Piece("back", [[(0, 0, 0), (x, 0, 0), at(1, 0, hb), at(0, 0, hb)]]),
        Piece("front", [[(0, y, 0), at(0, y, hf), at(1, y, hf), (x, y, 0)]]),
        Piece("left", [[at(0, yy, zz) for yy, zz in prof]]),
        Piece("right", [[at(1, yy, zz) for yy, zz in reversed(prof)]]),
    ]
    return pieces


def l_shape(p: dict[str, Any], roll: float = math.inf) -> list[Piece]:
    """Arm A along x (outside length X, depth dA), arm B along y (outside length Y, depth dB),
    the outside corner at the origin; back strips sA, sB; back height hb, front height hf."""
    X, Y = _cm(p, "x_length_cm"), _cm(p, "y_length_cm")
    dA, dB = _cm(p, "x_arm_depth_cm"), _cm(p, "y_arm_depth_cm")
    sA, sB = _cm(p, "x_back_strip_cm", 0.0), _cm(p, "y_back_strip_cm", 0.0)
    hb, hf = _cm(p, "back_height_cm"), _cm(p, "front_height_cm")
    if not (sA < dA < Y and sB < dB < X):
        raise CoverError("the L shape's sizes do not fit together")
    pieces = []
    corner = str(p.get("strip_corner") or "mitre")  # mitre | x (x strip runs on) | y
    if sA > 0 or sB > 0:
        if corner == "x":  # the x strip runs to the outside corner, the y strip butts on to it
            x_strip = [(0, 0, hb), (X, 0, hb), (X, sA, hb), (sB, sA, hb), (0, sA, hb)]
            y_strip = [(0, sA, hb), (sB, sA, hb), (sB, Y, hb), (0, Y, hb)]
        elif corner == "y":
            x_strip = [(sB, 0, hb), (X, 0, hb), (X, sA, hb), (sB, sA, hb)]
            y_strip = [(0, 0, hb), (sB, 0, hb), (sB, sA, hb), (sB, Y, hb), (0, Y, hb)]
        else:  # from the inside corner of the strips to the outside corner
            x_strip = [(0, 0, hb), (X, 0, hb), (X, sA, hb), (sB, sA, hb)]
            y_strip = [(0, 0, hb), (sB, sA, hb), (sB, Y, hb), (0, Y, hb)]
        pieces += [Piece("top-x strip", [x_strip]), Piece("top-y strip", [y_strip])]
    pieces += _bands("top-x slope", [(sB, sA, hb), (X, sA, hb), (X, dA, hf), (dB, dA, hf)], roll)
    pieces += _bands("top-y slope", [(sB, Y, hb), (sB, sA, hb), (dB, dA, hf), (dB, Y, hf)], roll)
    pieces += [
        Piece("back-x", [[(0, 0, 0), (X, 0, 0), (X, 0, hb), (0, 0, hb)]]),
        Piece("back-y", [[(0, 0, 0), (0, 0, hb), (0, Y, hb), (0, Y, 0)]]),
        Piece("front-x", [[(dB, dA, 0), (dB, dA, hf), (X, dA, hf), (X, dA, 0)]]),
        Piece("front-y", [[(dB, dA, 0), (dB, Y, 0), (dB, Y, hf), (dB, dA, hf)]]),
    ]
    end_x = [(X, 0, 0), (X, dA, 0), (X, dA, hf), (X, sA, hb), (X, 0, hb)]
    end_y = [(0, Y, 0), (0, Y, hb), (sB, Y, hb), (dB, Y, hf), (dB, Y, 0)]
    pieces += [Piece("end-x", [_dedupe(end_x)]), Piece("end-y", [_dedupe(end_y)])]
    return pieces


def _dedupe(face: Face) -> Face:
    out: Face = []
    for q in face:
        if not out or np.linalg.norm(np.subtract(q, out[-1])) > 1e-6:
            out.append(q)
    return out


def round_cover(p: dict[str, Any], roll_mm: float) -> list[Piece]:
    """A cylinder: the top split into strips no wider than the roll, the band into pieces. The
    points where a strip seam meets the edge are points of the band too (no gaps)."""
    r, h = _cm(p, "diameter_cm") / 2, _cm(p, "height_cm")
    bands = max(2, int(p.get("band_pieces") or 2))  # a band closes with at least one seam
    strips = max(1, math.ceil(2 * r / roll_mm))
    edges = np.linspace(-r, r, strips + 1)
    angles = [float(t) for t in np.linspace(0, 2 * math.pi, ROUND_SEGMENTS, endpoint=False)]
    for e in edges[1:-1]:  # where the strip seams meet the edge
        t = math.acos(float(e) / r)
        angles += [t, 2 * math.pi - t]
    angles = sorted(set(round(t, 12) for t in angles))
    ring = np.array([(r * math.cos(t), r * math.sin(t)) for t in angles])
    pieces = []
    for i in range(strips):
        lo, hi = edges[i] - 1e-6, edges[i + 1] + 1e-6  # param-ok: rounding margin
        pts = ring[(ring[:, 0] >= lo) & (ring[:, 0] <= hi)]
        c = pts.mean(axis=0)
        pts = pts[np.argsort(np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0]))]
        pieces.append(Piece(f"top-{i + 1}", [[(float(x), float(y), h) for x, y in pts]]))
    n = len(ring)
    per = n // bands
    for b in range(bands):
        idx = range(b * per, (b + 1) * per if b < bands - 1 else n)
        faces = []
        for i in idx:
            (x0, y0), (x1, y1) = ring[i], ring[(i + 1) % n]
            faces.append([(x0, y0, 0), (x1, y1, 0), (x1, y1, h), (x0, y0, h)])
        pieces.append(Piece(f"band-{b + 1}", faces))
    return pieces


def build(shape: str, params: dict[str, Any], roll_mm: float) -> list[Piece]:
    if shape == "box":
        return box(params, roll_mm)
    if shape == "sloped box":
        return sloped_box(params, roll_mm)
    if shape == "L shape":
        return l_shape(params, roll_mm)
    if shape == "round":
        return round_cover(params, roll_mm)
    raise CoverError(f"no generator for the shape {shape!r} yet")
