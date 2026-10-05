"""Free-form covers from the owner's drawings (ADR-068): a cross-section swept along a path.

Most of the "other" drawings (quarter rings, U and horseshoe sofas, crescents, tapered and
angled sofas, arms that slope down along their length) are the sloped box of drawn.py along a
path that is not one straight line. The path is the cover's back edge in the top view (cm):

- {"line": length}                  a straight stretch;
- {"arc": radius, "angle": degrees} a curve; a positive angle turns towards the front (the back
                                     edge outside, as in a quarter ring), a negative one away;
- {"turn": degrees}                 a sharp corner (mitred: the top meets in a diagonal line).

The cross-section is the top from the back edge to the front edge as points (offset from the
back edge in plan, height), e.g. [[0, 86], [20, 86], [99, 38], [120, 38]]: a flat strip, a slope,
a flat front strip; every point is a seam along the length. The walls drop from the first and
the last point to the ground. It may change along the path ("profiles" at positions along the
back edge, interpolated), so a tapered sofa or an arm that comes down is the same shape.

Cross seams: where the drawing shows them (`seams_cm`, along the back edge), at every corner and
every change between a line and an arc, and wherever a piece would be longer than the workshop
cuts (`max_piece_mm`). Ends: "square" (an upright end wall), "angled" (leaning in, in the top
view, by `end_angle_deg`; straight paths only), or "round" (a half-round end, like the nose of a
U-shaped sofa). Sizes in cm, the surface in mm; x along the back, y towards the front, Z up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from coverengine.drawn import MM, Face, Piece, conform
from coverengine.errors import CoverError

STEP_CM = 5.0  # param-ok: curves sampled at least every 5 cm along the back edge
ROUND_STEPS = 16  # param-ok: a half-round end as this many bits


@dataclass
class Station:
    s: float  # cm along the back edge
    p: np.ndarray  # the back edge point (cm, plan)
    n: np.ndarray  # towards the front, scaled so offsets reach the mitre at a corner
    corner: bool = False


def _path(segments: list[dict[str, Any]], seams: list[float]) -> tuple[list[Station], list[float]]:
    """The back edge as stations (with the front direction at each), and the cross seams."""
    p, h, s = np.zeros(2), 0.0, 0.0
    out: list[Station] = []
    cuts: list[float] = [0.0]

    def front(heading: float) -> np.ndarray:
        return np.array([-math.sin(heading), math.cos(heading)])

    out.append(Station(0.0, p.copy(), front(h)))
    for seg in segments:
        if "line" in seg:
            length = float(seg["line"])
            if length <= 0:
                continue
            d = np.array([math.cos(h), math.sin(h)])
            k = max(1, math.ceil(length / STEP_CM))
            for i in range(1, k + 1):
                out.append(Station(s + length * i / k, p + d * length * i / k, front(h)))
            p, s = p + d * length, s + length
        elif "arc" in seg:
            r, a = float(seg["arc"]), math.radians(float(seg["angle"]))
            length = abs(r * a)
            centre = p + front(h) * r * np.sign(a)
            k = max(2, math.ceil(length / STEP_CM))
            start = math.atan2(*(p - centre)[::-1])
            for i in range(1, k + 1):
                t = start + a * i / k
                q = centre + r * np.array([math.cos(t), math.sin(t)])
                out.append(Station(s + length * i / k, q, front(h + a * i / k)))
            p, h, s = out[-1].p.copy(), h + a, s + length
        elif "turn" in seg:
            a = math.radians(float(seg["turn"]))
            n1, n2 = front(h), front(h + a)
            m = n1 + n2
            m = m / max(float(np.dot(m, n1)), 1e-6)  # param-ok: the mitre reaches both offsets
            out[-1] = Station(s, p.copy(), m, corner=True)
            h += a
        else:
            raise CoverError(f"a path segment needs line, arc or turn: {seg}")
        cuts.append(s)  # every change of segment is a seam
    cuts += [float(x) for x in seams if 0 < float(x) < s]
    return out, sorted({round(c, 6) for c in cuts} | {round(s, 6)})


def _profiles(p: dict[str, Any], total: float) -> list[tuple[float, np.ndarray]]:
    """The cross-sections along the path: (position cm, points [[offset, height], ...])."""
    if p.get("profile") and not p.get("profiles"):  # one cross-section all along
        p = {**p, "profiles": [{"at_cm": 0, "points": p["profile"]}]}
    if p.get("profiles"):
        out = [(float(x["at_cm"]), np.array(x["points"], dtype=float)) for x in p["profiles"]]
    else:
        out = [(0.0, _simple(p))]
        if p.get("end"):  # a second cross-section at the far end (taper, a sloping arm)
            out.append((total, _simple({**p, **p["end"]})))
    out.sort(key=lambda t: t[0])
    n = len(out[0][1])
    if any(len(q) != n for _, q in out):
        raise CoverError("every cross-section needs the same number of points")
    return out


def _simple(p: dict[str, Any]) -> np.ndarray:
    """A sloped box's cross-section from its sizes: back strip, slope, front strip."""
    d, hb, hf = float(p["depth_cm"]), float(p["back_height_cm"]), float(p["front_height_cm"])
    b, f = float(p.get("back_strip_cm") or 0), float(p.get("front_strip_cm") or 0)
    pts = [(0.0, hb)]
    if b > 0:
        pts.append((b, hb))
    if f > 0:
        pts.append((d - f, hf))
    pts.append((d, hf))
    return np.array(pts)


