"""Fewer pieces on the drawing covers: neighbours without a real crease joined (ADR-076).

    uv run python scripts/drawing_merge.py [--only drawing-s43,...] [--dry-run] [--workers 3]

For every models/drawing-*/: its own parts (model.glb) are joined by coverengine.drawn_merge
(fold under drawn.merge_fold_deg, flat within drawn.merge_max_stretch_pct, fits the roll). When
that gives fewer pieces, the joined surface replaces the cover's surface in its own folder and
the cover is calculated again as a new revision (the shape is the same; only seams go). Out:
out/drawings/merge.json, one row per cover with the pieces before and after.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coverengine.drawn_merge import merge, model_parts  # noqa: E402
from coverengine.params import Registry  # noqa: E402
from drawing_cover import roll_mm  # noqa: E402


def merged_scene(parts: list[tuple[str, trimesh.Trimesh]]) -> trimesh.Scene:
    sc = trimesh.Scene()
    for name, m in parts:
        sc.add_geometry(m, node_name=name, geom_name=name)
    return sc


def one(model: Path, dry: bool) -> dict[str, Any]:
    params = Registry.load(None).resolve()
    parts = model_parts(model / "model.glb")
    out = merge(parts, roll_mm(), float(params["drawn.merge_fold_deg"]),  # type: ignore[arg-type]
                float(params["drawn.merge_max_stretch_pct"]))  # type: ignore[arg-type]  # fmt: skip
    res: dict[str, Any] = {"model": model.name, "before": len(parts), "after": len(out)}
    if len(out) >= len(parts):
        res["status"] = "kept: nothing to join"
        return res
    if dry:
        res["status"] = "would join (dry run)"
        return res
    src = Path("out/drawn") / f"{model.name}-merged.glb"
    src.parent.mkdir(parents=True, exist_ok=True)
    merged_scene(out).export(src)
    from drawing_rebuild import replace_live

    doc = json.loads((model / "cover.json").read_text())
    note = (doc.get("notes") or "") + (f" | Pieces joined where there is no crease (ADR-076): "
                                       f"{len(parts)} -> {len(out)} parts.")  # fmt: skip
    keep = doc.get("parameters", {})
    res["status"] = replace_live(model, src, keep, note)
    if res["status"] == "replaced":
        res["status"] = "joined"
        fin = json.loads((model / "finished.json").read_text())
        res["pieces_now"] = sum(1 for p in fin["pieces"] if not p["name"].startswith("vent-"))
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--one", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.one:  # a child process: one cover (the geometry libraries are not thread safe)
        print(json.dumps(one(Path("models") / a.one, a.dry_run)), flush=True)
        return 0
    names = (
        a.only.split(",") if a.only else sorted(p.name for p in Path("models").glob("drawing-*"))
    )

    def child(name: str) -> dict[str, Any]:
        args = [sys.executable, __file__, "--one", name] + (["--dry-run"] if a.dry_run else [])
        r = subprocess.run(args, capture_output=True, text=True, timeout=3600, check=False)
        try:
            res = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            tail = (r.stderr.strip().splitlines() or ["?"])[-1]
            res = {"model": name, "status": f"failed: {tail[-200:]}"}
        print(res["model"], res["status"], res.get("before"), "->", res.get("after"), flush=True)
        return res

    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        rows = list(pool.map(child, names))
    Path("out/drawings").mkdir(parents=True, exist_ok=True)
    Path("out/drawings/merge.json").write_text(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
