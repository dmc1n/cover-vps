"""S43's (and S44's, mirrored) pieces as the drawing draws them, written as a "faces" shape
(drawing_given) from the sizes and seam points read off the drawing (Rens, Desk 14 Oct 2026:
"seams beter volgen zoals op tekening"; ADR-140).

    uv run python scripts/s43_shape.py testdata/drawing_shapes

The body is the swept shape read before (ADR-131): the back edge a 41.24 cm line and a 167.1 cm
radius arc over 61.835 degrees; the profile from the back: upright to 40.64 cm, leaning in 9.4 cm
to 88.01 cm, a 33.07 cm level strip, a slope to 40.64 cm at 141.86 cm; a round nose (the
section's half circle) whose wall is 40.64 cm all round. What changes are the seams, traced off
the drawing's top view and checked against its 3D view (cm, origin the back left corner, y to
the front):

- the strip ends on the line A-B (A on its inner edge, ~59.5 degrees round the arc as traced;
  B on its outer edge where the written 185.94 cm "cushion circumference" ends, ~52.6 degrees),
  not square across at the arc's end;
- the leaning back band runs on past B round the back of the nose to C on the rim, its end the
  line B-C (a cone from B);
- the slope runs on to D on the front of the nose, its end the line A-D (a cone from A);
- the nose top is what is left: A, B, C, the rim round to D (cones from B and from A);
- the walls are cut where the drawing draws vertical lines: at the back corner and the front
  corner of the straight end, where the straight front turns into the curve, where the concave
  curve turns into the round nose, at D and at C.

Every piece is made of flat triangles and quads that are rulings of cones, so each lies flat.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

LINE = 41.24
RB = 167.1  # the back edge's radius
THETA = 61.835  # degrees the arc turns
WALL, TOP, BAND_IN, STRIP_IN, DEPTH = 40.64, 88.01, 9.4, 42.47, 141.86
# traced off the drawing's top view (cm), each moved onto the line it lies on
A_READ, B_READ, C_READ, D_READ = (149.3, 103.3), (169.4, 75.8), (193.8, 106.5), (119.7, 191.2)
CUSHION = (
    185.94  # written: "Length Cushion circumference", the strip's outer edge (the blue line) to B
)
STEP_DEG = 2.0  # arcs as straight bits of at most this many degrees

CENTRE = np.array([LINE, RB])  # the arc's centre


def arc_pt(r: float, deg: float) -> np.ndarray:
    t = math.radians(deg)
    return CENTRE + r * np.array([math.sin(t), -math.cos(t)])


def arc_deg(p: tuple[float, float]) -> float:
    d = np.asarray(p) - CENTRE
    return math.degrees(math.atan2(d[0], -d[1]))


def steps(a: float, b: float, most: float = STEP_DEG, extra: tuple[float, ...] = ()) -> list[float]:
    """From a to b (either way) through every multiple of `most` between and the `extra` angles,
    so two pieces sampling the same arc share their points."""
    lo, hi = min(a, b), max(a, b)
    grid = {k * most for k in range(math.floor(lo / most) + 1, math.ceil(hi / most))}
    pts = sorted({lo, hi} | {g for g in grid if lo + 1e-6 < g < hi - 1e-6}
                 | {e for e in extra if lo + 1e-6 < e < hi - 1e-6})  # fmt: skip
    return pts if a <= b else pts[::-1]


RF = RB - DEPTH
N = CENTRE + (RB + RF) / 2 * np.array(
    [math.sin(math.radians(THETA)), -math.cos(math.radians(THETA))]
)
RN = DEPTH / 2


def nose_pt(deg: float) -> np.ndarray:
    t = math.radians(deg)
    return N + RN * np.array([math.cos(t), math.sin(t)])


def nose_deg(p: tuple[float, float]) -> float:
    d = np.asarray(p) - N
    return math.degrees(math.atan2(d[1], d[0]))


def P(xy: np.ndarray, z: float) -> list[float]:
    return [round(float(xy[0]), 3), round(float(xy[1]), 3), round(z, 3)]


def pieces() -> tuple[dict[str, list[list[list[float]]]], dict[str, float]]:
    th_a = round(arc_deg(A_READ), 1)
    # B where the written cushion length ends (traced: ~54.5 deg; written sizes win, ADR-133)
    th_b = round(math.degrees((CUSHION - LINE) / (RB - BAND_IN)), 2)
    ph_c, ph_d = round(nose_deg(C_READ), 1), round(nose_deg(D_READ), 1)
    ph_back = nose_deg(tuple(arc_pt(RB, THETA)))  # the back end of the nose's diameter
    ph_front = nose_deg(tuple(arc_pt(RF, THETA)))  # its front end
    rs, ri = RB - BAND_IN, RB - STRIP_IN
    a, b = arc_pt(ri, th_a), arc_pt(rs, th_b)
    out: dict[str, list[list[list[float]]]] = {}

    # the outline's rim points, in order round each run
    back_rim = [arc_pt(RB, t) for t in steps(0, THETA, extra=(th_b,))] + [
        nose_pt(f) for f in steps(ph_back, ph_c)[1:]
    ]
    front_arc = [arc_pt(RF, t) for t in steps(0, THETA, extra=(th_a,))]  # the concave curve
    front_round = [nose_pt(f) for f in steps(ph_front, ph_d)]  # the nose's front, to D
    nose_rim = [nose_pt(f) for f in steps(ph_c, ph_d, 3.0)]

    # back band: the straight part, the cone round the arc to B, the cone from B to C
    band = [[[0, 0, WALL], [LINE, 0, WALL], [LINE, BAND_IN, TOP], [0, BAND_IN, TOP]]]
    ts = steps(0, th_b)
    for t0, t1 in zip(ts, ts[1:], strict=False):
        band.append([P(arc_pt(RB, t0), WALL), P(arc_pt(RB, t1), WALL), P(arc_pt(rs, t1), TOP),
                     P(arc_pt(rs, t0), TOP)])  # fmt: skip
    wedge = [arc_pt(RB, t) for t in steps(th_b, THETA)] + back_rim[
        len(steps(0, THETA, extra=(th_b,))) :
    ]
    for q0, q1 in zip(wedge, wedge[1:], strict=False):
        band.append([P(q0, WALL), P(q1, WALL), P(b, TOP)])
    out["back-band"] = band

    # strip: level, from the straight end round to the line A-B
    strip = [[0, BAND_IN, TOP], [LINE, BAND_IN, TOP]]
    strip += [P(arc_pt(rs, t), TOP) for t in steps(0, th_b)[1:]]
    strip += [P(arc_pt(ri, t), TOP) for t in reversed(steps(0, th_a)[1:])]
    strip += [[LINE, STRIP_IN, TOP], [0, STRIP_IN, TOP]]
    out["strip"] = [strip]

    # slope: the straight part, the cone round the arc to A, the cone from A to D
    slope = [[[0, STRIP_IN, TOP], [LINE, STRIP_IN, TOP], [LINE, DEPTH, WALL], [0, DEPTH, WALL]]]
    ts = steps(0, th_a)
    for t0, t1 in zip(ts, ts[1:], strict=False):
        slope.append([P(arc_pt(ri, t0), TOP), P(arc_pt(ri, t1), TOP), P(arc_pt(RF, t1), WALL),
                      P(arc_pt(RF, t0), WALL)])  # fmt: skip
    fw = [arc_pt(RF, t) for t in steps(th_a, THETA)] + [
        nose_pt(f) for f in steps(ph_front, ph_d)[1:]
    ]
    for q0, q1 in zip(fw, fw[1:], strict=False):
        slope.append([P(a, TOP), P(q1, WALL), P(q0, WALL)])
    out["slope"] = slope

    # nose top: fans from B and from A over the rim, the triangle A-B-P between
    mid = (a + b) / 2
    perp = np.array([b[1] - a[1], -(b[0] - a[0])])
    perp /= np.linalg.norm(perp)
    if (N - mid) @ perp < 0:
        perp = -perp
    ph_p = min(nose_rim, key=lambda q: float(np.linalg.norm(q - (mid + perp * 1e3))))
    ip = next(i for i, q in enumerate(nose_rim) if q is ph_p)
    nose = []
    for q0, q1 in zip(nose_rim[: ip + 1], nose_rim[1 : ip + 1], strict=False):
        nose.append([P(b, TOP), P(q0, WALL), P(q1, WALL)])
    nose.append([P(b, TOP), P(nose_rim[ip], WALL), P(a, TOP)])
    for q0, q1 in zip(nose_rim[ip:], nose_rim[ip + 1 :], strict=False):
        nose.append([P(a, TOP), P(q0, WALL), P(q1, WALL)])
    out["nose"] = nose

    def wall(rim: list[np.ndarray]) -> list[list[list[float]]]:
        return [
            [P(q0, 0), P(q1, 0), P(q1, WALL), P(q0, WALL)]
            for q0, q1 in zip(rim, rim[1:], strict=False)
        ]

    out["wall-end"] = [[[0, 0, 0], [0, DEPTH, 0], [0, DEPTH, WALL], [0, STRIP_IN, TOP],
                        [0, BAND_IN, TOP], [0, 0, WALL]]]  # fmt: skip
    out["wall-back"] = wall([np.array([0.0, 0.0])] + back_rim)
    out["wall-front-1"] = wall([np.array([0.0, DEPTH]), np.array([LINE, DEPTH])])
    out["wall-front-2"] = wall(front_arc)
    out["wall-front-3"] = wall(front_round)
    out["wall-nose"] = wall(nose_rim)

    def cm(q: np.ndarray) -> list[float]:
        return [round(float(v), 1) for v in q]

    read = {"A_deg_on_arc": th_a, "B_deg_on_arc": th_b, "C_deg_on_nose": ph_c,
            "D_deg_on_nose": ph_d, "A": cm(a), "B": cm(b), "C": cm(nose_pt(ph_c)),
            "D": cm(nose_pt(ph_d))}  # fmt: skip
    return out, read


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    a = ap.parse_args()
    ps, pts = pieces()
    common = (
        "The body as read before (ADR-131): the back edge a 41.24 cm line and a 167.1 cm radius "
        "arc over 61.835 deg; the profile: upright to 40.64 cm, leaning in 9.4 cm to 88.01 cm, a "
        "33.07 cm level strip, a slope to 40.64 cm at 141.86 cm; the round nose the section's half "
        "circle (r 70.93 cm), its wall 40.64 cm all round. The seams as the drawing draws them "
        "(Rens, Desk 14 Oct 2026: 'seams beter volgen zoals op tekening'), traced off its top view "
        "and checked on its 3D view, in cm from the back left corner: the strip ends on the line "
        f"A {pts['A']} - B {pts['B']} (B where the written 185.94 cm cushion circumference along "
        "the strip's outer edge ends); the leaning back band runs on round the back of the nose to "
        f"C {pts['C']} on the rim (the line B-C); the slope runs on to D {pts['D']} on the front "
        "of the nose (the line A-D); the nose top is A-B-C and the rim round to D; the walls are "
        "cut at the straight end's two corners, where the straight front turns into the curve, "
        "where the concave curve turns into the nose, at D and at C, as the 3D views draw them. "
        "Written by scripts/s43_shape.py."
    )
    s44 = ("S44 is S43 mirrored (both drawings 196.95/197.0 x 192.63/192.4 cm, 88 cm back, 33 cm "
           "strip, 141.9 cm slope to 40.6 cm). ")  # fmt: skip
    for name, mirror, extra in (("drawing-s43", False, ""), ("drawing-s44", True, s44)):
        doc = {"shape": "faces", "params": {"pieces": ps}, "read": extra + common}
        if mirror:
            doc["mirror"] = True
        (a.out / f"{name}.json").write_text(json.dumps(doc, separators=(",", ":")) + "\n")
        print(name, {k: len(v) for k, v in ps.items()}, pts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
