"""Covers rebuilt in staging from the Desk's answers, checked twice, a compare picture (ADR-117).

    uv run python scripts/answers_stage.py SPECS.json --out out/answers [--only a,b] [--workers 2]

SPECS.json: a list of
    {"model": ID,
     "cover": {...},          # merged into the staged cover.json (a null value removes the key)
     "files": {"box_shape.json": "testdata/box_shapes/ID.json"},   # copied into the folder
     "steps": ["hull", "cut", "flatten", "export"]}                # default: all four

Each live folder (--models, only read) is copied to OUT/<model>/ without its revisions, the
changes are applied, the steps run with --force, then the checks: finished.json warnings,
`cover audit` (OUT/<model>/audit.json) and the independent re-measure scripts/fewer_check.py.
A compare picture goes to OUT/compare/<model>.png: per Desk picture of the model (its
desk/*.png) the picture, the live cover and the staged cover from the camera fitted to the
picture (scripts/desk_marks.py), with the red marks mapped onto the live cover; below them the
live and staged covers from above and from the back. One line per cover in OUT/stage.json.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from coverengine.staging import guard_staging_output

ROOT = Path(__file__).resolve().parent.parent
LIVE = Path("/home/dev/cover-pattern-engine/models")
STEPS = ["hull", "cut", "flatten", "export"]


def _merge(doc: dict[str, Any], patch: dict[str, Any]) -> None:
    for k, v in patch.items():
        if v is None:
            doc.pop(k, None)
        elif isinstance(v, dict) and isinstance(doc.get(k), dict):
            _merge(doc[k], v)
        else:
            doc[k] = v


def _run(args: list[str], log: Path) -> int:
    with log.open("a", encoding="utf-8") as f:
        f.write("$ " + " ".join(args) + "\n")
        f.flush()
        return subprocess.run(args, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT).returncode


def _pieces(d: Path) -> list[dict[str, Any]]:
    fin = d / "finished.json"
    if not fin.is_file():
        return []
    return [
        {"name": p["name"], "size_mm": [round(x) for x in p.get("size_mm") or []]}
        for p in json.loads(fin.read_text())["pieces"]
        if not str(p["name"]).startswith("vent-")
    ]


def stage(spec: dict[str, Any], out: Path, models: Path) -> dict[str, Any]:
    guard_staging_output(out, models)
    model = spec["model"]
    src, dst = models / model, out / model
    guard_staging_output(dst, src)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=True, ignore=shutil.ignore_patterns("revisions"))
    log = dst / "answers.log"
    res: dict[str, Any] = {"model": model}
    cov = dst / "cover.json"
    doc = json.loads(cov.read_text()) if cov.is_file() else {"format_version": 1}
    _merge(doc, spec.get("cover") or {})
    cov.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, path in (spec.get("files") or {}).items():
        shutil.copyfile(ROOT / path, dst / name)
    (dst / "vents.json").unlink(missing_ok=True)
    for stale in dst.glob("drape*"):  # the live cover's drape, not this one's (not re-run)
        stale.unlink()
    cover = [sys.executable, "-m", "coverengine.cli"]
    for step in spec.get("steps", STEPS):
        if _run([*cover, step, str(dst), "--force"], log):
            res["error"] = f"cover {step} failed (see {log})"
            return res
    from coverengine.finish.vents3d import ensure_vents

    ensure_vents(dst)
    vents = (
        json.loads((dst / "vents.json").read_text())["vents"]
        if (dst / "vents.json").is_file()
        else []
    )
    res["vents"] = len(vents)
    res["vent_pieces"] = sorted(v["piece"] for v in vents)
    fin = json.loads((dst / "finished.json").read_text())
    res["warnings"] = fin.get("warnings") or []
    res["pieces"] = _pieces(dst)
    res["pieces_live"] = len(_pieces(src))
    _run([*cover, "audit", str(dst), "--out", str(dst / "audit-out")], log)
    au = dst / "audit.json"
    checks = json.loads(au.read_text())["checks"] if au.is_file() else []
    res["audit_ok"] = bool(checks) and all(c["ok"] for c in checks)
    res["audit_failed"] = {c["check"]: c["detail"] for c in checks if not c["ok"]}
    f = subprocess.run([sys.executable, str(ROOT / "scripts/fewer_check.py"), str(dst)],
                       cwd=ROOT, capture_output=True, text=True)  # fmt: skip
    res["fewer_exit"] = f.returncode
    res["fewer"] = [ln.strip() for ln in (f.stdout + f.stderr).splitlines() if ln.strip()][-3:]
    try:
        res["compare"] = str(compare(model, src, dst, out / "compare" / f"{model}.png"))
    except Exception as exc:  # noqa: BLE001 - the picture must not stop the checks
        res["compare"] = f"failed: {exc!r}"
    return res


# --- the compare picture ---------------------------------------------------------------------


def _draw(d: Path, cam: Any, w: int, h: int, title: str, marks: list | None = None) -> Any:
    from coverengine.palette import PIECES
    from PIL import Image, ImageDraw

    data = np.load(d / "panels.npz")
    names = [p["name"] for p in json.loads((d / "panels.json").read_text())["panels"]]
    verts, faces, labels, orig = (
        data["vertices"],
        data["faces"],
        data["labels"],
        data["original_vertex"],
    )
    p = cam.project(verts)
    tri = verts[faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    facing = np.einsum("ij,ij->i", n, tri.mean(axis=1) - cam.eye) < 0
    light = np.array([0.4, -0.5, 0.8]) / np.linalg.norm([0.4, -0.5, 0.8])
    shade = 0.62 + 0.38 * np.abs(n @ light)
    order = np.argsort(-((tri.mean(axis=1) - cam.eye) @ cam.f))
    im = Image.new("RGB", (w, h), (249, 246, 232))
    dr = ImageDraw.Draw(im)
    for fi in order:
        c = (
            np.array(PIECES[int(labels[fi]) % len(PIECES)])
            * shade[fi]
            * (1.0 if facing[fi] else 0.75)
        )
        col = tuple(int(255 * min(v, 1)) for v in c)
        dr.polygon([tuple(p[i]) for i in faces[fi]], fill=col, outline=col)
    key: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    for fi, t in enumerate(faces):
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            key.setdefault((min(orig[a], orig[b]), max(orig[a], orig[b])), []).append((fi, a, b))
    for lst in key.values():
        labs = {int(labels[f]) for f, _, _ in lst}
        if (len(labs) > 1 or len(lst) == 1) and any(facing[f] for f, _, _ in lst):
            _, a, b = lst[0]
            dr.line([tuple(p[a]), tuple(p[b])], fill=(40, 45, 55), width=2)
    vj = d / "vents.json"
    for v in json.loads(vj.read_text())["vents"] if vj.is_file() else []:
        c = np.asarray(v["corners_mm"]) + np.asarray(v["normal"]) * 10.0
        if (np.asarray(v["normal"]) @ (c.mean(axis=0) - cam.eye)) < 0:
            dr.polygon([tuple(q) for q in cam.project(c)], fill=(30, 30, 30), outline=(200, 40, 30))
    for li, nm in enumerate(names):
        sel = (labels == li) & facing
        if sel.sum() < 3:
            continue
        c = cam.project(tri[sel].reshape(-1, 3).mean(axis=0)[None])[0]
        dr.text((c[0] - 20, c[1]), nm, fill=(20, 20, 90))
    for pt in marks or []:
        q = cam.project(np.array([pt[:3]], float))[0]
        dr.ellipse([q[0] - 3, q[1] - 3, q[0] + 3, q[1] + 3], fill=(225, 30, 30))
    dr.text((10, 8), f"{title}: {len(names)} pieces", fill=(0, 0, 0))
    return im


def _fit(src: Path, pic: Path, cache: Path) -> dict[str, Any] | None:
    if not cache.is_file():
        args = [sys.executable, str(ROOT / "scripts/desk_marks.py"), str(src), str(pic),
                str(cache.with_suffix(""))]  # fmt: skip
        r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
        if r.returncode or not cache.is_file():
            return None
    return dict(json.loads(cache.read_text()))


def compare(model: str, src: Path, dst: Path, png: Path) -> Path:
    from PIL import Image, ImageDraw

    sys.path.insert(0, str(ROOT / "scripts"))
    from desk_marks import Cam

    data = np.load(src / "panels.npz")
    lo, hi = data["vertices"].min(axis=0), data["vertices"].max(axis=0)
    centre, size = (lo + hi) / 2, float(np.linalg.norm(hi - lo))
    w, h = 700, 420
    rows = []
    pics = sorted((src / "desk").glob("*.png")) if (src / "desk").is_dir() else []
    marks_dir = png.parent.parent / "marks"
    marks_dir.mkdir(parents=True, exist_ok=True)
    for pic in pics:
        fit = _fit(src, pic, marks_dir / f"{model}-{pic.stem}.json")
        img = Image.open(pic).convert("RGB")
        if fit is None:
            rows.append([img.resize((w, int(img.height * w / img.width)))])
            continue
        c = fit["camera"]
        x = np.array([math.radians(c["azimuth_deg"]), math.radians(c["elevation_deg"]),
                      c["distance"], *c["target_shift"]])  # fmt: skip
        W, H = img.size
        cam = Cam(x, centre, size, w, int(H * w / W))
        pts = [p for s in fit["strokes"] for p in s["points"]]
        rows.append([img.resize((w, int(H * w / W))),
                     _draw(src, cam, w, int(H * w / W), "live", pts),
                     _draw(dst, cam, w, int(H * w / W), "staged")])  # fmt: skip
    views = []
    for az, el, nm in (
        (-90.0, 85.0, "from above"),
        (45.0, 30.0, "back right"),
        (225.0, 30.0, "front left"),
    ):
        cam = Cam(np.array([math.radians(az), math.radians(el), 1.5, 0, 0, 0]), centre, size, w, h)
        views.append(_draw(src, cam, w, h, f"live, {nm}"))
        views.append(_draw(dst, cam, w, h, f"staged, {nm}"))
    rows.append(views[0::2])
    rows.append(views[1::2])
    width = max(sum(t.width for t in r) for r in rows)
    height = sum(max(t.height for t in r) for r in rows) + 30
    out = Image.new("RGB", (width, height), (255, 255, 255))
    ImageDraw.Draw(out).text(
        (10, 8),
        f"{model}: Rens's picture | live | staged; then live and staged views",
        fill=(0, 0, 0),
    )
    y = 30
    for r in rows:
        xx = 0
        for t in r:
            out.paste(t, (xx, y))
            xx += t.width
        y += max(t.height for t in r)
    png.parent.mkdir(parents=True, exist_ok=True)
    out.save(png)
    return png


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("specs", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "out/answers")
    ap.add_argument("--models", type=Path, default=LIVE)
    ap.add_argument("--only", default="")
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    specs = json.loads(a.specs.read_text())
    if a.only:
        specs = [s for s in specs if s["model"] in a.only.split(",")]
    guard_staging_output(a.out, a.models)
    a.out.mkdir(parents=True, exist_ok=True)
    path = a.out / "stage.json"
    done = {r["model"]: r for r in json.loads(path.read_text())} if path.is_file() else {}

    def one(s: dict[str, Any]) -> dict[str, Any]:
        try:
            return stage(s, a.out, a.models)
        except Exception as e:  # noqa: BLE001 - one cover must not stop the rest
            return {"model": s["model"], "error": repr(e)}

    with ThreadPoolExecutor(a.workers) as ex:
        for r in ex.map(one, specs):
            done[r["model"]] = r
            path.write_text(json.dumps(list(done.values()), indent=1, ensure_ascii=False))
            ok = "ok" if r.get("audit_ok") and r.get("fewer_exit") == 0 else "CHECK"
            print(r["model"], ok, len(r.get("pieces") or []), "pieces", r.get("vents"), "vents",
                  r.get("error", ""), r.get("audit_failed", ""), flush=True)  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
