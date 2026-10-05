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
import base64
import csv
import json
import re
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coverengine import swept  # noqa: E402
from coverengine.ai import ask_parts  # noqa: E402
from coverengine.errors import CoverError  # noqa: E402
from coverengine.params import Registry  # noqa: E402

DPI = 120
CM = re.compile(r"(\d+(?:[.,]\d+)?)\s*cm", re.I)
INCH = re.compile(r"(\d+(?:[.,]\d+)?)\s*in\b", re.I)
TOL_CM, TOL_REL = 1.0, 0.006  # a written size matches within 1 cm or 0.6 %

SYSTEM = """You turn a cover workshop's technical drawing (several pages: views with sizes in cm,
inches in brackets) into the exact shape a program rebuilds. Many covers here are a sofa-like
"sloped box" that runs along a path which is not one straight line: a quarter ring, a U or
horseshoe, a crescent, a tapered or angled sofa, an arm that comes down along its length. The
program sweeps a cross-section along the cover's BACK EDGE (the bottom edge of the high, back
side; for a ring or U it is the outside edge) as seen in the top view.

THE PATH starts at one end of the back edge and runs along it to the other end. Heading at the
start: along +x; the front is on the side the cover's depth goes. Segments, in cm:
  {"line": L}                      straight;
  {"arc": R, "angle": A}           a curve of radius R (of the back edge itself). A > 0 when the
                                   back edge bends TOWARDS the front (the back is the outer side:
                                   ring, U, crescent seen from inside), A < 0 when it bends away;
  {"turn": A}                      a sharp corner (degrees, > 0 towards the front).
Find radii from arc lengths: an arc of length L over angle A (deg) has R = L / (A·π/180); two
concentric arcs of lengths L1 > L2, D apart, span A = (L1 − L2)/D radians.

THE CROSS-SECTION: the top from the back edge to the front edge as points [offset, height]: the
offset is the HORIZONTAL (plan) distance from the back edge, the height above the ground, both in
cm; every point is a line along the cover on the drawing (a seam or a fold). Example: a back wall
62.9 high, a short steep chamfer up to a flat top at 87.9, the flat top 43 deep, a long slope to
the front wall 40 high, 120 deep in all: [[0, 62.9], [17, 87.9], [60, 87.9], [120, 40]]. If a size
is along a slope, convert it to plan with Pythagoras. The walls drop from the first and the last
point to the ground. If the cross-section changes along the path (a taper, an arm that comes
down), give "profiles": [{"at_cm": s, "points": [...]}, ...] with the same number of points, s
along the back edge; otherwise "profile": [[o, z], ...].

SEAMS ACROSS: "seams_cm": positions along the back edge (cm from the path's start) of every line
drawn across the cover (top and walls); corners and line/arc changes are seams already.
HIPS: when a line along the top is shorter than the cover (it stops before the ends and the top
slopes down to a lower end wall, the end wall's top running straight from the back wall's top to
the front wall's top), give "line_lengths_cm": one value per cross-section point, its length as
written (null for the lines that run the full length; the first and last always do). The
program stops it evenly at both ends and makes the sloping end faces.
ENDS: "start_end" and "end_end": "square" (upright end wall), "round" (half-round in the top view),
or "angled" with "end_angle_deg" (leaning in, in the top view; straight paths only).

If the drawing is not such a shape at all (two separate covers, a sleeve, a closed ring), say so in
"why_not" and give your best path anyway. Answer with JSON only:
{"path": [...], "profile": [...] or "profiles": [...], "line_lengths_cm": [...], "seams_cm": [...],
 "start_end": "...",
 "end_end": "...", "end_angle_deg": 0, "notes": "how you read it, which view gave what",
 "why_not": ""}"""


def written_sizes(pdf: Path) -> list[float]:
    """The sizes on the drawing in cm; a drawing in inches only (S38, S39) is converted."""
    text = " ".join(page.get_text() for page in pymupdf.open(pdf))
    out = [float(m.group(1).replace(",", ".")) for m in CM.finditer(text)]
    if not out:
        out = [round(float(m.group(1).replace(",", ".")) * 2.54, 2) for m in INCH.finditer(text)]
    return sorted({v for v in out if 1.0 <= v <= 2000})  # param-ok: sensible cover sizes


def pictures(pdf: Path) -> list[str]:
    doc = pymupdf.open(pdf)
    return [base64.b64encode(p.get_pixmap(dpi=DPI).tobytes("png")).decode() for p in doc]


