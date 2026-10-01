"""Build one of the owner's drawings as a cover model and calculate it (ADR-046).

    uv run python scripts/drawing_cover.py <code> <shape> '<sizes as JSON, in cm>'

The cover surface goes to models/drawing-<code>/ as one part per piece, recognised as a cover
surface, then cut, flattened and exported like any model.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from coverengine.catalogue import set_info
from coverengine.cli import main as cover
from coverengine.drawn import build, scene
from coverengine.io.kind import confirm
from coverengine.params import Registry

STEPS = ("hull", "cut", "flatten", "export", "preview")


def make(code: str, shape: str, sizes: dict, models: Path, note: str = "") -> Path:
    params = Registry.load(None).resolve()
    roll = float(params["roll.usable_width_mm"]) - 2 * float(params["stitching.allowance_mm"])
    pieces = build(shape, sizes, roll)
    model = models / ("drawing-" + re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-"))
    src = models.parent / "out" / "drawn" / f"{model.name}.glb"
    src.parent.mkdir(parents=True, exist_ok=True)
    scene(pieces).export(src)
    if cover(["import", str(src), "--out", str(model), "--units", "mm", "--up", "z"]):
        raise SystemExit(f"{code}: import failed")
    confirm(model, "cover")
    set_info(
        model,
        {
            "status": "draft",
            "tags": ["drawing", "reference"],
            "notes": f"Drawing {code}: {shape}, built from the drawing's sizes {json.dumps(sizes)}"
            + (f". {note}" if note else ""),
        },
    )
    for step in STEPS:
        if cover([step, str(model)]):
            raise SystemExit(f"{code}: {step} failed")
    return model


if __name__ == "__main__":
    make(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), Path("models"))
