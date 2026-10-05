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

import trimesh
from coverengine.catalogue import set_info
from coverengine.cli import main as cover
from coverengine.drawn import build, scene
from coverengine.io.kind import confirm
from coverengine.params import Registry

STEPS = ("hull", "cut", "flatten", "export", "preview")


def roll_mm() -> float:
    params = Registry.load(None).resolve()
    return float(params["roll.usable_width_mm"]) - 2 * float(params["stitching.allowance_mm"])


def make(
    code: str,
    shape: str,
    sizes: dict,
    models: Path,
    note: str = "",
    middle_cord: bool = False,
    pieces: list | None = None,
    parameters: dict | None = None,
) -> Path:
    """`pieces`: already made (the drawing's own views, ADR-075) instead of built from `sizes`.
    `parameters`: merged into the cover's parameters before it is calculated."""
    if pieces is None:
        pieces = build(shape, sizes, roll_mm())
    model = models / ("drawing-" + re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-"))
    src = models.parent / "out" / "drawn" / f"{model.name}.glb"
    src.parent.mkdir(parents=True, exist_ok=True)
    sc = scene(pieces)
    if shape in ("swept", "outline", "views"):  # the program made these seams: join where no crease
        from coverengine.drawn_merge import merge

        params = Registry.load(None).resolve()
        parts = [(str(n), sc.geometry[g].copy()) for n, g in
                 ((n, sc.graph[n][1]) for n in sc.graph.nodes_geometry)]  # fmt: skip
        joined = merge(parts, roll_mm(), float(params["drawn.merge_fold_deg"]),  # type: ignore[arg-type]
                       float(params["drawn.merge_max_stretch_pct"]))  # type: ignore[arg-type]  # fmt: skip
        sc = trimesh.Scene()
        for name, m in joined:
            sc.add_geometry(m, node_name=name, geom_name=name)
    sc.export(src)
    if cover(["import", str(src), "--out", str(model), "--units", "mm", "--up", "z"]):
        raise SystemExit(f"{code}: import failed")
    confirm(model, "cover")
    if parameters:
        doc = json.loads((model / "cover.json").read_text())
        mine = doc.setdefault("parameters", {})
        for group, values in parameters.items():
            mine.setdefault(group, {}).update(values)
        (model / "cover.json").write_text(json.dumps(doc, indent=2) + "\n")
    if middle_cord:  # the drawing shows a drawstring in the middle of the cover
        doc = json.loads((model / "cover.json").read_text())
        doc.setdefault("parameters", {}).setdefault("features", {})["middle_cord"] = True
        (model / "cover.json").write_text(json.dumps(doc, indent=2) + "\n")
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
