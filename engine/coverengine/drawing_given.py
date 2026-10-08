"""Drawing covers whose shape a person read from the drawing (8 Oct 2026, Rens's rejections).

Route A (ADR-081) reads what the program can read and says "needs a person" for the rest. For
those drawings a person writes the shape down once, in the model's `drawing_shape.json`, from
the drawing's own written sizes; `cover drawing-build` then builds it like any route-A cover
(reader "given"). The file is per model: no drawing gets a special case in the code.

    {"shape": "<kind>", "params": {...}, "mirror": false, "read": "how each size was read"}

The kinds, sizes in cm, x along the back, y towards the front, z up:

- every shape of drawn.py ("box", "sloped box", "L shape", "round", "outline", "swept");
- "plan-profile": the exact top view and a profile from the back edge (ADR-084);
- "hip": a convex plan whose top is, at every point, the lowest of the profiles measured from
  each outline edge (`edges`: a class per edge, `profiles`: per class [[distance, height], ...],
  each rising and then level or falling, so each class is the lowest of straight lines). This
  is the Blocchi family (D1, D2, D5, D6, S26, S27): a back chamfer, a flat strip, a long slope
  to the front, and ends that lean in. The seams fall where one plane meets the next, so they
  are straight lines (on a round front, a cone);
- "faces": flat pieces given corner by corner (`pieces`: {name: [[[x, y, z], ...], ...]});
- "angled": two arms of one cross-section meeting at an angle (S21, an angled sofa);
- "revolve": a round cover from a side view (`profile`: [[radius, height], ...] from the hem up
  to the top; `gores`: pieces round each band). A side view alone draws a round object (U2);
- `skirt_cm` in the params of any kind: the walls cut at that height all round, a level skirt
  seam (the domain rule 13; Rens on S43, the 18 cm line on D1 and D2);
- "mirror": true on any kind mirrors it left to right (the drawings "24 & 24B are mirrored of
  each other", "S44 is S43 mirrored").
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from coverengine.drawn import MM, Face, Piece, conform
from coverengine.errors import CoverError

GIVEN_FILE = "drawing_shape.json"
FAR_CM = 1.0e4  # param-ok: a half-plane drawn as a polygon this large (cm)
AREA_MIN_CM2 = 1.0  # param-ok: a region smaller than this is a rounding left-over
SAME_DIR_DEG = 30.0  # param-ok: outline edges turning less than this are one curved side
ROUND_STEPS = 64  # param-ok: a round band as this many straight bits
ON_EDGE_CM = 1e-3  # param-ok: a corner this close to an outline edge lies on it
TWIST_MM = 1.0  # param-ok: a quad whose fourth corner lies further off its plane is twisted
SKIRT_UPRIGHT = 0.05  # param-ok: a face whose normal leans less than this from level stands up
SKIRT_SLIVER_MM = 5.0  # param-ok: a wall reaching less than this above the skirt has no upper part


def load(model_dir: Path) -> dict[str, Any] | None:
    f = model_dir / GIVEN_FILE
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None


def build(
    spec: dict[str, Any],
    roll_mm: float,
    wall_max_mm: float = 0.0,
    join: tuple[float, float] | None = None,
) -> list[Piece]:
    """The pieces of a shape a person read from the drawing. `join` (fold degrees, stretch %):
    a swept shape's own seams are joined where there is no crease (ADR-076) before the level
    skirt is cut, so the skirt seam stays."""
    from coverengine import drawn, plan_profile

    kind = str(spec.get("shape"))
    p = dict(spec.get("params") or {})
    if kind == "plan-profile":
        pieces = plan_profile.build(p, roll_mm, wall_max_mm)
    elif kind == "hip":
        pieces = hip(p, roll_mm)
    elif kind == "faces":
        pieces = faces(p)
    elif kind == "revolve":
        pieces = revolve(p, roll_mm)
    elif kind == "angled":
        pieces = angled(p, roll_mm)
    else:
        pieces = drawn.build(kind, p, roll_mm)
        if kind == "swept" and join is not None:
            pieces = _joined(pieces, roll_mm, *join)
    if p.get("skirt_cm"):
        pieces = level_skirt(pieces, float(p["skirt_cm"]) * MM, wall_max_mm)
    if spec.get("mirror"):
        pieces = mirror(pieces)
    return pieces


def _joined(pieces: list[Piece], roll_mm: float, fold_deg: float, stretch: float) -> list[Piece]:
    """The pieces joined where they meet without a crease, back as pieces (drawn coordinates:
    drawn.scene turns y round, so it is turned back here)."""
    from coverengine.drawn import scene
    from coverengine.drawn_merge import merge

    sc = scene(pieces)
    parts = [(str(n), sc.geometry[sc.graph[n][1]]) for n in sc.graph.nodes_geometry]
    out = []
    for name, m in merge(parts, roll_mm, fold_deg, stretch):
        tri = m.vertices[m.faces]
        out.append(Piece(name, [[(float(x), -float(y), float(z)) for x, y, z in t] for t in tri]))
    return out


def mirror(pieces: list[Piece]) -> list[Piece]:
    """Left and right swapped (x → -x); each face turned round so it still faces out."""
    return [Piece(p.name, [[(-x, y, z) for x, y, z in reversed(f)] for f in p.faces])
            for p in pieces]  # fmt: skip


# --- angled ----------------------------------------------------------------------------------


def angled(p: dict[str, Any], roll_mm: float = math.inf) -> list[Piece]:
    """Two arms of one cross-section meeting at an angle, the back on the outside (S21, the
    Vento angled 4-seater: the arms meet at 140 degrees). `arm_a_cm`, `arm_b_cm`: the back
    edges' lengths from the corner; `bend_deg`: how far the second arm turns from the first
    (180 minus the angle between the backs); `profile`: [[offset from the back, height], ...]
    from the back wall to the front; `end_profile` (optional): the arm ends lean in, the
    lowest of it measured from the end and the cross-section (a hipped end, S21's 10 cm).
    Each arm is a hip shape (`hip`) on its own plan, open on the mitre (the bisector), where
    the arms meet at the same heights.

    swept.py's sharp turn cannot do this when the front is on the inside of the bend: its
    stations next to the corner reach past the mitre and the pieces fold over."""
    prof = [[float(o), float(z)] for o, z in p["profile"]]
    depth = prof[-1][0]
    far = [[0.0, FAR_CM], [1.0, FAR_CM]]  # a side that never limits the top
    beta = math.radians(float(p["bend_deg"])) / 2
    out: list[Piece] = []
    for side, length, sign in (("a", float(p["arm_a_cm"]), -1.0), ("b", float(p["arm_b_cm"]), 1.0)):
        d = np.array([sign * math.cos(beta), math.sin(beta)])  # along the back, from the corner
        n = np.array([-sign * math.sin(beta), math.cos(beta)])  # towards the front
        end = d * length
        mitre = np.array([0.0, depth / math.cos(beta)])
        plan = [[0.0, 0.0], end.tolist(), (end + n * depth).tolist(), mitre.tolist()]
        ends = p.get("end_profile") or far
        spec = {"plan_cm": plan, "edges": ["back", "end", "front", "mitre"], "open": ["mitre"],
                "profiles": {"back": prof, "end": ends, "front": far}}  # fmt: skip
        for piece in hip(spec, roll_mm):
            out.append(Piece(f"{side}-{piece.name}", piece.faces))
    return conform(out)


# --- faces -----------------------------------------------------------------------------------


def faces(p: dict[str, Any]) -> list[Piece]:
    """Pieces given corner by corner. A four-cornered face whose corners are not in one plane
    (a side that leans in more at the back than at the front, D1) is the ruled patch between
    its opposite edges, as the fabric lies."""
    from coverengine.drawn import _twisted

    out = []
    for name, fs in (p.get("pieces") or {}).items():
        mine: list[Face] = []
        for f in fs:
            face = [(x * MM, y * MM, z * MM) for x, y, z in f]
            if len(face) == 4 and _off_plane(face) > TWIST_MM:  # param-ok: a quad
                mine += _twisted(str(name), face).faces
            else:
                mine.append(face)
        out.append(Piece(str(name), mine))
    if not out:
        raise CoverError("no pieces given")
    return conform(out)


def _off_plane(face: Face) -> float:
    """How far the fourth corner lies off the plane of the first three (mm)."""
    v = np.asarray(face, dtype=float)
    n = np.cross(v[1] - v[0], v[2] - v[0])
    if np.linalg.norm(n) < 1e-9:
        return 0.0
    return float(abs((v[3] - v[0]) @ n) / np.linalg.norm(n))


# --- hip -------------------------------------------------------------------------------------


def _lines(profile: list[list[float]]) -> list[tuple[float, float, int]]:
    """A rising-then-level-or-falling profile as the straight lines it is the lowest of:
    (height at 0, slope per cm, segment number)."""
    pts = np.asarray(profile, dtype=float)
    pts = pts[np.argsort(pts[:, 0])]
    if len(pts) < 2:  # param-ok: a line needs two points
        raise CoverError("a profile needs at least two points")
    out = []
    last = math.inf
    for k, ((d0, z0), (d1, z1)) in enumerate(zip(pts[:-1], pts[1:], strict=True)):
        g = (z1 - z0) / (d1 - d0)
        if g > last + 1e-9:
            raise CoverError("a hip profile must not get steeper again (it would hold water)")
        last = g
        out.append((z0 - g * d0, g, k))
    return out


def _groups(plan: np.ndarray, classes: list[str]) -> list[int]:
    """A group number per outline edge: neighbouring edges of one class that turn gently (the
    bits of a round front) are one side."""
    n = len(plan)
    d = np.roll(plan, -1, axis=0) - plan
    ang = np.degrees(np.arctan2(d[:, 1], d[:, 0]))
    group = [0] * n
    g = 0
    for i in range(1, n):
        turn = abs((ang[i] - ang[i - 1] + 180) % 360 - 180)
        if classes[i] != classes[i - 1] or turn > SAME_DIR_DEG:
            g += 1
        group[i] = g
    if n > 1 and classes[0] == classes[-1]:  # the run round the start
        turn = abs((ang[0] - ang[-1] + 180) % 360 - 180)
        if turn <= SAME_DIR_DEG and group[-1] != 0:
            last = group[-1]
            group = [0 if x == last else x for x in group]
    return group


def _planes(p: dict[str, Any]) -> tuple[np.ndarray, list[str], list[int], list[dict[str, Any]]]:
    import shapely

    plan = np.asarray(p["plan_cm"], dtype=float)
    poly = shapely.Polygon(plan)
    if not poly.exterior.is_ccw:
        plan = plan[::-1]
        # edge i runs from point i to i+1; reversed, edge i is the old edge n-2-i
        classes = [p["edges"][(len(plan) - 2 - i) % len(plan)] for i in range(len(plan))]
    else:
        classes = list(p["edges"])
    if len(classes) != len(plan):
        raise CoverError("one class per outline edge")
    if shapely.Polygon(plan).convex_hull.area - shapely.Polygon(plan).area > AREA_MIN_CM2:
        raise CoverError("a hip shape needs a convex plan")
    groups = _groups(plan, classes)
    profiles = {k: _lines(v) for k, v in p["profiles"].items()}
    open_ = set(p.get("open") or [])  # edges with no profile and no wall (a mitre)
    planes = []
    for i in range(len(plan)):
        if classes[i] in open_:
            continue
        a, b = plan[i], plan[(i + 1) % len(plan)]
        t = (b - a) / np.linalg.norm(b - a)
        n = np.array([-t[1], t[0]])  # inward for a counter-clockwise outline
        for z0, g, k in profiles[classes[i]]:
            # z = z0 + g * (n · (q - a))
            planes.append({"c": z0 - g * float(n @ a), "v": g * n, "edge": i,
                           "key": ("flat", round(z0, 3)) if abs(g) < 1e-9
                           else (classes[i], groups[i], k)})  # fmt: skip
    return plan, classes, groups, planes


def _z(planes: list[dict[str, Any]], q: np.ndarray) -> np.ndarray:
    q = np.atleast_2d(q)
    return np.min([pl["c"] + q @ pl["v"] for pl in planes], axis=0)


def _halfplane(a: np.ndarray, c: float) -> Any:
    """{q : a · q <= c} as a large polygon."""
    import shapely

    n = float(np.linalg.norm(a))
    if n < 1e-12:
        return shapely.box(-FAR_CM, -FAR_CM, FAR_CM, FAR_CM) if c >= 0 else shapely.Polygon()
    u = a / n
    base = u * (c / n)
    t = np.array([-u[1], u[0]])
    r = FAR_CM + abs(c / n)  # reaching back past the origin however far the line lies
    pts = [base + t * r, base - t * r, base - t * r - u * 2 * r, base + t * r - u * 2 * r]
    return shapely.Polygon(pts)


def hip(p: dict[str, Any], roll_mm: float = math.inf) -> list[Piece]:
    """The lowest of the edges' profiles: a region per plane where it is the lowest, joined per
    side and profile segment (flat planes of one height are one piece); walls on the outline."""
    import shapely
    from shapely.ops import unary_union

    plan, classes, groups, planes = _planes(p)
    outline = shapely.Polygon(plan)
    regions: dict[Any, list[Any]] = {}
    for i, pi in enumerate(planes):
        reg = outline
        for j, pj in enumerate(planes):
            if i == j:
                continue
            reg = reg.intersection(_halfplane(pi["v"] - pj["v"], pj["c"] - pi["c"]))
            if reg.area < AREA_MIN_CM2:
                break
        if reg.area >= AREA_MIN_CM2:
            regions.setdefault(pi["key"], []).append(reg)
    roll_cm = roll_mm / MM
    pieces: list[Piece] = []
    names: dict[str, int] = {}
    for key, regs in sorted(regions.items(), key=lambda kv: str(kv[0])):
        merged = unary_union(regs).buffer(0)
        for g in getattr(merged, "geoms", [merged]):
            if g.geom_type != "Polygon" or g.area < AREA_MIN_CM2:
                continue
            base = "top" if key[0] == "flat" else f"{key[0]}-{key[2] + 1}"
            for part in _roll_split(g.simplify(1e-6), key, planes, roll_cm):
                names[base] = names.get(base, 0) + 1
                pieces.append(Piece(f"{base}-{names[base]}", _tri(part, planes)))
    pieces += _walls(plan, classes, groups, planes, regions, set(p.get("open") or []))
    return conform(pieces)


def _roll_split(g: Any, key: Any, planes: list[dict[str, Any]], roll_cm: float) -> list[Any]:
    """A top piece wider than the roll both ways cut into strips with seams running down its
    slope (water runs along them, not across)."""
    import shapely
    from shapely.ops import split

    rect = g.minimum_rotated_rectangle
    c = np.asarray(rect.exterior.coords)[:4]
    w = min(np.linalg.norm(c[1] - c[0]), np.linalg.norm(c[2] - c[1]))
    if w <= roll_cm:
        return [g]
    v = next((pl["v"] for pl in planes if pl["key"] == key), np.zeros(2))
    fall = (
        v / np.linalg.norm(v)
        if np.linalg.norm(v) > 1e-9
        else (c[1] - c[0]) / np.linalg.norm(c[1] - c[0])
    )
    across = np.array([-fall[1], fall[0]])
    t = np.asarray(g.exterior.coords) @ across
    n = math.ceil((t.max() - t.min()) / roll_cm)
    parts = [g]
    for k in range(1, n):
        s = t.min() + (t.max() - t.min()) * k / n
        q = across * s
        line = shapely.LineString([q - fall * FAR_CM, q + fall * FAR_CM])
        parts = [x for part in parts for x in split(part, line).geoms]
    return [x for x in parts if x.area >= AREA_MIN_CM2]


def _tri(region: Any, planes: list[dict[str, Any]]) -> list[Face]:
    import shapely

    tris = shapely.constrained_delaunay_triangles(region)
    out: list[Face] = []
    for t in tris.geoms:
        xy = np.asarray(t.exterior.coords)[:3]
        z = _z(planes, xy)
        out.append(
            [(float(x * MM), float(y * MM), float(h * MM)) for (x, y), h in zip(xy, z, strict=True)]
        )
    return out


def _walls(
    plan: np.ndarray,
    classes: list[str],
    groups: list[int],
    planes: list[dict[str, Any]],
    regions: dict[Any, list[Any]],
    open_: set[str] | None = None,
) -> list[Piece]:
    """A wall per side (a group of edges), up to the top's height along the outline, with a
    corner wherever a seam of the top meets the outline; none on an open edge (a mitre)."""
    corners = [np.asarray(r.exterior.coords) for rs in regions.values() for r in rs]
    allc = np.vstack(corners) if corners else np.zeros((0, 2))
    walls: dict[int, list[Face]] = {}
    for i in range(len(plan)):
        if classes[i] in (open_ or set()):
            continue
        a, b = plan[i], plan[(i + 1) % len(plan)]
        d = b - a
        L = float(np.linalg.norm(d))
        t = (allc - a) @ d / L**2
        off = np.abs((allc - a) @ np.array([-d[1], d[0]]) / L)
        on = t[(off < ON_EDGE_CM) & (t > 0) & (t < 1)]
        ts = sorted({0.0, 1.0, *[round(float(x), 9) for x in on]})
        pts = np.array([a + d * s for s in ts])
        z = _z(planes, pts)
        face: Face = [(float(q[0] * MM), float(q[1] * MM), 0.0) for q in (pts[0], pts[-1])]
        face = [face[0], face[1]] + [
            (float(q[0] * MM), float(q[1] * MM), float(h * MM))
            for q, h in zip(pts[::-1], z[::-1], strict=True)
        ]
        walls.setdefault(groups[i], []).append(face)
    out = []
    for g, fs in sorted(walls.items()):
        i = groups.index(g)
        out.append(Piece(f"wall-{classes[i]}-{g + 1}", fs))
    return out


# --- level skirt -----------------------------------------------------------------------------


def _upright(p: Piece) -> bool:
    """A wall: every face stands upright."""
    for f in p.faces:
        v = np.asarray(f, dtype=float)
        if len(v) < 3:  # param-ok: a face needs three corners
            continue
        n = np.cross(v[1] - v[0], v[-1] - v[0])
        if np.linalg.norm(n) > 1e-9 and abs(n[2]) / np.linalg.norm(n) > SKIRT_UPRIGHT:
            return False
    return True


def _clip(face: Face, h: float, below: bool) -> Face:
    """The part of a flat face below (or above) the height h (Sutherland-Hodgman)."""
    out: Face = []
    n = len(face)
    inside = (lambda q: q[2] <= h + 1e-9) if below else (lambda q: q[2] >= h - 1e-9)  # noqa: E731
    for i in range(n):
        a, b = face[i], face[(i + 1) % n]
        if inside(a):
            out.append(a)
        if inside(a) != inside(b) and abs(b[2] - a[2]) > 1e-12:
            t = (h - a[2]) / (b[2] - a[2])
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, h))
    return _clean(out)


def level_skirt(pieces: list[Piece], h_mm: float, wall_max_mm: float = 0.0) -> list[Piece]:
    """The walls cut at one height all round (the domain rule 13, Rens on S43: "keep the skirt
    height level all round"): below it one skirt band in runs no longer than `wall_max_mm`,
    above it what is left of each wall."""
    tops: list[Piece] = []
    walls: list[Piece] = []
    for p in pieces:
        (walls if _upright(p) else tops).append(p)
    skirt: list[tuple[Face, int]] = []
    upper: dict[str, list[Face]] = {}
    for k, w in enumerate(walls):
        for f in w.faces:
            lo = _clip(f, h_mm, True)
            if len(lo) > 2:  # param-ok: a face needs three corners
                skirt.append((lo, k))
            if max(q[2] for q in f) > h_mm + SKIRT_SLIVER_MM:
                hi = _clip(f, h_mm, False)
                if len(hi) > 2:  # param-ok: a face needs three corners
                    upper.setdefault(w.name, []).append(hi)
    out = list(tops)
    out += [Piece(f"upper-{n}", fs) for n, fs in sorted(upper.items())]
    out += _skirt_runs(skirt, wall_max_mm)
    return conform(out)


def _clean(f: Face) -> Face:
    out: Face = []
    for q in f:
        if not out or math.dist(q, out[-1]) > 1e-6:
            out.append(q)
    if len(out) > 1 and math.dist(out[0], out[-1]) < 1e-6:
        out.pop()
    return out


def _floor(f: Face) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """The face's edge on the floor, as (from, to) in plan, in the face's own order."""
    n = len(f)
    for i in range(n):
        a, b = f[i], f[(i + 1) % n]
        if abs(a[2]) < 1e-6 and abs(b[2]) < 1e-6 and math.dist(a, b) > 1e-6:
            return (a[0], a[1]), (b[0], b[1])
    return None


def _skirt_runs(faces_: list[tuple[Face, int]], longest_mm: float) -> list[Piece]:
    """The skirt faces chained in order round the outline (each one's floor edge ends where the
    next begins), cut where one wall ends and the next begins (where the seams above come down,
    Rens's lines on S43), whole walls packed into runs no longer than `longest_mm`, a wall
    longer than that in equal parts; at least two runs (a closed band needs a seam)."""
    every = [(f, w, _floor(f)) for f, w in faces_]
    items = [(f, w, fl) for f, w, fl in every if fl is not None]
    extra = [f for f, _, fl in every if fl is None]  # the upper triangle of a wall quad
    if not items:
        return []
    key = lambda q: (round(q[0], 3), round(q[1], 3))  # noqa: E731
    starts: dict[tuple[float, float], list[int]] = {}
    for i, (_, _, fl) in enumerate(items):
        starts.setdefault(key(fl[0]), []).append(i)
        starts.setdefault(key(fl[1]), []).append(i)
    order: list[int] = []
    seen: set[int] = set()
    for first in range(len(items)):
        if first in seen:
            continue
        cur: int | None = first
        while cur is not None and cur not in seen:
            seen.add(cur)
            order.append(cur)
            a, b = items[cur][2]  # type: ignore[misc]
            nxt = [j for k in (key(a), key(b)) for j in starts.get(k, []) if j not in seen]
            cur = nxt[0] if nxt else None
    # start at a wall's beginning, so no run wraps round through the middle of a wall
    cut = next((i for i in range(len(order)) if items[order[i]][1] != items[order[i - 1]][1]), 0)
    order = order[cut:] + order[:cut]
    groups: list[list[int]] = []
    for i in order:
        if groups and items[groups[-1][-1]][1] == items[i][1]:
            groups[-1].append(i)
        else:
            groups.append([i])
    length = lambda idx: sum(math.dist(*items[i][2]) for i in idx)  # type: ignore[misc]  # noqa: E731
    limit = longest_mm if longest_mm > 0 else math.inf
    parts: list[list[int]] = []
    for g in groups:  # a wall longer than the limit in equal parts
        n = max(1, math.ceil(length(g) / limit)) if math.isfinite(limit) else 1
        if n == 1:
            parts.append(g)
            continue
        step = length(g) / n
        acc, chunk = 0.0, []
        for i in g:
            chunk.append(i)
            acc += math.dist(*items[i][2])  # type: ignore[misc]
            if acc >= step - 1e-6 and n > 1:
                parts.append(chunk)
                chunk, acc, n = [], 0.0, n - 1
        if chunk:
            parts.append(chunk)
    runs: list[list[int]] = []
    for part in parts:  # whole walls packed together while they fit
        if runs and length(runs[-1]) + length(part) <= limit:
            runs[-1] += part
        else:
            runs.append(list(part))
    if len(runs) < 2:  # param-ok: a closed band needs a seam
        half, acc, first_run = length(order) / 2, 0.0, []
        for i in order:
            if acc >= half:
                break
            first_run.append(i)
            acc += math.dist(*items[i][2])  # type: ignore[misc]
        runs = [first_run, [i for i in order if i not in set(first_run)]]
    run_of = {i: r for r, run in enumerate(runs) for i in run}
    out_faces: dict[int, list[Face]] = {r: [items[i][0] for i in run] for r, run in enumerate(runs)}
    vkey = lambda q: tuple(round(c, 3) for c in q)  # noqa: E731
    for f in extra:  # with the floor face it shares most corners with (its own quad)
        mine = {vkey(q) for q in f}
        best = max(order, key=lambda i: len(mine & {vkey(q) for q in items[i][0]}))
        out_faces[run_of[best]].append(f)
    out = [Piece(f"skirt-{k + 1}", fs) for k, fs in sorted(out_faces.items()) if fs]
    return out


# --- revolve ---------------------------------------------------------------------------------

SIDE_SIMPLIFY_CM = 3.0  # param-ok: a side view's outline straightened within this (a small round
#                         corner becomes the band's edge, as the fabric takes it)


def side_profile(outline_cm: np.ndarray, height_cm: float | None = None) -> list[list[float]]:
    """The profile of a round object drawn from the side only (U2, Rens: "should be
    cylindrical, the drawing is a side view"): at each height of the outline's (straightened)
    corners, half the width there is the radius; from the hem up to the top, which closes on the
    axis. `height_cm`: the written overall height, which sets the scale."""
    import shapely

    poly = shapely.Polygon(outline_cm).buffer(0)
    x0, z0, x1, z1 = poly.bounds
    k = height_cm / (z1 - z0) if height_cm else 1.0
    poly = shapely.affinity.scale(poly, k, k, origin=(x0, z0)).simplify(SIDE_SIMPLIFY_CM)
    x0, z0, x1, z1 = poly.bounds
    zs = sorted({float(z) for _, z in np.asarray(poly.exterior.coords)})

    def width(z: float) -> float:
        return float(poly.intersection(shapely.LineString([(x0 - 1, z), (x1 + 1, z)])).length)

    prof: list[list[float]] = []
    for z in zs:
        if z - z0 < SIDE_SIMPLIFY_CM:
            z, r = z0, width(z0 + SIDE_SIMPLIFY_CM) / 2
        elif z1 - z < SIDE_SIMPLIFY_CM:
            continue
        else:
            r = width(z) / 2
        if prof and math.dist(prof[-1], [r, z - z0]) < SIDE_SIMPLIFY_CM:
            continue
        prof.append([round(r, 2), round(z - z0, 2)])
    top = width(z1 - SIDE_SIMPLIFY_CM) / 2
    if math.dist(prof[-1], [top, z1 - z0]) >= SIDE_SIMPLIFY_CM:
        prof.append([round(top, 2), round(z1 - z0, 2)])
    else:
        prof[-1] = [prof[-1][0], round(z1 - z0, 2)]
    prof.append([0.0, round(z1 - z0, 2)])
    out: list[list[float]] = []
    for q in prof:  # straight runs as one band
        if len(out) >= 2:  # param-ok: a run needs two points
            (r0, h0), (r1, h1) = out[-2], out[-1]
            cross = (r1 - r0) * (q[1] - h0) - (q[0] - r0) * (h1 - h0)
            if abs(cross) < SIDE_SIMPLIFY_CM * math.dist(out[-2], q):
                out[-1] = q
                continue
        out.append(q)
    return out


def revolve(p: dict[str, Any], roll_mm: float = math.inf) -> list[Piece]:
    """A body of revolution: each straight bit of the profile a band (a cylinder or a cone,
    which lie flat), in as many gores as the roll needs (at least `gores`, at least two for a
    closed band); a flat top disc where the profile ends on the axis."""
    prof = np.asarray(p["profile"], dtype=float) * MM
    steps = int(p.get("steps") or ROUND_STEPS)
    ang = np.linspace(0, 2 * math.pi, steps + 1)
    pieces: list[Piece] = []
    for k, ((r0, z0), (r1, z1)) in enumerate(zip(prof[:-1], prof[1:], strict=True)):
        if r0 < 1e-6 and r1 < 1e-6:
            continue
        if abs(z1 - z0) < 1e-6:  # a flat ring or disc
            r_out, r_in = max(r0, r1), min(r0, r1)
            ring = [(r_out * math.cos(a), r_out * math.sin(a), z0) for a in ang[:-1]]
            if r_in < 1e-6:
                pieces.append(Piece(f"top-{k + 1}", [ring]))
                continue
        slant = math.hypot(r1 - r0, z1 - z0)
        circ = 2 * math.pi * max(r0, r1)
        n = max(int(p.get("gores") or 2), 2 if slant > roll_mm else 1)  # param-ok: a ring
        if min(slant, circ / n) > roll_mm:
            n = math.ceil(circ / roll_mm)
        n = max(n, 2)  # param-ok: a closed band needs a seam to lie flat
        cuts = np.round(np.linspace(0, steps, n + 1)).astype(int)
        for g in range(n):
            fs: list[Face] = []
            for i in range(cuts[g], cuts[g + 1]):
                a, b = ang[i], ang[i + 1]
                fs.append([(r0 * math.cos(a), r0 * math.sin(a), z0),
                           (r0 * math.cos(b), r0 * math.sin(b), z0),
                           (r1 * math.cos(b), r1 * math.sin(b), z1),
                           (r1 * math.cos(a), r1 * math.sin(a), z1)])  # fmt: skip
            pieces.append(Piece(f"band-{k + 1}-{g + 1}", [_clean(f) for f in fs]))
    return pieces
