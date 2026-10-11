"""The scroll story's and the clips' extra data (ADR-120), next to hero_data.py's output.

`reel.json` in the hero data folder:

- **roll**: every finished piece of cut.dxf laid on the 152 cm roll (a simple bottom-left
  nest, as the cutting table's own nesting would), with its cut outline, its openings, its pen
  lines and labels moved there; and for every piece of the sewn cover the 2D transform that
  carries its flat pattern (`uv` in cover.npz, the seam line) onto its place inside its cut
  outline on the roll. The flat pattern is matched to its cut outline by the label the export
  writes in it ("P7 TOP-1") and then by shape: turned (and mirrored where the export mirrored
  it) to where its outline runs evenly inside the cut outline (the seam allowance).
- **vents**: every air vent of vents.json (on the designed cover) carried to the draped cover:
  its centre, the cloth's outward normal and up there, its size; for the hood in the close-ups.
- **size**: the furniture's length, depth and height (mm), for the dimension lines.

    uv run python scripts/film/reel_data.py DATA MODEL_DIR

DATA: the folder hero_data.py wrote (cover.npz, pieces.json, furniture.glb).
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon

ROLL_M = 1.52  # the fabric roll's width
EDGE_M = 0.012  # the selvedge kept free on each side
GAP_M = 0.02  # room between pieces in the nest
LABEL = re.compile(r"^P\d+\s+(.+)$")


def loops(faces: np.ndarray) -> list[list[int]]:
    """The boundary loops of a triangle set, as point indices in order."""
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    key = np.sort(e, axis=1)
    _, inv, count = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    nxt = {int(a): int(b) for (a, b), c in zip(e, count[inv], strict=True) if c == 1}
    out, seen = [], set()
    for start in list(nxt):
        if start in seen:
            continue
        loop, v = [], start
        while v not in seen and v in nxt:
            seen.add(v)
            loop.append(v)
            v = nxt[v]
        if len(loop) > 2:
            out.append(loop)
    return out


def rot(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s], [s, c]])


def register(flat: np.ndarray, cut: Polygon) -> tuple[np.ndarray, np.ndarray]:
    """A (2x2, rotation and maybe a mirror) and b with A @ p + b carrying the flat pattern's
    outline into the cut outline, its seam line evenly inside (the allowance)."""
    pc = np.array(Polygon(flat).centroid.coords[0])
    cc = np.array(cut.centroid.coords[0])
    ring = cut.exterior
    sample = flat[:: max(1, len(flat) // 160)] - pc
    best = (math.inf, np.eye(2))
    for mirror in (False, True):
        m = np.diag([-1.0, 1.0]) if mirror else np.eye(2)
        for deg in range(0, 360, 2):
            a = rot(math.radians(deg)) @ m
            q = sample @ a.T + cc
            d = np.array([ring.distance(Point(x, y)) for x, y in q])
            inside = np.array([cut.contains(Point(x, y)) for x, y in q])
            cost = float(np.std(d) + 4 * (~inside).mean())  # even allowance, all inside
            if cost < best[0]:
                best = (cost, a)
    a = best[1]
    return a, cc - a @ pc


def nest(sizes: list[tuple[float, float]]) -> list[tuple[float, float, bool]]:
    """Bottom-left placement of boxes along the roll: (x, y, turned) per box."""
    width = ROLL_M - 2 * EDGE_M
    placed: list[tuple[float, float, float, float]] = []
    out: list[tuple[float, float, bool]] = [(0.0, 0.0, False)] * len(sizes)
    order = sorted(range(len(sizes)), key=lambda i: -sizes[i][0] * sizes[i][1])
    for i in order:
        best = None
        for turned in (False, True):
            w, h = sizes[i][::-1] if turned else sizes[i]
            if h > width:
                continue
            xs = sorted({0.0} | {r[2] + GAP_M for r in placed})
            ys = sorted({0.0} | {r[3] + GAP_M for r in placed})
            for x in xs:
                for y in ys:
                    if y + h > width:
                        continue
                    if any(x < r[2] and r[0] < x + w and y < r[3] and r[1] < y + h
                           for r in placed):  # fmt: skip
                        continue
                    cand = (x + w, x, y, turned, w, h)
                    if best is None or cand[:3] < best[:3]:
                        best = cand
                    break
        assert best is not None, "a piece wider than the roll"
        _, x, y, turned, w, h = best
        placed.append((x, y, x + w, y + h))
        out[i] = (x, y + EDGE_M, turned)
    return out


def roll(data: Path) -> dict[str, Any]:
    d = dict(np.load(data / "cover.npz"))
    doc = json.loads((data / "pieces.json").read_text())
    outlines = [np.asarray(c)[:-1] if np.allclose(c[0], c[-1]) else np.asarray(c)
                for c in doc["cut"]]  # fmt: skip
    polys = [Polygon(c) for c in outlines]
    area = [p.area for p in polys]

    def owner(pt) -> int:  # the smallest outer outline holding a point
        hold = [i for i, p in enumerate(polys) if p.contains(Point(pt))]
        outer = [i for i in hold if not any(j != i and polys[j].contains(polys[i]) for j in hold)]
        pick = outer or hold
        return min(pick, key=lambda i: area[i]) if pick else -1

    outer = [i for i, p in enumerate(polys)
             if not any(j != i and q.contains(p) for j, q in enumerate(polys))]  # fmt: skip
    group = {i: i for i in outer}
    for i, p in enumerate(polys):
        if i not in group:  # an opening: belongs to the piece around it
            group[i] = min((j for j in outer if polys[j].contains(p)), key=lambda j: area[j])
    pen_of = [owner(line[0]) for line in doc["pen"]]
    text_of = [owner(t["at"]) for t in doc["text"]]
    # each sewn piece's cut outline, by the label the export writes inside it
    names = [str(n).lower() for n in d["names"]]
    piece_cut: dict[int, int] = {}
    for t, g in zip(doc["text"], text_of, strict=True):
        m = LABEL.match(t["text"].strip())
        if m and g >= 0 and m.group(1).lower() in names:
            piece_cut.setdefault(names.index(m.group(1).lower()), g)
    # the nest of the outer outlines
    boxes = {g: (outlines[g].min(axis=0), outlines[g].max(axis=0)) for g in outer}
    place = nest([tuple(boxes[g][1] - boxes[g][0]) for g in outer])
    to_roll: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for g, (x, y, turned) in zip(outer, place, strict=True):
        lo, hi = boxes[g]
        a = rot(math.pi / 2) if turned else np.eye(2)
        corners = np.array([lo, hi, [lo[0], hi[1]], [hi[0], lo[1]]]) @ a.T
        to_roll[g] = (a, np.array([x, y]) - corners.min(axis=0))

    def move(g: int, pts) -> list[list[float]]:
        a, b = to_roll[group[g]]
        return (np.asarray(pts) @ a.T + b).round(5).tolist()

    pieces = {}
    for k, g in piece_cut.items():
        sel = d["piece"] == k
        idx = np.flatnonzero(sel)
        faces = d["faces"][np.all(sel[d["faces"]], axis=1)]
        ring = max(loops(faces), key=len)
        a1, b1 = register(d["uv"][ring].astype(float), polys[g])
        a2, b2 = to_roll[g]
        pieces[str(k)] = {
            "name": names[k],
            "group": int(g),
            "A": (a2 @ a1).round(6).tolist(),
            "b": (a2 @ b1 + b2).round(6).tolist(),
            "points": int(len(idx)),
        }
    length = max(np.asarray(move(g, outlines[g]))[:, 0].max() for g in outer)
    return {
        "width": ROLL_M,
        "length": round(float(length), 4),
        "pieces": pieces,
        "cut": [
            {"group": int(group[i]), "opening": i not in outer, "line": move(i, outlines[i])}
            for i in range(len(outlines))
        ],  # fmt: skip
        "pen": [
            {"group": int(group[g]), "line": move(g, line)}
            for line, g in zip(doc["pen"], pen_of, strict=True)
            if g >= 0
        ],  # fmt: skip
        "text": [
            {
                "group": int(group[g]),
                "text": t["text"],
                "h": t["h"],
                "at": move(g, [t["at"]])[0],
                "rot": t["rot"] + (90.0 if place[outer.index(group[g])][2] else 0.0),
            }
            for t, g in zip(doc["text"], text_of, strict=True)
            if g >= 0
        ],  # fmt: skip
    }


def vents(data: Path, model: Path) -> list[dict[str, Any]]:
    path = model / "vents.json"
    if not path.is_file():
        return []
    d = dict(np.load(data / "cover.npz"))
    names = [str(n).lower() for n in d["names"]]
    design, drape = d["design"].astype(float), d["frames"][-1].astype(float)
    out = []
    for v in json.loads(path.read_text()).get("vents", []):
        c = np.asarray(v["centre_mm"]) / 1000
        sel = np.flatnonzero(d["piece"] == names.index(v["piece"].lower()))
        near = sel[np.linalg.norm(design[sel] - c, axis=1) < 0.16]
        if len(near) < 6:
            continue
        p = drape[near]
        centre = p.mean(axis=0)
        _, _, vt = np.linalg.svd(p - centre)
        n = vt[2] * np.sign(vt[2] @ np.asarray(v["normal"], float) or 1.0)
        up = np.array([0.0, 0.0, 1.0]) - n * n[2]
        up /= np.linalg.norm(up)
        # the centre on the cloth: the drape point nearest the designed centre's own point
        at = drape[near[np.argmin(np.linalg.norm(design[near] - c, axis=1))]]
        out.append({"piece": v["piece"], "centre": at.round(5).tolist(),
                    "normal": n.round(5).tolist(), "up": up.round(5).tolist(),
                    "size": (np.asarray(v["size_mm"]) / 1000).tolist()})  # fmt: skip
    return out


def size(data: Path) -> list[float]:
    m = trimesh.load(data / "furniture.glb", force="mesh")
    lo, hi = m.bounds  # glTF: Y up, metres or mm as the model was saved
    ext = hi - lo
    k = 1000.0 if ext.max() < 20 else 1.0
    return [round(float(ext[0] * k)), round(float(ext[2] * k)), round(float(ext[1] * k))]


def main(data: Path, model: Path) -> None:
    out: dict[str, Any] = {"roll": roll(data), "vents": vents(data, model), "size_mm": size(data)}
    (data / "reel.json").write_text(json.dumps(out))
    r = out["roll"]
    print(
        f"roll {r['length']:.2f} m, {len(r['pieces'])} sewn pieces placed, "
        f"{len(r['cut'])} cut lines, {len(out['vents'])} vents, size {out['size_mm']} mm"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser())
