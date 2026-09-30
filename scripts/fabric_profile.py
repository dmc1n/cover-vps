"""Turn swatch measurements into a fabric profile (docs/CALIBRATION.md, M8).

    uv run python scripts/fabric_profile.py testdata/fabrics/acrylic-300.measurements.json

reads the measurements (fill in a copy of `testdata/fabrics/measurements.template.json`) and
writes `testdata/fabrics/<fabric>.json` with `status: measured`. It prints the smallest weld
radius to put in `config/defaults.yaml` (`seams.min_weld_radius_mm`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

GAUGE_MM = 200.0  # the marked gauge length on every strip


def profile(m: dict[str, Any]) -> dict[str, Any]:
    def pct(lengths: list[float]) -> float:
        return round(mean((x - GAUGE_MM) / GAUGE_MM * 100 for x in lengths), 3)

    def shrink(w: dict[str, Any]) -> float:
        before = float(w["before_mm"])
        return round(mean((before - float(a)) / before * 100 for a in w["after_mm"]), 3)

    for key in ("fabric", "stretch_mm", "weld", "thickness_mm"):
        if key not in m:
            raise ValueError(f"measurements: missing {key!r}")
    return {
        "format_version": 1,
        "id": m["fabric"],
        "name": m.get("name", m["fabric"]),
        "status": "measured",
        "stretch_pct": {d: pct(m["stretch_mm"][d]) for d in ("warp", "weft", "bias")},
        "permanent_set_pct": {d: pct(v) for d, v in m.get("relaxed_mm", {}).items()},
        "weld_shrinkage_pct": {d: shrink(m["weld"][d]) for d in ("along", "across")},
        "thickness_mm": round(mean(float(t) for t in m["thickness_mm"]), 3),
        "min_weld_radius_mm": m.get("min_weld_radius_mm"),
        "source": (
            f"swatch tests {m.get('date', '?')}, roll batch {m.get('roll_batch', '?')}, "
            f"load {m.get('load_kg', '?')} kg (docs/CALIBRATION.md)"
        ),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    src = Path(argv[0])
    doc = profile(json.loads(src.read_text(encoding="utf-8")))
    out = src.parent / f"{doc['id']}.json"
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"profile -> {out}")
    print(
        f"  stretch % warp {doc['stretch_pct']['warp']}, weft {doc['stretch_pct']['weft']}, "
        f"bias {doc['stretch_pct']['bias']}"
    )
    print(
        f"  weld shrinkage % along {doc['weld_shrinkage_pct']['along']}, "
        f"across {doc['weld_shrinkage_pct']['across']}"
    )
    if doc["min_weld_radius_mm"]:
        print(
            f"  set seams.min_weld_radius_mm: {doc['min_weld_radius_mm']} in config/defaults.yaml"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
