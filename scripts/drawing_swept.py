"""The owner's free-form drawings (curved, U-shaped, tapered, angled) as cover models (ADR-068).

    uv run python scripts/drawing_swept.py out/drawings/swept --pdfs <PDF folder> [--only S24,C26]
        [--codes-from out/drawings/covers-and-all/covers.json] [--rounds 3] [--no-build]

For each drawing: Gemini (ai.vision_*) reads all its pages into the swept shape (a cross-section
along a path; coverengine/swept.py). The program builds it and measures every length a drawing
can show (each seam line along the cover, per piece and in total; the cross-section's heights,
widths and slopes); every size written on the drawing must come back within the tolerance.
Sizes that do not are sent back to the AI with the model's own lengths, up to --rounds times.
Then the cover is built as models/drawing-<code>/ and calculated like the others. Results:
<out>/swept.json and swept.csv (per drawing: the sizes matched, the ones that are not, why).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coverengine.drawing_ai import (  # noqa: E402
    read,
)
from coverengine.params import Registry  # noqa: E402


def calculate(code: str, shape: dict[str, Any], timeout: int) -> dict[str, Any]:
    """The cover built and calculated (drawing_cover.py) in a process of its own, with a limit."""
    import subprocess

    cmd = [sys.executable, str(Path(__file__).with_name("drawing_cover.py")), code, "swept",
           json.dumps(shape)]  # fmt: skip
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "failed", "detail": f"the calculation took over {timeout} s"}
    if r.returncode:
        last = (r.stderr.strip().splitlines() or r.stdout.strip().splitlines() or ["?"])[-1]
        return {"status": "failed", "detail": last[-300:]}
    model = "drawing-" + re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-")
    return {"status": "calculated", "model": model}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--pdfs", type=Path, required=True)
    ap.add_argument("--only")
    ap.add_argument("--codes-from", type=Path)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=1500, help="seconds for one cover's calculation")
    ap.add_argument("--force", action="store_true", help="also the drawings already built")
    a = ap.parse_args()
    base = Registry.load(None).resolve()
    params = Registry.load(None).resolve(trial={
        "ai.provider": str(base["ai.vision_provider"]), "ai.model": str(base["ai.vision_model"]),
        "ai.base_url": str(base["ai.vision_base_url"]), "ai.timeout_s": 600})  # fmt: skip
    pdfs = {re.sub(r"^cover \d+ - ", "", p.stem): p for p in sorted(a.pdfs.glob("*.pdf"))}
    codes = list(pdfs)
    if a.codes_from:
        rows = json.loads(a.codes_from.read_text())
        codes = [
            r["code"] for r in rows if r.get("status") == "not built" and r.get("shape") == "other"
        ]
    if a.only:
        codes = a.only.split(",")
    a.out.mkdir(parents=True, exist_ok=True)
    results = []

    each = a.out / "each"
    each.mkdir(exist_ok=True)

    def one(code: str) -> dict[str, Any]:
        """One drawing, its result kept at once; the calculation in its own process with a time
        limit, so one cover that hangs or fails never stops the others."""
        keep = each / (re.sub(r"[^A-Za-z0-9]+", "-", code).strip("-") + ".json")
        if keep.is_file() and not a.force:
            old = json.loads(keep.read_text())
            if old.get("status") == "built":
                return dict(old)
        pdf = pdfs.get(code) or next((p for k, p in pdfs.items() if k.endswith(code)), None)
        res: dict[str, Any] = {"code": code, "status": "no pdf"}
        try:
            if pdf is not None:
                res = read(code, pdf, params, a.rounds)
                res["status"] = "read" if not res["missing"] else "read, sizes missing"
                if (res.get("shape") or {}).get("why_not"):
                    # the reader says this drawing is not a swept shape: never build a stand-in
                    # (S45, a kidney, came out as a box; ADR-072). drawing_outline.py may fit it.
                    res["status"] = "not a swept shape"
                elif not a.no_build and not res.get("error"):
                    res.update(calculate(code, res["shape"], a.timeout))
                    if res["status"] == "calculated":
                        res["status"] = "built" if not res["missing"] else "built, check sizes"
            n = f"{res.get('matched')}/{len(res.get('written') or [])}"
            print(f"{code}: {res['status']}, {n} sizes {res.get('detail', '')}", flush=True)
        except BaseException as exc:  # noqa: BLE001 - one drawing must not stop the others
            res = {**res, "status": "failed", "error": str(exc),
                   "trace": traceback.format_exc()[-800:]}  # fmt: skip
            print(f"{code}: failed: {exc}", flush=True)
        keep.write_text(json.dumps(res, indent=1, default=str))
        return res

    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        results = list(pool.map(one, codes))
    (a.out / "swept.json").write_text(json.dumps(results, indent=1, default=str))
    with (a.out / "swept.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "status", "matched", "written", "missing", "notes", "why_not"])
        for r in results:
            sh = r.get("shape") or {}
            w.writerow([r["code"], r.get("status"), r.get("matched"), len(r.get("written") or []),
                        " ".join(str(x) for x in r.get("missing") or []), sh.get("notes", ""),
                        sh.get("why_not", "")])  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