def _at(profiles: list[tuple[float, np.ndarray]], s: float) -> np.ndarray:
    if s <= profiles[0][0] or len(profiles) == 1:
        return profiles[0][1]
    for (s0, a), (s1, b) in zip(profiles, profiles[1:], strict=False):
        if s <= s1:
            t = (s - s0) / max(s1 - s0, 1e-9)
            return a + (b - a) * t
    return profiles[-1][1]


def _xyz(st: Station, offset: float, z: float) -> tuple[float, float, float]:
    q = st.p + st.n * offset
    return (float(q[0]) * MM, float(q[1]) * MM, float(z) * MM)


def build(p: dict[str, Any], roll_mm: float, max_piece_mm: float) -> list[Piece]:
    stations, cuts = _path(list(p.get("path") or []), list(p.get("seams_cm") or []))
    total = stations[-1].s
    if total <= 0:
        raise CoverError("the path has no length")
    profiles = _profiles(p, total)
    _check_bends(p, profiles)
    profiles = _narrow(profiles, roll_mm / MM, _line_lengths(p, stations, profiles))
    if p.get("line_lengths_cm") and len(p["line_lengths_cm"]) != len(profiles[0][1]):
        p = {**p, "line_lengths_cm": _spread(p, profiles)}
    # cut the sections longer than the workshop cuts into equal parts
    cuts = _split(cuts, max_piece_mm / MM)
    stations = _with_cuts(stations, cuts)
    rows = len(profiles[0][1])
    spans = _spans(p, stations, profiles, rows)
    stations = _with_cuts(stations, sorted({x for ab in spans for x in ab}))
    prof = {id(st): _at(profiles, st.s) for st in stations}

    def pt(st: Station, j: int, ground: bool = False) -> tuple[float, float, float]:
        q = prof[id(st)]
        return _xyz(st, q[j, 0], 0.0 if ground else q[j, 1])

    def section(s: float) -> int:
        return next(k for k, c1 in enumerate(cuts[1:], start=1) if s <= c1 + 1e-6)

    pieces: list[Piece] = []
    for j in range(rows - 1):  # the top: one piece per band between two seam lines, per section
        (a0, b0), (a1, b1) = spans[j], spans[j + 1]
        lo, hi = max(a0, a1), min(b0, b1)
        both = [st for st in stations if lo - 1e-6 <= st.s <= hi + 1e-6]
        faces: dict[int, list[Face]] = {}
        for a, b in zip(both, both[1:], strict=False):
            faces.setdefault(section((a.s + b.s) / 2), []).append(
                [pt(a, j), pt(b, j), pt(b, j + 1), pt(a, j + 1)]
            )
        # a hip: where one line runs on past the other, it fans out to the shorter one's end
        first = j if a0 < a1 else j + 1  # the line that starts first
        last = j if b0 > b1 else j + 1  # the line that stops last
        eps = 1e-6  # param-ok: rounding
        before = [st for st in stations if min(a0, a1) - eps <= st.s <= lo + eps]
        after = [st for st in stations if hi - eps <= st.s <= max(b0, b1) + eps]
        ends = ((lo, first, 2 * j + 1 - first, before), (hi, last, 2 * j + 1 - last, after))
        for end_s, longer, shorter, ls in ends:
            if len(ls) < 2:
                continue
            tip = next(st for st in stations if abs(st.s - end_s) < 1e-6)
            for a, b in zip(ls, ls[1:], strict=False):
                faces.setdefault(section((a.s + b.s) / 2), []).append(
                    [pt(a, longer), pt(b, longer), pt(tip, shorter)]
                )
        for k in sorted(faces):
            pieces.append(Piece(f"top-{k}-{j + 1}", faces[k]))
    for k, (c0, c1) in enumerate(zip(cuts, cuts[1:], strict=False), start=1):
        sec = [st for st in stations if c0 - 1e-6 <= st.s <= c1 + 1e-6]  # param-ok: rounding
        for name, j in (("back", 0), ("front", rows - 1)):  # the walls
            faces_w = [[pt(a, j, True), pt(b, j, True), pt(b, j), pt(a, j)]
                       for a, b in zip(sec, sec[1:], strict=False)]  # fmt: skip
            pieces.append(Piece(f"{name}-{k}", faces_w))
    full = [j for j in range(rows) if spans[j][0] <= 1e-6 and spans[j][1] >= total - 1e-6]
    for side, st, at in (("start", stations[0], 0), ("end", stations[-1], 1)):
        pr = _at(profiles, st.s)
        pieces += _end(p, side, st, pr[full] if len(full) < rows else pr)
        if len(full) < rows:  # the hip's end face: the ends of the lines that stop early
            tips = []
            for j in range(rows):
                s_end = spans[j][at]
                tip = next(x for x in stations if abs(x.s - s_end) < 1e-6)
                tips.append(pt(tip, j))
            cap = [[tips[0], tips[i], tips[i + 1]] for i in range(1, rows - 1)]
            pieces.append(Piece(f"{side}-hip", cap))
    _check_widths(pieces, roll_mm)
    return conform(pieces)