def lengths(p: dict[str, Any]) -> dict[str, float]:
    """Every length the drawing could show, from the model the program builds (cm)."""
    stations, cuts = swept._path(list(p.get("path") or []), list(p.get("seams_cm") or []))
    total = stations[-1].s
    profiles = swept._profiles(_norm(p), total)
    stations = swept._with_cuts(stations, cuts)
    rows = len(profiles[0][1])
    spans = swept._spans(p, stations, profiles, rows)
    stations = swept._with_cuts(stations, sorted({x for ab in spans for x in ab}))
    out: dict[str, float] = {}
    prof0, prof1 = profiles[0][1], swept._at(profiles, total)

    def run(seg: np.ndarray) -> float:
        return float(np.linalg.norm(np.diff(seg, axis=0), axis=1).sum()) if len(seg) > 1 else 0.0

    for j in range(rows):
        a, b = spans[j]
        on = [st for st in stations if a - 1e-6 <= st.s <= b + 1e-6]
        xyz = np.array([[*(st.p + st.n * swept._at(profiles, st.s)[j, 0]),
                         swept._at(profiles, st.s)[j, 1]] for st in on])  # fmt: skip
        out[f"line {j} along the cover"] = run(xyz)
        for k, (c0, c1) in enumerate(zip(cuts, cuts[1:], strict=False), start=1):
            sel = [i for i, st in enumerate(on) if c0 - 1e-6 <= st.s <= c1 + 1e-6]
            out[f"line {j}, part {k}"] = run(xyz[sel])
        out[f"height of line {j} (start)"] = float(prof0[j, 1])
        out[f"height of line {j} (end)"] = float(prof1[j, 1])
        out[f"plan offset of line {j}"] = float(prof0[j, 0])
    for j in range(len(prof0) - 1):
        for tag, pr in (("start", prof0), ("end", prof1)):
            d = pr[j + 1] - pr[j]
            out[f"band {j + 1} across, along the surface ({tag})"] = float(np.hypot(*d))
            out[f"band {j + 1} across, in plan ({tag})"] = float(abs(d[0]))
            out[f"rise of band {j + 1} ({tag})"] = float(abs(d[1]))
    out["depth (start)"] = float(prof0[-1, 0])
    out["depth (end)"] = float(prof1[-1, 0])
    for i, seg in enumerate(p.get("path") or []):
        if "line" in seg:
            out[f"path segment {i + 1} (line)"] = float(seg["line"])
    return out


def _norm(p: dict[str, Any]) -> dict[str, Any]:
    q = dict(p)
    if "profile" in q and "profiles" not in q:
        q["profiles"] = [{"at_cm": 0, "points": q["profile"]}]
    return q


def check(
    written: list[float], model: dict[str, float]
) -> tuple[list[dict[str, Any]], list[float]]:
    matched, missing = [], []
    vals = list(model.items())
    for w in written:
        name, v = min(vals, key=lambda kv: abs(kv[1] - w))
        if abs(v - w) <= max(TOL_CM, TOL_REL * w):
            matched.append({"written_cm": w, "model": name, "model_cm": round(v, 2)})
        else:
            missing.append(w)
    return matched, missing


def read(code: str, pdf: Path, params: Any, rounds: int) -> dict[str, Any]:
    imgs = pictures(pdf)
    sizes = written_sizes(pdf)
    parts: list[dict[str, Any]] = [{"type": "text", "text":
        f"Drawing {code}. Sizes written on it (cm): {sizes}. All its pages follow."}]  # fmt: skip
    parts += [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{i}"}} for i in imgs
    ]
    history: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for r in range(rounds):
        ans = ask_parts(params, SYSTEM, parts)
        ans.pop("_usage", None)
        shape = _norm(ans)
        try:
            ls = lengths(shape)
            swept.build(shape, 1e9, 1e9)  # it can be built at all
            matched, missing = check(sizes, ls)
            err = ""
        except (CoverError, KeyError, ValueError, IndexError, TypeError) as exc:
            matched, missing, ls, err = [], sizes, {}, str(exc)
        step = {"round": r + 1, "shape": shape, "matched": len(matched), "missing": missing,
                "error": err}  # fmt: skip
        history.append(step)
        if best is None or (not err and len(matched) > best["matched"]):
            best = {**step, "lengths": ls, "matched_list": matched}
        if not err and not missing:
            break
        feedback = (f"Round {r + 1}: " + (f"the program could not build it: {err}. " if err else "")
                    + f"These written sizes are not found in the model: {missing}. The model's own "
                    f"lengths (cm): {json.dumps({k: round(v, 2) for k, v in ls.items()})}. "
                    "Look again at the views and correct the path, the cross-section or the seams "
                    "so every written size comes back. Answer the full JSON again.")  # fmt: skip
        parts = [
            *parts,
            {"type": "text", "text": json.dumps(ans)},
            {"type": "text", "text": feedback},
        ]
    assert best is not None
    return {"code": code, "file": pdf.name, "written": sizes, "rounds": history, **best}


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
