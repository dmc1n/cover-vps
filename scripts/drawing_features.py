"""What the drawing's text says about features, put on its cover, and the cover exported again.

    uv run python scripts/drawing_features.py --pdfs <PDF folder> [--only S45,C27] [--workers 4]
        [--no-export]

For every models/drawing-<code>/ with its PDF: coverengine.drawing_vectors.features reads the
drawing (the number of air vents, where they sit, open bottom, drawstring, ...). A written
vent count goes into the cover's parameters as `features.vents_total` (it always wins over the
one-per-metre rule, owner 5 Oct 2026). Everything read is kept in drawing_features.json. Then
`cover export` and `cover preview` run again, so the cut file, the cutting list and vents.json
(the vents in 3D) follow. Out: one line per cover, and out/drawings/features.json.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from coverengine.drawing_vectors import features


def slug(code: str) -> str:
    return "drawing-" + re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-")


def pdfs(folder: Path) -> dict[str, Path]:
    return {re.sub(r"^cover \d+ - ", "", p.stem): p for p in sorted(folder.glob("*.pdf"))}


def apply(model: Path, pdf: Path) -> dict[str, Any]:
    """The drawing's features on the cover: drawing_features.json, and the written vent count
    as `features.vents_total` in cover.json (removed again when the drawing gives none)."""
    found = features(pdf)
    (model / "drawing_features.json").write_text(json.dumps(found, indent=1) + "\n")
    path = model / "cover.json"
    doc = json.loads(path.read_text())
    feats = doc.setdefault("parameters", {}).setdefault("features", {})
    before = feats.get("vents_total")
    if found["vents_total"]:
        feats["vents_total"] = int(found["vents_total"])
        feats.pop("vents_min", None)  # a hand-set minimum gives way to the drawing's number
    else:
        feats.pop("vents_total", None)
    if not feats:
        doc["parameters"].pop("features")
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return {**found, "changed": before != feats.get("vents_total")}


def cover(*args: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "coverengine.cli", *args], capture_output=True,
                       text=True, check=False)  # fmt: skip
    return r.returncode, (r.stderr.strip().splitlines() or r.stdout.strip().splitlines() or [""])[
        -1
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdfs", type=Path, required=True)
    ap.add_argument("--models", type=Path, default=Path("models"))
    ap.add_argument("--only")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-export", action="store_true")
    a = ap.parse_args()
    found = pdfs(a.pdfs)
    codes = a.only.split(",") if a.only else list(found)

    def one(code: str) -> dict[str, Any]:
        model = a.models / slug(code)
        if code not in found or not (model / "cover.json").is_file():
            return {"code": code, "status": "no model"}
        res: dict[str, Any] = {"code": code, "model": model.name, **apply(model, found[code])}
        if not a.no_export:
            for step in ("export", "preview"):
                rc, last = cover(step, str(model))
                if rc:
                    res["status"] = f"{step} failed: {last[-200:]}"
                    break
            else:
                res["status"] = "exported"
        print(code, res.get("status", "read"), "vents", res["vents_total"], flush=True)
        return res

    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        rows = list(pool.map(one, codes))
    out = Path("out/drawings")
    out.mkdir(parents=True, exist_ok=True)
    (out / "features.json").write_text(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