def _spans(p: dict[str, Any], stations: list[Station], profiles: list[tuple[float, np.ndarray]],
           rows: int) -> list[tuple[float, float]]:  # fmt: skip
    """Where each line along the cover starts and stops (cm along the back edge). A line that is
    shorter than the cover (`line_lengths_cm`) stops early at both ends, evenly: a hipped end."""
    total = stations[-1].s
    want = list(p.get("line_lengths_cm") or [None] * rows)
    out = []
    for j in range(rows):
        if j >= len(want) or want[j] in (None, 0):
            out.append((0.0, total))
            continue
        pts = np.array([[*_xyz(st, _at(profiles, st.s)[j, 0], _at(profiles, st.s)[j, 1])]
                        for st in stations]) / MM  # fmt: skip
        cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
        trim = max(0.0, (cum[-1] - float(want[j])) / 2)
        s = np.array([st.s for st in stations])
        out.append((float(np.interp(trim, cum, s)), float(np.interp(cum[-1] - trim, cum, s))))
    return out


def _check_bends(p: dict[str, Any], profiles: list[tuple[float, np.ndarray]]) -> None:
    """A curve towards the front must be wider than the cover is deep, or the front edge would
    cross itself (the inside of a U folding over): say so, with the numbers."""
    deepest = max(float(q[:, 0].max()) for _, q in profiles)
    for seg in p.get("path") or []:
        if "arc" in seg and float(seg["angle"]) > 0 and float(seg["arc"]) <= deepest:
            raise CoverError(
                f"an arc of radius {float(seg['arc']):g} cm bends towards the front, but the cover "
                f"is {deepest:g} cm deep: the front edge would cross itself (radius must be larger)"
            )


def _line_lengths(
    p: dict[str, Any], stations: list[Station], profiles: list[tuple[float, np.ndarray]]
) -> list[float]:
    """How long each line along the cover is (cm): as written for a hip, else along the path."""
    want = list(p.get("line_lengths_cm") or [])
    out = []
    for j in range(len(profiles[0][1])):
        if j < len(want) and want[j]:
            out.append(float(want[j]))
            continue
        pts = np.array([st.p + st.n * _at(profiles, st.s)[j, 0] for st in stations])
        out.append(float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum()))
    return out


def _narrow(
    profiles: list[tuple[float, np.ndarray]], roll_cm: float, lengths: list[float]
) -> list[tuple[float, np.ndarray]]:
    """A band across the top that fits the roll neither across nor along (turned) gets a seam in
    the middle, or more, the same in every cross-section. Along the roll a piece may be long."""
    first = profiles[0][1]
    parts = []
    for j in range(len(first) - 1):
        widest = max(float(np.hypot(*(q[j + 1] - q[j]))) for _, q in profiles)
        along = max(lengths[j], lengths[j + 1])
        parts.append(1 if min(widest, along) <= roll_cm else math.ceil(widest / roll_cm))
    if all(n == 1 for n in parts):
        return profiles
    out = []
    for s, q in profiles:
        pts = [q[0]]
        for j, n in enumerate(parts):
            pts += [q[j] + (q[j + 1] - q[j]) * (i / n) for i in range(1, n + 1)]
        out.append((s, np.array(pts)))
    return out


