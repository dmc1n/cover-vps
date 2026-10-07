"""The cover unfolded, piece by piece, with where its fabric goes (ADR-085).

The owner, 7 October 2026: "an animation from the 3D model of all panels, how they come
together and lie flat, so we also see all dimensions and where the extra lengths of fabric come
from". Three shapes of the same points, like the website's story (ADR-071, `story.py`):

- `design`: the cover as calculated, cut into its pieces;
- `apart`: every piece pulled out along its own normal, so the seams show;
- `flat`: every piece flat on a table in front of the furniture, laid on its own finished
  outline (finished.json: the net outline and the cut outline with its allowances).

With them, per piece: the net and the cut size, the net and the cut outline on the table (and
the vent openings), and where the extra fabric goes: seam allowances, the hem, ease along its
seams; plus the vent hoods and membranes, and the roll's waste. Computed on request and kept
per cover revision (`unfold/`), never in the standard run (ADR-080).

Units: metres in the viewer's frame (Y up: engine x, z, -y), like story.py. Binary layout,
little endian: design f32[n*3], apart f32[n*3], flat f32[n*3], piece u8[n], faces u32[m*3].
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from coverengine import drape as dr
from coverengine.params import EffectiveParams
from coverengine.story import FLOOR_M, MM_PER_M, _view

CACHE_DIR = "unfold"
APART_SHARE = 0.32  # param-ok: pieces move out by this share of the cover's size
TABLE_GAP_MM = 120.0  # param-ok: room between pieces on the table
TABLE_FRONT_M = 0.35  # param-ok: the table starts this far in front of the furniture
TABLE_ASPECT = (
    1.6  # param-ok: the table's rows this much longer than the square root of the cut area
)
M2_PER_MM2 = 1e-6  # param-ok: units
MM_PER_CM = 10.0  # param-ok: units
FIT_POINTS = 300  # param-ok: points of a piece used to lay it on its outline
EXTRA = ("vent-hood", "vent-membrane")


def _area(poly: Any) -> float:
    p = np.asarray(poly, dtype=np.float64)
    if len(p) < 3:  # param-ok: a polygon
        return 0.0
    x, y = p[:, 0], p[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y)) / 2)


def _key(model_dir: Path) -> str:
    h = hashlib.sha256()
    for name in ("panels.npz", "finished.json"):
        f = model_dir / name
        h.update(f.read_bytes() if f.is_file() else b"-")
    return h.hexdigest()[:16]


def _fit(uv: np.ndarray, net: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The rotation (and mirror) and shift that lay a piece's flat points on its finished net
    outline: centres matched, then the best of the turns of its main axis, scored by how close
    the outline's points come to the flat points' hull."""
    import shapely

    cu, cn = uv.mean(axis=0), net.mean(axis=0)
    a, b = uv - cu, net - cn

    def axis(p: np.ndarray) -> float:
        _, _, vt = np.linalg.svd(p, full_matrices=False)
        return math.atan2(vt[0, 1], vt[0, 0])

    hull_net = shapely.Polygon(net).buffer(0)
    best: tuple[float, np.ndarray, np.ndarray] = (math.inf, np.eye(2), cn - cu)
    base = axis(b) - axis(a)
    for mirror in (False, True):
        m = np.diag([1.0, -1.0]) if mirror else np.eye(2)
        am = a @ m.T
        base_m = axis(b) - axis(am)
        for turn in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2):
            t = (base_m if mirror else base) + turn
            r = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]]) @ m
            moved = a @ r.T + cn
            pts = shapely.MultiPoint(moved[:: max(1, len(moved) // FIT_POINTS)])
            miss = float(hull_net.symmetric_difference(pts.convex_hull).area)
            if miss < best[0]:
                best = (miss, r, cn)
    _, r, shift = best
    return r, shift - (cu @ r.T)


def _edges_split(piece: dict[str, Any], net_area: float, cut_area: float) -> dict[str, float]:
    """The cut outline's extra over the net outline, split over seam allowances and the hem in
    proportion to each edge's length times its allowance (corners are shared out the same way)."""
    seam = hem = 0.0
    for e in piece.get("edges") or []:
        band = float(e.get("length_mm") or 0) * float(e.get("allowance_mm") or 0)
        if e.get("kind") == "hem":
            hem += band
        else:
            seam += band
    extra = max(cut_area - net_area, 0.0) * M2_PER_MM2
    total = seam + hem
    if total <= 0:
        return {"seam_m2": extra, "hem_m2": 0.0}
    return {"seam_m2": extra * seam / total, "hem_m2": extra * hem / total}


def _bands(fp: dict[str, Any], net: np.ndarray, cut: np.ndarray, off: np.ndarray,
           view2: Any) -> dict[str, list[dict[str, Any]]]:  # fmt: skip
    """The allowance band (cut outline minus net outline) as polygons on the table: the hem's
    part (below the net outline's lowest edge, where a skirt's hem lies) and the seams' part."""
    import shapely

    try:
        band = shapely.Polygon(cut).buffer(0).difference(shapely.Polygon(net).buffer(0))
    except Exception:  # noqa: BLE001 - a broken outline shows no band
        return {}
    has_hem = any(e.get("kind") == "hem" for e in fp.get("edges") or [])
    lo = float(net[:, 1].min())
    hem = shapely.box(-1e7, -1e7, 1e7, lo) if has_hem else shapely.Polygon()  # param-ok: far
    parts = {"hem": band.intersection(hem), "seam": band.difference(hem)}
    out: dict[str, list[dict[str, Any]]] = {}
    for kind, g in parts.items():
        polys = [x for x in getattr(g, "geoms", [g]) if x.geom_type == "Polygon" and x.area > 1]
        # a band round a whole piece is a ring: its hole goes with it
        out[kind] = [{"outer": view2(np.asarray(x.exterior.coords)[:-1], off),
                      "holes": [view2(np.asarray(h.coords)[:-1], off) for h in x.interiors]}
                     for x in polys]  # fmt: skip
    return out


def build(model_dir: Path, params: EffectiveParams) -> tuple[dict[str, Any], bytes]:
    """The unfold for this cover, from the cache when its pieces have not changed."""
    key = _key(model_dir)
    cache = model_dir / CACHE_DIR
    meta_f, blob_f = cache / f"{key}.json", cache / f"{key}.bin"
    if meta_f.is_file() and blob_f.is_file():
        meta = json.loads(meta_f.read_text())
        meta["cached"] = True
        return meta, blob_f.read_bytes()
    meta, blob = _build(model_dir, params)
    cache.mkdir(exist_ok=True)
    for old in cache.glob("*"):
        old.unlink()
    blob_f.write_bytes(blob)
    meta_f.write_text(json.dumps(meta))
    meta["cached"] = False
    return meta, blob


def _build(model_dir: Path, params: EffectiveParams) -> tuple[dict[str, Any], bytes]:
    fin = json.loads((model_dir / "finished.json").read_text())
    pat = json.loads((model_dir / "pattern.json").read_text())
    by_name = {p["name"]: p for p in fin["pieces"]}
    ease_by = {p["name"]: sum(abs(float(e.get("ease_mm") or 0)) for e in p.get("edges") or [])
               for p in pat["panels"]}  # fmt: skip

    c = dr.cloth(model_dir, params)
    if c.flat is None:
        raise ValueError("no flat pieces")
    faces, piece, flat = c.faces, c.piece, c.flat
    keys = np.stack([faces.ravel(), np.repeat(piece, 3)], axis=1)  # param-ok: three corners
    uniq, idx = np.unique(keys, axis=0, return_inverse=True)
    idx = idx.reshape(-1, 3)  # param-ok: three corners
    uv = np.zeros((len(uniq), 2))
    uv[idx.ravel()] = flat.reshape(-1, 2)
    design_mm = c.x[uniq[:, 0]]
    ids = sorted(set(piece.tolist()))

    # the table: every piece on its own finished outline, in rows in front of the furniture
    lo3, hi3 = design_mm.min(axis=0), design_mm.max(axis=0)
    size_mm = float(np.max(hi3 - lo3))
    # rows about as long as the table is deep: a square-ish table, not one long strip
    cut_total = sum(_area(by_name[c.names[k]]["cut_mm"]) for k in ids if c.names[k] in by_name)
    row_w = max(math.sqrt(cut_total) * TABLE_ASPECT, float(params["roll.width_mm"]))  # type: ignore[arg-type]
    x0 = float(lo3[0])
    y_front = float(lo3[1]) - TABLE_FRONT_M * MM_PER_M  # engine y: the front is -y
    flat_mm = np.zeros((len(uniq), 3))
    pieces_out: list[dict[str, Any]] = []
    cx, cy, row_h = x0, y_front, 0.0
    placements: dict[str, tuple[np.ndarray, np.ndarray, float, float]] = {}
    order = sorted(ids, key=lambda k: -_area(by_name.get(c.names[k], {}).get("cut_mm") or [[0, 0]]))
    for k in order:
        name = c.names[k]
        fp = by_name.get(name)
        sel = uniq[:, 1] == k
        pts = uv[sel]
        if fp is None or not fp.get("net_mm"):
            net = pts
            cut = pts
        else:
            net = np.asarray(fp["net_mm"], dtype=np.float64)
            cut = np.asarray(fp.get("cut_mm") or net, dtype=np.float64)
        r, t = _fit(pts, net)
        local = pts @ r.T + t
        lo, hi = cut.min(axis=0), cut.max(axis=0)
        w, h = float(hi[0] - lo[0]), float(hi[1] - lo[1])
        if cx + w > x0 + row_w and cx > x0:  # a new row, further to the front
            cx, cy, row_h = x0, cy - row_h - TABLE_GAP_MM, 0.0
        off = np.array([cx - lo[0], cy - hi[1]])  # the row hangs from its top edge (towards -y)
        flat_mm[sel, :2] = local + off
        placements[name] = (off, lo, w, h)
        cx += w + TABLE_GAP_MM
        row_h = max(row_h, h)
    # the vent hoods and membranes beside the pieces
    for name in EXTRA:
        fp = by_name.get(name)
        if not fp:
            continue
        cut = np.asarray(fp["cut_mm"], dtype=np.float64)
        lo, hi = cut.min(axis=0), cut.max(axis=0)
        w, h = float(hi[0] - lo[0]), float(hi[1] - lo[1])
        if cx + w > x0 + row_w and cx > x0:
            cx, cy, row_h = x0, cy - row_h - TABLE_GAP_MM, 0.0
        placements[name] = (np.array([cx - lo[0], cy - hi[1]]), lo, w, h)
        cx += w + TABLE_GAP_MM
        row_h = max(row_h, h)

    def view2(p: np.ndarray, off: np.ndarray) -> list[list[float]]:
        q = np.column_stack([np.asarray(p, dtype=np.float64) + off, np.zeros(len(p))])
        v = _view(q)
        v[:, 1] = FLOOR_M * 2
        return v.round(4).tolist()

    totals = {"net_m2": 0.0, "seam_m2": 0.0, "hem_m2": 0.0, "vents_m2": 0.0, "cut_m2": 0.0}
    for fp in fin["pieces"]:
        name, qty = fp["name"], int(fp.get("quantity") or 1)
        if name not in placements:
            continue
        off, lo, w, h = placements[name]
        net = np.asarray(fp.get("net_mm") or fp["cut_mm"], dtype=np.float64)
        cut = np.asarray(fp["cut_mm"], dtype=np.float64)
        net_a, cut_a = _area(net), _area(cut)
        is_extra = name in EXTRA
        split = {"seam_m2": 0.0, "hem_m2": 0.0} if is_extra else _edges_split(fp, net_a, cut_a)
        nlo, nhi = net.min(axis=0), net.max(axis=0)
        item = {
            "name": name, "quantity": qty, "extra": is_extra,
            "net_cm": [round(float(v) / MM_PER_CM, 1) for v in nhi - nlo],
            "cut_cm": [round(w / MM_PER_CM, 1), round(h / MM_PER_CM, 1)],
            "net_m2": round(0.0 if is_extra else net_a * M2_PER_MM2, 4),
            "cut_m2": round(cut_a * M2_PER_MM2, 4),
            "seam_m2": round(split["seam_m2"], 4), "hem_m2": round(split["hem_m2"], 4),
            "ease_cm": round(ease_by.get(name, 0.0) / MM_PER_CM, 1),
            "net": [] if is_extra else view2(net, off), "cut": view2(cut, off),
            "openings": [view2(o, off) for o in fp.get("openings_mm") or []],
            "bands": {} if is_extra else _bands(fp, net, cut, off, view2),
            "label_at": view2(np.array([[lo[0] + w / 2, lo[1] + h / 2]]), off)[0],
        }  # fmt: skip
        pieces_out.append(item)
        if is_extra:
            totals["vents_m2"] += cut_a * M2_PER_MM2 * qty
        else:
            totals["net_m2"] += net_a * M2_PER_MM2 * qty
            totals["seam_m2"] += split["seam_m2"] * qty
            totals["hem_m2"] += split["hem_m2"] * qty
        totals["cut_m2"] += cut_a * M2_PER_MM2 * qty
    sheet = fin.get("sheet") or {}
    roll_len = float(sheet.get("roll_length_mm") or 0)
    roll_w = float(params["roll.width_mm"])  # type: ignore[arg-type]
    used = roll_len * roll_w * M2_PER_MM2
    totals["fabric_m2"] = used
    totals["waste_m2"] = max(used - totals["cut_m2"], 0.0)
    totals["roll_length_m"] = roll_len / MM_PER_M
    totals = {k: round(v, 3) for k, v in totals.items()}

    # the three shapes of the same points
    design = _view(design_mm)
    centre3 = design.mean(axis=0)
    apart = design.copy()
    for k in ids:
        sel = uniq[:, 1] == k
        tri = faces[piece == k]
        n = np.cross(c.x[tri[:, 1]] - c.x[tri[:, 0]], c.x[tri[:, 2]] - c.x[tri[:, 0]]).sum(axis=0)
        nv = _view(n[None, :] * 1.0)[0]
        if np.linalg.norm(nv) < 1e-9:
            nv = design[sel].mean(axis=0) - centre3
        nv /= max(float(np.linalg.norm(nv)), 1e-9)
        if nv @ (design[sel].mean(axis=0) - centre3) < 0:
            nv = -nv
        apart[sel] += nv * APART_SHARE * size_mm / MM_PER_M
    on_table = _view(flat_mm)
    on_table[:, 1] = FLOOR_M
    meta = {
        "points": int(len(uniq)), "triangles": int(len(faces)),
        "pieces": [{"name": c.names[k], "index": int(k)} for k in ids],
        "flat": pieces_out, "totals": totals,
        "size_m": (design.max(axis=0) - design.min(axis=0)).round(3).tolist(),
    }  # fmt: skip
    blob = b"".join([
        design.astype("<f4").tobytes(), apart.astype("<f4").tobytes(),
        on_table.astype("<f4").tobytes(), uniq[:, 1].astype(np.uint8).tobytes(),
        idx.astype("<u4").tobytes(),
    ])  # fmt: skip
    return meta, blob
