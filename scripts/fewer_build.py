"""Drawing covers built again in a staging folder, never in models/ (ADR-097).

    uv run python scripts/fewer_build.py OUT --codes C27,C26 [--workers 3] [--pdfs DIR]
    uv run python scripts/fewer_build.py OUT --merge drawing-s43,... [--models models]

--codes: route A (`cover drawing-build`) from each drawing PDF ("cover NN - CODE.pdf") into
OUT/drawing-<code>/. --merge: a copy of each live drawing cover is made in OUT/<model>/ and its own
parts are joined and its slivers absorbed (drawn_merge), then calculated there (hull, cut, flatten,
export, preview). Each cover in its own process. One line per cover in OUT/build.json.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

PDFS = Path.home() / "cover-data/uploads/20261001-112212"
COPY = (
    "model.glb",
    "model.json",
    "parts.json",
    "kind.json",
    "cover.json",
    "reference.pdf",
    "drawing_features.json",
    "drawing_read.json",
    "part_edits.json",
)
STEPS = ("hull", "cut", "flatten", "export", "preview")


def _pdf(code: str, pdfs: Path) -> Path:
    hits = sorted(pdfs.glob(f"cover * - {code}.pdf"))
    if not hits:
        raise SystemExit(f"no drawing for {code} in {pdfs}")
    return hits[0]


def _pieces(model: Path) -> int | None:
    fin = model / "finished.json"
    if not fin.is_file():
        return None
    return sum(
        1 for p in json.loads(fin.read_text())["pieces"] if not p["name"].startswith("vent-")
    )


def merge_one(src: Path, out: Path, always: bool = False) -> dict[str, Any]:
    """A live cover's own parts joined and slivers absorbed, calculated in `out`."""
    import trimesh
    from coverengine.drawing_route import JOINABLE, roll_mm
    from coverengine.drawn_merge import absorb_slivers, merge, model_parts
    from coverengine.params import Registry

    out.mkdir(parents=True, exist_ok=True)
    for name in COPY:
        if (src / name).is_file():
            shutil.copyfile(src / name, out / name)
    params = Registry.load(None).resolve()
    tags = set(json.loads((src / "cover.json").read_text()).get("tags") or [])
    read = (
        json.loads((src / "drawing_read.json").read_text())
        if (src / "drawing_read.json").is_file()
        else {}
    )
    parts = model_parts(src / "model.glb")
    before = len(parts)
    stretch = float(params["drawn.merge_max_stretch_pct"])  # type: ignore[arg-type]
    joinable = read.get("reader") in JOINABLE or bool(
        tags & {"swept", "outline", "views", "isofit"}
    )
    if joinable:
        parts = merge(parts, roll_mm(params), float(params["drawn.merge_fold_deg"]), stretch)  # type: ignore[arg-type]
    parts = absorb_slivers(
        parts, float(params["seams.min_piece_width_mm"]), roll_mm(params), stretch
    )  # type: ignore[arg-type]
    res: dict[str, Any] = {
        "model": src.name,
        "parts_before": before,
        "parts_after": len(parts),
        "joinable": joinable,
    }
    if len(parts) == before and not always:
        res["status"] = "nothing to join"
        return res
    sc = trimesh.Scene()
    for n, m in parts:
        sc.add_geometry(m, node_name=n, geom_name=n)
    surf = out / "drawing-surface.glb"
    sc.export(surf)
    from coverengine.cli import main as cover

    keep = json.loads((out / "cover.json").read_text())
    if cover(["import", str(surf), "--out", str(out), "--units", "mm", "--up", "z"]):
        res["status"] = "import failed"
        return res
    from coverengine.io.kind import confirm

    confirm(out, "cover")
    (out / "cover.json").write_text(json.dumps(keep, indent=2) + "\n")
    for step in STEPS:
        if cover([step, str(out)]):
            res["status"] = f"{step} failed"
            return res
    res["status"] = "built"
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--codes")
    ap.add_argument("--merge")
    ap.add_argument("--models", type=Path, default=Path("/home/dev/cover-pattern-engine/models"))
    ap.add_argument("--pdfs", type=Path, default=PDFS)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--skip", help="with --merge all: these models not")
    ap.add_argument("--always", action="store_true", help="calculate even when nothing joins")
    ap.add_argument("--one-merge", help=argparse.SUPPRESS)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if a.one_merge:
        res = merge_one(a.models / a.one_merge, a.out / a.one_merge, a.always)
        print("RESULT " + json.dumps(res), flush=True)
        return 0
    jobs: list[tuple[str, list[str]]] = []
    for code in a.codes.split(",") if a.codes else []:
        model = a.out / f"drawing-{code.lower()}"
        if model.exists():
            shutil.rmtree(model)
        jobs.append(
            (
                model.name,
                [
                    sys.executable,
                    "-m",
                    "coverengine.cli",
                    "drawing-build",
                    str(model),
                    "--pdf",
                    str(_pdf(code, a.pdfs)),
                ],
            )
        )
    names = a.merge.split(",") if a.merge else []
    if a.merge == "all":
        skip = set(a.skip.split(",")) if a.skip else set()
        names = sorted(p.name for p in a.models.glob("drawing-*") if p.name not in skip)
    for name in names:
        if (a.out / name).exists():
            shutil.rmtree(a.out / name)
        jobs.append(
            (
                name,
                [
                    sys.executable,
                    __file__,
                    str(a.out),
                    "--models",
                    str(a.models),
                    "--one-merge",
                    name,
                ]
                + (["--always"] if a.always else []),
            )
        )

    def run(job: tuple[str, list[str]]) -> dict[str, Any]:
        name, args = job
        t = time.time()
        r = subprocess.run(args, capture_output=True, text=True, timeout=3600, check=False)
        (a.out / f"{name}.log").write_text(r.stdout + "\n--- stderr\n" + r.stderr)
        res: dict[str, Any] = {"model": name, "rc": r.returncode, "s": round(time.time() - t)}
        for line in r.stdout.splitlines():
            if line.startswith("RESULT "):
                res.update(json.loads(line[len("RESULT ") :]))
        res["pieces"] = _pieces(a.out / name)
        print(json.dumps(res), flush=True)
        return res

    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        rows = list(pool.map(run, jobs))
    old = json.loads((a.out / "build.json").read_text()) if (a.out / "build.json").is_file() else []
    keep = [r for r in old if r["model"] not in {x["model"] for x in rows}]
    (a.out / "build.json").write_text(json.dumps(keep + rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
