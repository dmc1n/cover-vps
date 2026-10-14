"""Compare a linked pair (ADR-132): the drawing's cover against the cover computed on the 3D
model of the same product, piece by piece and side by side.

    COVER_DATA_DIR=~/cover-data uv run python scripts/link_compare.py [--out out/links/compare]
        [--models DIR] [--db FILE] [--pairs drawing-d1:suns-daybed-portofino,...]

Without --pairs it compares every pair a person confirmed or chose in Covers → Links (app.db,
`links.learning_pairs`): nothing else is ever used to learn from. --pairs compares pairs named by
hand, for looking only; the report marks them "not confirmed".

Per pair, from both covers' finished.json (the sewn pieces) and hull.json:
- the cover's box (length, width, height) and the difference;
- per side of the skirt (front, back, left, right): the hem length and the skirt height;
- per top piece, matched by name (top-1 ↔ top-1), else by the nearest size: its size;
- the pieces, the vents, the fabric area, the seam length.
A mirror pair (`mirror` on the link) swaps the drawing's left and right before comparing.

Writes <out>/<drawing>__<model>.json per pair and <out>/summary.csv; reads only.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path
from typing import Any

from coverapi import links
from coverengine.staging import guard_staging_output

SIDES = ("front", "back", "left", "right")
MIRROR = {"left": "right", "right": "left"}
MM_PER_CM = 10.0  # param-ok: units


def _read(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _side(name: str, mirror: bool) -> str | None:
    m = re.match(r"skirt-(front|back|left|right)", name)
    if not m:
        return None
    s = m.group(1)
    return MIRROR.get(s, s) if mirror else s


def summary(model_dir: Path, mirror: bool = False) -> dict[str, Any]:
    """One cover's numbers, as the workshop would measure them."""
    fin = _read(model_dir / "finished.json")
    hull = _read(model_dir / "hull.json")
    pieces = fin.get("pieces") or []
    box = None
    if hull.get("bbox_mm"):
        lo, hi = hull["bbox_mm"]
        x, y, z = (float(hi[i]) - float(lo[i]) for i in range(3))
        box = [round(v / MM_PER_CM, 1) for v in (*sorted([x, y])[::-1], z)]
    sides: dict[str, dict[str, float]] = {}
    tops: dict[str, list[float]] = {}
    seam = hem = area = 0.0
    vents = 0
    for p in pieces:
        name = str(p.get("name") or "")
        q = int(p.get("quantity") or 1)
        if name.startswith("vent-hood"):
            vents += q
        if name.startswith("vent"):
            continue
        area += float(p.get("area_m2") or 0) * q
        net = p.get("net_mm") or []
        if net:
            xs, ys = [float(v[0]) for v in net], [float(v[1]) for v in net]
            size = [max(xs) - min(xs), max(ys) - min(ys)]
        else:
            size = [float(v) for v in p.get("size_mm") or [0, 0]]
        for e in p.get("edges") or []:
            length = float(e.get("length_mm") or e.get("length_3d") or 0)
            if e.get("kind") == "hem":
                hem += length * q
            elif e.get("kind") == "seam":
                seam += length * q / 2.0  # a seam has two sides
        s = _side(name, mirror)
        if s:
            hem_len = sum(
                float(e.get("length_mm") or 0)
                for e in p.get("edges") or []
                if e.get("kind") == "hem"
            )
            cur = sides.setdefault(s, {"hem_mm": 0.0, "height_mm": 0.0})
            cur["hem_mm"] += hem_len * q
            if hem_len and size:  # the band along the hem: its height is the skirt's
                h = min(size)
                cur["height_mm"] = h if not cur["height_mm"] else min(cur["height_mm"], h)
        elif name.startswith("top"):
            tops[name] = sorted(size)[::-1]
    return {
        "box_cm": box,
        "sides": sides,
        "tops": tops,
        "pieces": len(pieces),
        "vents": vents,
        "hem_mm": round(hem),
        "seam_mm": round(seam),
        "area_m2": round(area, 2),
    }


def _match_tops(a: dict[str, list[float]], b: dict[str, list[float]]) -> list[dict[str, Any]]:
    """Top pieces matched by the nearest size (the two layouts number their pieces each
    their own way), largest first; a piece without a partner is listed alone."""
    out: list[tuple[str | None, str | None]] = []
    left_a, left_b = dict(a), dict(b)
    for na, sa in sorted(left_a.items(), key=lambda kv: -kv[1][0]):
        if not left_b:
            out.append((na, None))
            continue
        nb = min(left_b, key=lambda k: sum(abs(x - y) for x, y in zip(sa, left_b[k], strict=False)))
        out.append((na, nb))
        left_b.pop(nb)
    out += [(None, nb) for nb in left_b]
    rows = []
    for na, nb in out:
        sa, sb = a.get(na or ""), b.get(nb or "")
        rows.append(
            {
                "drawing": na,
                "model": nb,
                "drawing_mm": sa,
                "model_mm": sb,
                "diff_mm": [round(y - x) for x, y in zip(sa, sb, strict=False)]
                if sa and sb
                else None,
            }
        )
    return rows