def _spread(p: dict[str, Any], profiles: list[tuple[float, np.ndarray]]) -> list[Any]:
    """The written line lengths, for the lines a too-wide band got: the new ones run full."""
    old = list(p["line_lengths_cm"])
    first = profiles[0][1]
    out: list[Any] = [None] * len(first)
    out[0], out[-1] = old[0], old[-1]
    # the original points are still in the new cross-section: match them by position
    src = _profiles({k: v for k, v in p.items() if k != "line_lengths_cm"}, 0.0)[0][1]
    for j, q in enumerate(src):
        k = int(np.argmin(np.linalg.norm(first - q, axis=1)))
        out[k] = old[j] if j < len(old) else None
    return out


def _split(cuts: list[float], longest: float) -> list[float]:
    out = [cuts[0]]
    for a, b in zip(cuts, cuts[1:], strict=False):
        parts = max(1, math.ceil((b - a) / longest - 1e-9))  # param-ok: rounding
        out += [a + (b - a) * i / parts for i in range(1, parts + 1)]
    return out


def _with_cuts(stations: list[Station], cuts: list[float]) -> list[Station]:
    """Stations at every cut too (interpolated on the back edge), so pieces end exactly there."""
    have = {round(st.s, 6) for st in stations}
    extra = []
    for c in cuts:
        if round(c, 6) in have:
            continue
        for a, b in zip(stations, stations[1:], strict=False):
            if a.s < c < b.s:
                t = (c - a.s) / (b.s - a.s)
                n = a.n + (b.n - a.n) * t
                extra.append(Station(c, a.p + (b.p - a.p) * t, n / np.linalg.norm(n)))
                break
    return sorted(stations + extra, key=lambda st: (st.s, not st.corner))


def _end(p: dict[str, Any], side: str, st: Station, prof: np.ndarray) -> list[Piece]:
    kind = str(p.get(f"{side}_end") or p.get("ends") or "square")
    out_dir = np.array([st.n[1], -st.n[0]]) / max(float(np.linalg.norm(st.n)), 1e-9)
    if side == "start":
        out_dir = -out_dir
    if kind == "round":  # a half-round end: the top follows the cross-section, the wall round
        d = float(prof[-1, 0])
        n = st.n / np.linalg.norm(st.n)
        centre = st.p + n * d / 2
        tops, walls = [], []
        prev = None
        for i in range(ROUND_STEPS + 1):
            phi = math.pi * i / ROUND_STEPS
            off = d / 2 - d / 2 * math.cos(phi)
            z = float(np.interp(off, prof[:, 0], prof[:, 1]))
            q = centre - n * (d / 2) * math.cos(phi) + out_dir * (d / 2) * math.sin(phi)
            on_line = st.p + n * off
            cur = (q, on_line, z)
            if prev is not None:
                (q0, l0, z0), (q1, l1, z1) = prev, cur
                tops.append([(*(l0 * MM), z0 * MM), (*(q0 * MM), z0 * MM),
                             (*(q1 * MM), z1 * MM), (*(l1 * MM), z1 * MM)])  # fmt: skip
                walls.append([(*(q0 * MM), 0.0), (*(q1 * MM), 0.0),
                              (*(q1 * MM), z1 * MM), (*(q0 * MM), z0 * MM)])  # fmt: skip
            prev = cur
        tops = [[(float(a), float(b), float(c)) for a, b, c in f] for f in tops]
        walls = [[(float(a), float(b), float(c)) for a, b, c in f] for f in walls]
        return [Piece(f"{side}-round-top", tops), Piece(f"{side}-round-wall", walls)]
    # an upright (or leaning) end wall: the cross-section closed down to the ground
    lean = math.tan(math.radians(float(p.get("end_angle_deg") or 0))) if kind == "angled" else 0
    pts = [(float(o), 0.0) for o in (prof[-1, 0],)] + [(float(o), float(z)) for o, z in prof[::-1]]
    pts.append((0.0, 0.0))
    face = []
    for o, z in pts:
        q = st.p + st.n * o - out_dir * o * lean
        face.append((float(q[0]) * MM, float(q[1]) * MM, z * MM))
    return [Piece(f"{side}-end", [face])]


def _check_widths(pieces: list[Piece], roll_mm: float) -> None:
    """Every piece must fit the roll in its narrowest direction (it may be turned, and be as long
    as it likes along the roll): its smaller extent across its own surface."""
    for pc in pieces:
        pts = np.array([v for f in pc.faces for v in f], dtype=float)
        if len(pts) < 3:  # noqa: PLR2004 - a triangle at least
            continue
        c = pts - pts.mean(axis=0)
        _, _, vt = np.linalg.svd(c, full_matrices=False)
        extents = sorted(float(np.ptp(c @ v)) for v in vt[:2])
        if extents[0] > roll_mm:
            raise CoverError(
                f"{pc.name} is {extents[0] / MM:.0f} cm in its narrowest direction, wider than "
                "the roll: it needs a seam the drawing does not show"
            )
