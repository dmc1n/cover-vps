"""Drawing covers built in staging from a shape a person read from the drawing (drawing_given).

    uv run python scripts/given_build.py OUT --shapes testdata/drawing_shapes [--only a,b]
        [--models /home/dev/cover-pattern-engine/models] [--workers 2]

For each SHAPES/<model>.json: the live model folder is copied to OUT/<model>/ (without its
revisions; models/ is only read), the shape is written there as drawing_shape.json and the cover
is built from its own reference.pdf by `cover drawing-build` (route A, reader "given"). One line
per cover in OUT/build.json.
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


def _pieces(model: Path) -> int | None:
    fin = model / "finished.json"
    if not fin.is_file():
        return None
    return sum(
        1 for p in json.loads(fin.read_text())["pieces"] if not p["name"].startswith("vent-")
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--shapes", type=Path, default=Path("testdata/drawing_shapes"))
    ap.add_argument("--models", type=Path, default=Path("/home/dev/cover-pattern-engine/models"))
    ap.add_argument("--only")
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    only = set(a.only.split(",")) if a.only else None
    jobs = []
    for f in sorted(a.shapes.glob("*.json")):
        name = f.stem
        if only and name not in only:
            continue
        src, dst = a.models / name, a.out / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("revisions", "desk-cache"))
        for stale in ("check.json", "drawing_read.json", "drawing-surface.glb"):
            (dst / stale).unlink(missing_ok=True)
        shutil.copyfile(f, dst / "drawing_shape.json")
        desk = src / "desk.json"
        info = json.loads(desk.read_text()) if desk.is_file() else {}
        code = info.get("code")
        pdf = dst / "reference.pdf"
        if not pdf.is_file() and info.get("pdf"):
            pdf = Path(info["pdf"])
        cmd = [sys.executable, "-m", "coverengine.cli", "drawing-build", str(dst),
               "--pdf", str(pdf)] + (["--code", code] if code else [])  # fmt: skip
        jobs.append((name, cmd))

    def run(job: tuple[str, list[str]]) -> dict[str, Any]:
        name, cmd = job
        t = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, check=False)
        (a.out / f"{name}.log").write_text(r.stdout + "\n--- stderr\n" + r.stderr)
        res = {"model": name, "rc": r.returncode, "s": round(time.time() - t),
               "pieces": _pieces(a.out / name)}  # fmt: skip
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
