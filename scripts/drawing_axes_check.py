"""Length and depth swapped on sloped-box drawing covers? (owner, 7 Oct 2026, S40)

    uv run python scripts/drawing_axes_check.py --pdfs <PDF folder> [--fix]

The covers read by the AI earlier (ADR-046) are sloped boxes: length along the back, depth
along the side that shows the profile. In a 3D view the AI sometimes took the one for the
other. The drawing says it without guessing: the back height and the front height stand at the
two ends of the profile, so the direction from one height dimension to the other is the depth
axis (of the two isometric axes, ±30°); the longest size along it is the depth (shorter ones
there are the strips), the longest along the other axis the length. Out: the covers whose built
length and depth are swapped; with --fix they are built again with the right ones (backup first).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coverengine.drawing_views import dimensions  # noqa: E402
from drawing_features import pdfs, slug  # noqa: E402

ISO = (30.0, 150.0)
NEAR_DEG = 12.0  # a dimension runs along an isometric axis within this


def axis_of(u: np.ndarray) -> float | None:
    ang = math.degrees(math.atan2(u[1], u[0])) % 180
    best = min(ISO, key=lambda a: abs(ang - a))
    return best if abs(ang - best) < NEAR_DEG else None


def read_axes(pdf: Path) -> dict[str, Any] | None:
    dims = dimensions(pdf)
    ups = [d for d in dims if abs(((math.degrees(math.atan2(*(d.b - d.a)[::-1]))) % 180) - 90) < 5]
    up_ids = {id(d) for d in ups}
    flat = [(d, axis_of((d.b - d.a) / d.length_pt)) for d in dims if id(d) not in up_ids]
    flat = [(d, a) for d, a in flat if a is not None]
    if len(ups) < 2 or not flat:
        return None
    hi = max(ups, key=lambda d: d.value_cm)
    lo = min(ups, key=lambda d: d.value_cm)
    by_axis: dict[float, list[float]] = {}
    for d, ax in flat:
        by_axis.setdefault(ax, []).append(d.value_cm)
    if len(by_axis) < 2:  # param-ok: both horizontal axes must be sized
        return None
    # the flat strip on top lies along the depth: the axis with the strip (two sizes, or the
    # smallest size) is the depth axis (S41: the heights stand at other corners, not the strip)
    depth_axis = max(by_axis, key=lambda a: (len(by_axis[a]), -min(by_axis[a])))
    if len(by_axis[depth_axis]) == 1:
        return None  # no strip to tell by: leave it
    along = [d.value_cm for d, a in flat if a == depth_axis]
    across = [d.value_cm for d, a in flat if a != depth_axis]
    if not along or not across:
        return None
    return {
        "depth_cm": max(along),
        "length_cm": max(across),
        "back_cm": hi.value_cm,
        "front_cm": lo.value_cm,
        "strip_cm": min(along) if len(along) > 1 else 0.0,
    }


def built(model: Path) -> dict[str, Any] | None:
    notes = str(json.loads((model / "cover.json").read_text()).get("notes") or "")
    m = re.search(r"sloped box, built from the drawing's sizes (\{.*?\})", notes)
    return json.loads(m.group(1)) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdfs", type=Path, required=True)
    ap.add_argument("--fix", action="store_true")
    a = ap.parse_args()
    found = pdfs(a.pdfs)
    swapped = []
    for code, pdf in found.items():
        model = Path("models") / slug(code)
        if not (model / "cover.json").is_file():
            continue
        sizes = built(model)
        if not sizes:
            continue
        r = read_axes(pdf)
        if not r:
            continue
        L, D = float(sizes["length_cm"]), float(sizes["depth_cm"])
        same = abs(L - r["length_cm"]) < 1 and abs(D - r["depth_cm"]) < 1
        swap = not same and abs(L - r["depth_cm"]) < 1 and abs(D - r["length_cm"]) < 1
        print(f"{code}: built {L:g} x {D:g}, drawing {r['length_cm']:g} x {r['depth_cm']:g} "
              f"-> {'ok' if same else 'SWAPPED' if swap else 'differs'}", flush=True)  # fmt: skip
        if swap:
            swapped.append((code, model, sizes, r))
    print(f"{len(swapped)} swapped")
    if a.fix:
        from drawing_cover import make  # noqa: F401 - see below

        for code, _model, sizes, _r in swapped:
            fixed = {**sizes, "length_cm": sizes["depth_cm"], "depth_cm": sizes["length_cm"]}
            print(code, "rebuild with", fixed)
            (Path("out/drawings/axes") / f"{code}.json").parent.mkdir(parents=True, exist_ok=True)
            (Path("out/drawings/axes") / f"{code}.json").write_text(json.dumps(fixed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