def compare(models: Path, drawing: str, model: str, mirror: bool = False) -> dict[str, Any]:
    a = summary(models / drawing, mirror)
    b = summary(models / model)
    sides = {}
    for s in SIDES:
        x, y = a["sides"].get(s), b["sides"].get(s)
        if x or y:
            sides[s] = {
                "drawing": x,
                "model": y,
                "hem_diff_mm": round(y["hem_mm"] - x["hem_mm"]) if x and y else None,
                "height_diff_mm": round(y["height_mm"] - x["height_mm"]) if x and y else None,
            }
    box_diff = (
        [round(y - x, 1) for x, y in zip(a["box_cm"], b["box_cm"], strict=True)]
        if a["box_cm"] and b["box_cm"]
        else None
    )
    return {
        "drawing": drawing,
        "model": model,
        "mirror": mirror,
        "box_cm": {"drawing": a["box_cm"], "model": b["box_cm"], "diff": box_diff},
        "sides": sides,
        "tops": _match_tops(a["tops"], b["tops"]),
        "totals": {
            k: {"drawing": a[k], "model": b[k]}
            for k in ("pieces", "vents", "hem_mm", "seam_mm", "area_m2")
        },
    }


def main() -> None:
    data = Path(os.environ.get("COVER_DATA_DIR", "~/cover-data")).expanduser()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="out/links/compare")
    ap.add_argument("--models", default=str(data / "models"))
    ap.add_argument("--db", default=str(data / "app.db"))
    ap.add_argument("--pairs", default="", help="drawing:model,... (for looking only)")
    a = ap.parse_args()
    out = Path(a.out)
    guard_staging_output(out)
    models = Path(a.models)
    if a.pairs:
        pairs = [
            {
                "drawing_id": x.split(":")[0],
                "model_id": x.split(":")[1],
                "mirror": False,
                "status": "not confirmed",
            }
            for x in a.pairs.split(",")
            if ":" in x
        ]
    else:
        pairs = links.learning_pairs(Path(a.db))
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for pr in pairs:
        r = compare(models, pr["drawing_id"], pr["model_id"], bool(pr.get("mirror")))
        r["status"] = pr["status"]
        (out / f"{pr['drawing_id']}__{pr['model_id']}.json").write_text(
            json.dumps(r, indent=1, ensure_ascii=False)
        )
        rows.append(r)
        bd = r["box_cm"]["diff"]
        print(f"{r['drawing']} ↔ {r['model']} ({r['status']}{', mirror' if r['mirror'] else ''})")
        print(f"  box drawing {r['box_cm']['drawing']} model {r['box_cm']['model']} cm, diff {bd}")
        for s, v in r["sides"].items():
            print(f"  skirt {s:5}: hem {v['hem_diff_mm']} mm, height {v['height_diff_mm']} mm")
        for t in r["tops"]:
            print(f"  {t['drawing'] or '-':8} ↔ {t['model'] or '-':8} {t['diff_mm']} mm")
        tot = r["totals"]
        print("  " + ", ".join(f"{k} {v['drawing']} → {v['model']}" for k, v in tot.items()))
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "drawing",
                "model",
                "status",
                "mirror",
                "box_diff_cm",
                "hem_mm_drawing",
                "hem_mm_model",
                "pieces_drawing",
                "pieces_model",
                "vents_drawing",
                "vents_model",
                "area_m2_drawing",
                "area_m2_model",
            ]
        )
        for r in rows:
            t = r["totals"]
            w.writerow(
                [
                    r["drawing"],
                    r["model"],
                    r["status"],
                    r["mirror"],
                    r["box_cm"]["diff"],
                    t["hem_mm"]["drawing"],
                    t["hem_mm"]["model"],
                    t["pieces"]["drawing"],
                    t["pieces"]["model"],
                    t["vents"]["drawing"],
                    t["vents"]["model"],
                    t["area_m2"]["drawing"],
                    t["area_m2"]["model"],
                ]
            )
    print(
        f"{len(rows)} pairs; written: {out}/summary.csv"
        + ("" if rows else " (no confirmed pair yet: confirm in Covers → Links, or --pairs)")
    )


if __name__ == "__main__":
    main()
