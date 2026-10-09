"""An independent re-measure of a built cover, from its exported files (ADR-097).

    uv run python scripts/fewer_check.py MODEL_DIR [MODEL_DIR ...] [--vents N] [--json OUT]

It does not trust the engine's own summary; it measures again:

- cut.dxf: every closed outline on the CUT layer; the pieces are the outlines not inside
  another, the openings (vents) those inside one. Each piece's width in its narrowest
  direction (minimum rotated rectangle) against roll.usable_width_mm.
- pattern.json + panels.npz: each seam's length on both pieces, from the flat outlines' own
  points, against each other (seams.seam_tolerance_mm, or the ease the engine recorded) and
  against the seam's length on the 3D surface (panels.npz seam edges).
- the net area of each flat piece against its 3D area (flattening keeps area).
- the openings: as many as the drawing says; on a piece standing more than
  features.vent_inner_mm inside the footprint's convex hull (an inner wall) only when the
  cover's `features.vent_inner_walls` allows it (on by default: owner, 9 Oct 2026, ADR-110).

Prints one line per cover, `PASS` or `FAIL` with the reasons.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from coverengine.params import Registry

AREA_TOL = 0.02  # flat area within 2 % of the 3D area
SEAM_3D_TOL = 0.01  # a flat seam within 1 % (or 3 mm) of its 3D length
SEAM_3D_MM = 3.0


def _closed_outlines(dxf: Path) -> list[np.ndarray]:
    import ezdxf

    out = []
    for e in ezdxf.readfile(dxf).modelspace():
        if e.dxf.layer != "CUT":
            continue
        if e.dxftype() == "LWPOLYLINE":
            pts = np.array([(p[0], p[1]) for p in e.get_points()])
        elif e.dxftype() == "POLYLINE":
            pts = np.array([(v.dxf.location[0], v.dxf.location[1]) for v in e.vertices])
        else:
            continue
        if len(pts) >= 3:
            out.append(pts)
    return out


def check(model: Path, vents_expected: int | None) -> dict[str, Any]:
    import shapely

    params = Registry.load(None).resolve()
    roll = float(params["roll.usable_width_mm"])
    tol = float(params["seams.seam_tolerance_mm"])
    inner_mm = float(params["features.vent_inner_mm"])
    bad: list[str] = []
    notes: list[str] = []

    # --- the cut file
    polys = [shapely.Polygon(p).buffer(0) for p in _closed_outlines(model / "cut.dxf")]
    inside = [
        any(
            j != i
            and polys[j].contains(polys[i].representative_point())
            and polys[j].area > polys[i].area
            for j in range(len(polys))
        )
        for i in range(len(polys))
    ]
    pieces = [p for p, ins in zip(polys, inside, strict=True) if not ins]
    openings = sum(inside)
    widths = []
    for p in pieces:
        r = np.asarray(p.minimum_rotated_rectangle.exterior.coords)[:4]
        widths.append(min(np.linalg.norm(r[1] - r[0]), np.linalg.norm(r[2] - r[1])))
    fin = json.loads((model / "finished.json").read_text())
    named = [q for q in fin["pieces"]]
    n_cut = sum(int(q["quantity"]) for q in named)
    n_pieces = sum(1 for q in named if not q["name"].startswith("vent-"))
    if len(pieces) != n_cut:
        notes.append(f"cut.dxf has {len(pieces)} outlines, finished.json {n_cut} (with quantities)")
    if widths and max(widths) > roll:
        bad.append(f"a piece is {max(widths):.0f} mm wide in its narrowest direction (> {roll:g})")

    # --- seams: both sides, and the 3D length
    pat = json.loads((model / "pattern.json").read_text())
    sides: dict[str, list[tuple[str, float]]] = defaultdict(list)
    ease = {}
    for pan in pat["panels"]:
        out = np.asarray(pan["outline_mm"], dtype=float)
        n = len(out)
        for e in pan["edges"]:
            if e["kind"] != "seam":
                continue
            a, b = e["range"]
            idx = [(a + j) % n for j in range((b - a) % n + 1)]
            length = float(np.linalg.norm(np.diff(out[idx], axis=0), axis=1).sum())
            sides[e["seam"]].append((pan["name"], length))
            if e.get("ease_mm"):
                ease[e["seam"]] = abs(float(e["ease_mm"]))
    for w in pat["warnings"]:
        if "recorded as ease" in w:
            sid = w.split("seam ")[1].split(":")[0]
            ease[sid] = max(ease.get(sid, 0.0), float(w.split("differ by ")[1].split(" mm")[0]))
    npz = np.load(model / "panels.npz")
    cut = json.loads((model / "panels.json").read_text())
    vtx = np.asarray(npz["vertices"])
    orig = np.asarray(npz["original_vertex"])
    pts = np.zeros((int(orig.max()) + 1, 3))
    pts[orig] = vtx
    l3: dict[int, float] = defaultdict(float)
    for (a, b), i in zip(npz["seam_edges"], npz["seam_index"], strict=True):
        l3[int(i)] += float(np.linalg.norm(pts[a] - pts[b]))
    seam_ids = [s["id"] for s in cut["seams"]]
    worst_pair, worst_3d = 0.0, 0.0
    for sid, both in sides.items():
        total = defaultdict(float)
        for name, length in both:
            total[name] += length
        if len(total) != 2:  # param-ok: a seam has two sides
            notes.append(f"seam {sid} has {len(total)} sides")
            continue
        la, lb = total.values()
        d = abs(la - lb)
        worst_pair = max(worst_pair, d)
        if d > tol + 0.05 and d > ease.get(sid, 0.0) + 0.5:
            bad.append(f"seam {sid}: sides {la:.1f} / {lb:.1f} mm, no ease recorded")
        if sid in seam_ids:
            t = l3[seam_ids.index(sid)]
            if t > 0:
                dd = max(abs(la - t), abs(lb - t))
                worst_3d = max(worst_3d, dd / t)
                if dd > max(SEAM_3D_MM, SEAM_3D_TOL * t):
                    bad.append(f"seam {sid}: flat {la:.0f}/{lb:.0f} mm against {t:.0f} mm in 3D")

    # --- area: flat against 3D
    faces, labels = np.asarray(npz["faces"]), np.asarray(npz["labels"])
    tri = vtx[faces]
    a3 = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1) / 2
    worst_area = 0.0
    for k, pan in enumerate(pat["panels"]):
        flat = shapely.Polygon(pan["outline_mm"]).area
        three = float(a3[labels == k].sum())
        if three > 0:
            r = abs(flat / three - 1)
            worst_area = max(worst_area, r)
            if r > AREA_TOL:
                bad.append(
                    f"{pan['name']}: flat area {flat / 1e6:.3f} m2 against "
                    f"{three / 1e6:.3f} m2 in 3D"
                )

    # --- stretch: every piece flattened again, with the other energy (ARAP, not the engine's
    #     SLIM), over the same share of its area
    from coverengine.flatten.pattern import _panel_mesh
    from coverengine.flatten.solve import flatten, singular_values

    limit = float(params["fabric.max_allowed_stretch_pct"])
    share = float(params["flatten.stretch_quantile"])
    worst_stretch, worst_name = 0.0, ""
    for k, pan in enumerate(pat["panels"]):
        mesh, _ = _panel_mesh(vtx, faces[labels == k])
        fl = flatten(
            mesh,
            "arap",
            int(params["flatten.iterations"]),
            float(params["flatten.slim_tolerance"]),
            int(params["flatten.max_triangles"]),
        )
        s1, s2, ar = singular_values(fl.vertices, fl.faces, fl.uv)
        w = np.maximum(s1 - 1, 1 - s2) * 100
        o = np.argsort(w)
        cum = np.cumsum(ar[o]) / max(float(ar.sum()), 1e-12)
        q = float(w[o][min(int(np.searchsorted(cum, share)), len(o) - 1)])
        if q > worst_stretch:
            worst_stretch, worst_name = q, pan["name"]
    if worst_stretch > limit:
        bad.append(f"{worst_name} stretches {worst_stretch:.2f} % (ARAP; limit {limit:g} %)")

    # --- vents: the count, and on an inner wall only where the cover allows it
    hull_xy = shapely.MultiPoint(vtx[:, :2]).convex_hull.exterior
    names = [p["name"] for p in cut["panels"]]
    on_inner = []
    for q in fin["pieces"]:
        if not q.get("openings_mm"):
            continue
        k = names.index(q["name"]) if q["name"] in names else -1
        if k < 0:
            continue
        c = vtx[faces[labels == k]].reshape(-1, 3)[:, :2]
        far = np.array(
            [hull_xy.distance(shapely.Point(x, y)) for x, y in c[:: max(1, len(c) // 200)]]
        )
        if float(np.mean(far >= inner_mm)) >= 0.5:  # param-ok: half or more inside
            on_inner.append(q["name"])
    vents = sum(len(q.get("openings_mm") or []) for q in fin["pieces"])
    if openings != vents:
        notes.append(f"cut.dxf has {openings} openings, finished.json {vents}")
    if vents_expected is not None and vents != vents_expected:
        bad.append(f"{vents} vents, the drawing says {vents_expected}")
    feats = {}
    if (model / "cover.json").is_file():
        feats = (
            json.loads((model / "cover.json").read_text()).get("parameters", {}).get("features", {})
        )
    try:  # the cover's own switch, else the company default (owner, 9 Oct 2026: on; ADR-110)
        from coverengine.params.registry import resolve_model

        inner_ok = bool(resolve_model(model)["features.vent_inner_walls"])
    except Exception:  # noqa: BLE001 - a staged folder without a readable cover.json
        inner_ok = bool(feats.get("vent_inner_walls", params["features.vent_inner_walls"]))
    if on_inner and inner_ok:
        notes.append("vents on the front (inner) walls: " + ", ".join(on_inner))
    elif on_inner:
        bad.append("vents on an inner wall: " + ", ".join(on_inner))
    # no vent hangs high up a wall (C24: from a free top edge, upside down; ADR-101)
    v3 = model / "vents.json"
    if v3.is_file() and feats.get("vent_align", "bottom") == "bottom":
        low = float(vtx[:, 2].min())
        reach = (float(params["features.vent_above_hem_mm"]) * 2
                 + float(params["features.vent_min_height_mm"])
                 + float(params["stitching.allowance_mm"]))  # fmt: skip
        high = [f"{x['piece']} at {min(c[2] for c in x['corners_mm']) / 10:.0f} cm"
                for x in json.loads(v3.read_text())["vents"]
                if min(c[2] for c in x["corners_mm"]) - low > reach]  # fmt: skip
        if high:
            bad.append("vents high up a wall: " + ", ".join(high))

    res = {
        "model": model.name,
        "pass": not bad,
        "pieces": n_pieces,
        "dxf_pieces": len(pieces),
        "widest_mm": round(max(widths), 1) if widths else None,
        "vents": vents,
        "dxf_openings": openings,
        "worst_seam_pair_mm": round(worst_pair, 2),
        "worst_seam_3d_pct": round(worst_3d * 100, 2),
        "worst_area_pct": round(worst_area * 100, 2),
        "worst_stretch_arap_pct": round(worst_stretch, 2),
        "worst_stretch_piece": worst_name,
        "problems": bad,
        "notes": notes,
    }
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+", type=Path)
    ap.add_argument("--vents", type=int)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    rows = []
    for m in a.models:
        want = a.vents
        if want is None:  # the drawing's count, as the cover keeps it (features.vents_total)
            feats = (
                json.loads((m / "cover.json").read_text()).get("parameters", {}).get("features", {})
            )
            want = feats.get("vents_total")
            places = [x for x in str(feats.get("vent_positions") or "").split(",") if x.strip()]
            if places:  # placed by hand on this cover (ADR-099)
                want = len(places)
        r = check(m, want)
        rows.append(r)
        print(
            f"{r['model']:34s} {'PASS' if r['pass'] else 'FAIL'} pieces={r['pieces']} "
            f"dxf={r['dxf_pieces']} widest={r['widest_mm']} vents={r['vents']}/{r['dxf_openings']} "
            f"pair={r['worst_seam_pair_mm']}mm 3d={r['worst_seam_3d_pct']}% "
            f"area={r['worst_area_pct']}% arap={r['worst_stretch_arap_pct']}% "
            + "; ".join(r["problems"] + r["notes"])
        )
    if a.json:
        a.json.write_text(json.dumps(rows, indent=1))
    return 0 if all(r["pass"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
