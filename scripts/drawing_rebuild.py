"""Every drawing cover built again from the drawing's own views; the better one stays (ADR-075).

    uv run python scripts/drawing_rebuild.py out/drawings/rebuild --pdfs <PDF folder>
        [--only S38,S44] [--dry-run] [--workers 3]

Per drawing:

1. coverengine.drawing_solid.best_solid: the views, the scale from the size arrows, the solid
   (plan cut by the elevations), the best fit to the drawing's 3D view (IoU).
2. The live cover's own surface is scored against the same 3D view.
3. When the new solid fits clearly better (at least MARGIN higher, and at least MIN_IOU), or
   the AIs found the live cover poor (below WEAK_SCORE) and the new one fits fairly, it is
   built as a cover beside the live one (out/.../staging/), with the drawing's features (vent
   count), and Gemini and DeepSeek check it and each other (coverengine.crosscheck). The live
   cover is checked too when it was not yet.
4. Only when the AIs also find it better (agreed "same" where the old was not, or a higher
   average score by SCORE_MARGIN) does it replace the live cover: in its own folder, as a new
   revision (history, references and settings kept; the old drape results removed, they showed
   the old shape). Everything is backed up before (the caller's job: see the night backup).

Out: <out>/<code>.json per drawing and rebuild.json; replaced covers listed for the mail.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coverengine import crosscheck  # noqa: E402
from coverengine.drawing_solid import best_solid, iso_fit, model_surface, pieces  # noqa: E402
from coverengine.io.kind import confirm  # noqa: E402
from drawing_cover import make, roll_mm  # noqa: E402
from drawing_features import pdfs, slug  # noqa: E402

MIN_IOU = 0.85  # the new solid must cover the 3D view this well
MARGIN = 0.03  # and this much better than the live cover
SCORE_MARGIN = 5.0  # the AIs' average score must rise this much (when neither is "same")
WEAK_SCORE = 60.0  # the AIs found the live cover poor below this average
FAIR_IOU = 0.80  # then a new shape that fits the 3D view this well is shown to them too
STEPS = ("hull", "cut", "flatten", "export", "preview")


def cover(*args: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "coverengine.cli", *args], capture_output=True,
                       text=True, check=False)  # fmt: skip
    lines = r.stderr.strip().splitlines() or r.stdout.strip().splitlines() or [""]
    return r.returncode, lines[-1]


def score(check: dict[str, Any]) -> float:
    g = check.get("gemini_second") or check.get("gemini") or {}
    d = check.get("deepseek") or {}
    vals = [float(x) for x in (g.get("score"), d.get("score")) if isinstance(x, int | float)]
    return sum(vals) / len(vals) if vals else 0.0


def better(new: dict[str, Any], old: dict[str, Any]) -> bool:
    if new.get("outcome") == "agreed: same" and old.get("outcome") != "agreed: same":
        return True
    if new.get("outcome") == "agreed: different" and old.get("outcome") == "agreed: same":
        return False
    return score(new) >= score(old) + SCORE_MARGIN


def replace_live(live: Path, src_glb: Path, params: dict[str, Any], note: str) -> str:
    """The new surface into the live cover's own folder, calculated as a new revision."""
    rc, last = cover("import", str(src_glb), "--out", str(live), "--units", "mm", "--up", "z")
    if rc:
        return f"import failed: {last}"
    confirm(live, "cover")
    doc = json.loads((live / "cover.json").read_text())
    mine = doc.setdefault("parameters", {})
    for group, values in params.items():
        mine.setdefault(group, {}).update(values)
    doc["notes"] = note
    (live / "cover.json").write_text(json.dumps(doc, indent=2) + "\n")
    for old in list(live.glob("drape*")):  # the old drape showed the old shape
        old.unlink()
    for step in STEPS:
        rc, last = cover(step, str(live))
        if rc:
            return f"{step} failed: {last}"
    return "replaced"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--pdfs", type=Path, required=True)
    ap.add_argument("--only")
    ap.add_argument("--dry-run", action="store_true", help="score and build, never replace")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--old-checks", type=Path, default=Path("out/drawings/crosscheck"))
    ap.add_argument("--one", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--timeout", type=int, default=2400, help="seconds per drawing")
    a = ap.parse_args()
    found = pdfs(a.pdfs)
    codes = a.only.split(",") if a.only else list(found)
    a.out.mkdir(parents=True, exist_ok=True)
    staging = a.out / "staging" / "models"
    staging.mkdir(parents=True, exist_ok=True)
    roll = roll_mm()

    def one(code: str) -> dict[str, Any]:
        pdf, live = found[code], Path("models") / slug(code)
        res: dict[str, Any] = {"code": code, "model": live.name, "time": time.time()}
        try:
            r = best_solid(pdf)
            b = r["best"]
            iso = next((v for v in r["read"]["views"] if v.kind == "iso"), None)
            res["scale_from"] = r["read"]["scale_from"]
            if b is None or iso is None:
                res["status"] = "kept: no plan or no 3D view to build from"
                return res
            res["new_iou"], res["how"] = round(b["iou"], 3), b["how"]
            res["old_iou"] = round(iso_fit(model_surface(live), iso, mirror=True)[0], 3)
            old_file = a.old_checks / f"{code}.json"
            old = json.loads(old_file.read_text()) if old_file.is_file() else None
            weak = old is not None and "outcome" in old and score(old) < WEAK_SCORE
            clearly = b["iou"] >= MIN_IOU and b["iou"] >= res["old_iou"] + MARGIN
            # the AIs found the live cover poor: let them judge any new shape that fits fairly
            fair = weak and b["iou"] >= FAIR_IOU and b["iou"] >= res["old_iou"] - MARGIN
            if not (clearly or fair):
                res["status"] = "kept: the new shape does not fit the 3D view clearly better"
                return res
            feats = apply_features(pdf)
            params = {"hull": {"top": "given"}, **feats}
            note = (f"Drawing {code}: built from the drawing's own views (ADR-075): "
                    f"{', '.join(b['how'])}; fits the 3D view {b['iou']:.0%}")  # fmt: skip
            cand = make(code, "views", {}, staging, note=note, pieces=pieces(b["solid"], roll),
                        parameters=params)  # fmt: skip
            res["candidate"] = str(cand)
            res["new_check"] = crosscheck.run(pdf, cand)
            if old is None or "outcome" not in old:
                old = crosscheck.run(pdf, live)
                a.old_checks.mkdir(parents=True, exist_ok=True)
                old_file.write_text(json.dumps({"code": code, **old}, indent=1))
            res["old_check"] = {k: old.get(k) for k in ("outcome", "gemini", "deepseek",
                                                          "gemini_second")}  # fmt: skip
            res["new_score"], res["old_score"] = score(res["new_check"]), score(old)
            if not better(res["new_check"], old):
                res["status"] = "kept: the AIs do not find the new cover better"
            elif a.dry_run:
                res["status"] = "would replace (dry run)"
            else:
                src = staging.parent / "out" / "drawn" / f"{live.name}.glb"
                res["status"] = replace_live(live, src, params, note)
        except Exception as exc:  # noqa: BLE001 - one drawing must not stop the others
            res["status"] = f"failed: {exc}"
            res["trace"] = traceback.format_exc()[-800:]
        finally:
            (a.out / f"{re.sub(r'[^A-Za-z0-9]+', '-', code).strip('-')}.json").write_text(
                json.dumps(res, indent=1, default=str))  # fmt: skip
            print(code, res.get("status"), res.get("old_iou"), "->", res.get("new_iou"),
                  res.get("old_score"), "->", res.get("new_score"), flush=True)  # fmt: skip
        return res

    if a.one:  # a child process: this one drawing
        one(codes[0])
        return 0

    def child(code: str) -> dict[str, Any]:
        """Each drawing in a process of its own: the geometry libraries are not safe in
        threads (a crash took the whole run with it), and one hang must not stop the rest."""
        args = [
            sys.executable,
            __file__,
            str(a.out),
            "--pdfs",
            str(a.pdfs),
            "--only",
            code,
            "--one",
            "--old-checks",
            str(a.old_checks),
        ] + (["--dry-run"] if a.dry_run else [])
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=a.timeout,
                               check=False)  # fmt: skip
            tail = (r.stdout.strip().splitlines() or [""])[-1]
        except subprocess.TimeoutExpired:
            tail = f"{code} failed: over {a.timeout} s"
        keep = a.out / f"{re.sub(r'[^A-Za-z0-9]+', '-', code).strip('-')}.json"
        res = json.loads(keep.read_text()) if keep.is_file() else {"code": code}
        if "status" not in res or r_failed(tail, res):
            res["status"] = res.get("status") or f"failed: {tail[-300:]}"
        print(tail, flush=True)
        return res

    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        rows = list(pool.map(child, codes))
    (a.out / "rebuild.json").write_text(json.dumps(rows, indent=1, default=str))
    return 0


def r_failed(tail: str, res: dict[str, Any]) -> bool:
    return "status" not in res


def apply_features(pdf: Path) -> dict[str, Any]:
    from coverengine.drawing_vectors import features

    f = features(pdf)
    return {"features": {"vents_total": int(f["vents_total"])}} if f["vents_total"] else {}


if __name__ == "__main__":
    raise SystemExit(main())
