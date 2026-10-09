"""Rebuild the covers with inner walls in staging with vents on the front walls (ADR-110).

    uv run python scripts/innerwalls_sweep.py LIST.json --out out/innerwalls [--models models]
        [--staged DIR] [--only a,b]

LIST.json: [{"model": ID, ...}] (the covers with inner walls). Each live folder is copied to
OUT/<model>/ (the live folder is only read), `cover flatten --force` and `cover export --force`
run with the company default (`features.vent_inner_walls: true`), then `cover audit` and
scripts/fewer_check.py check it twice. Per-cover `vent_positions` set from Rens's circles in a
staged folder (--staged, e.g. the vents agent's out/rejections/A) are carried over; a
`vent_inner_walls` set per cover is dropped (the default now says it). A compare picture per
cover goes to OUT/compare/ (scripts/vents_compare.py, with the Desk's marked pictures).
Writes OUT/results.json.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(args: list[str], log: Path) -> int:
    with log.open("a", encoding="utf-8") as f:
        f.write("$ " + " ".join(args) + "\n")
        f.flush()
        return subprocess.run(args, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT).returncode


def _vents(d: Path) -> list[dict]:
    p = d / "vents.json"
    return json.loads(p.read_text())["vents"] if p.is_file() else []


def sweep(model: str, models: Path, out: Path, staged: Path | None) -> dict:
    src, dst = models / model, out / model
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=True)
    log = dst / "innerwalls.log"
    res: dict = {"model": model, "vents_before": len(_vents(src))}
    cov = dst / "cover.json"
    doc = json.loads(cov.read_text()) if cov.is_file() else {}
    feats = doc.setdefault("parameters", {}).setdefault("features", {})
    feats.pop("vent_inner_walls", None)
    carried = None
    if staged and (staged / model / "cover.json").is_file():
        sf = (json.loads((staged / model / "cover.json").read_text()).get("parameters") or {}).get(
            "features", {}
        )
        if sf.get("vent_positions"):
            carried = feats["vent_positions"] = sf["vent_positions"]
    res["vent_positions"] = carried or feats.get("vent_positions")
    if not feats:
        doc["parameters"].pop("features")
    if cov.is_file() or carried:
        cov.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (dst / "vents.json").unlink(missing_ok=True)
    cover = [sys.executable, "-m", "coverengine.cli"]
    for step in ("flatten", "export"):
        rc = _run([*cover, step, str(dst), "--force"], log)
        if rc:
            res["error"] = f"{step} exit {rc}"
            return res
    # vents.json for the 3D view and the checks
    from coverengine.finish.vents3d import ensure_vents

    ensure_vents(dst)
    vents = _vents(dst)
    res["vents_after"] = len(vents)
    res["pieces_with_vents"] = sorted({v["piece"] for v in vents})
    _run([*cover, "audit", str(dst), "--out", str(dst / "audit-out")], log)
    au = dst / "audit.json"
    if au.is_file():
        checks = json.loads(au.read_text())["checks"]
        res["audit_ok"] = all(c["ok"] for c in checks)
        res["audit_failed"] = {c["check"]: c["detail"] for c in checks if not c["ok"]}
        res["audit_vents"] = next((c["detail"] for c in checks if c["check"] == "vents"), None)
    else:
        res["audit_ok"], res["audit_failed"] = False, {"audit": "no audit.json"}
    old = src / "audit.json"
    if old.is_file():  # the live cover's own last audit, for what was failing before
        res["audit_failed_live"] = sorted(
            c["check"] for c in json.loads(old.read_text())["checks"] if not c["ok"]
        )
    f = subprocess.run(
        [sys.executable, str(ROOT / "scripts/fewer_check.py"), str(dst)],
        cwd=ROOT, capture_output=True, text=True,
    )  # fmt: skip
    res["fewer_exit"] = f.returncode
    res["fewer"] = [ln for ln in (f.stdout + f.stderr).splitlines() if ln.strip()][-6:]
    pics = sorted((src / "desk").glob("*.png")) if (src / "desk").is_dir() else []
    (out / "compare").mkdir(parents=True, exist_ok=True)
    png = out / "compare" / f"{model}.png"
    c = subprocess.run(
        [sys.executable, str(ROOT / "scripts/vents_compare.py"), str(png),
         "--old", str(src), "--new", str(dst), *(["--pics", *map(str, pics)] if pics else [])],
        cwd=ROOT, capture_output=True, text=True,
    )  # fmt: skip
    res["compare"] = str(png) if not c.returncode else c.stderr[-300:]
    res["desk_pics"] = len(pics)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("list", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "out/innerwalls")
    ap.add_argument("--models", type=Path, default=ROOT / "models")
    ap.add_argument("--staged", type=Path)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    ids = [r["model"] for r in json.loads(a.list.read_text())]
    if a.only:
        ids = [m for m in ids if m in a.only.split(",")]
    a.out.mkdir(parents=True, exist_ok=True)
    path = a.out / "results.json"
    done = {r["model"]: r for r in json.loads(path.read_text())} if path.is_file() else {}
    for m in ids:
        try:
            r = sweep(m, a.models, a.out, a.staged)
        except Exception as e:  # noqa: BLE001 - one cover must not stop the rest
            r = {"model": m, "error": repr(e)}
        done[m] = r
        path.write_text(json.dumps(list(done.values()), indent=1))
        ok = "ok" if r.get("audit_ok") and r.get("fewer_exit") == 0 else "CHECK"
        print(m, r.get("vents_before"), "->", r.get("vents_after"), ok, r.get("error", ""),
              flush=True)  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
